from tinkoff.invest import (
    Client,
    CandleInterval,
    OrderDirection,
    OrderType,
    InstrumentIdType,
    MoneyValue,
    RequestError
)
from decouple import config
from tinkoff.invest.utils import now
from datetime import datetime, timedelta
import time
import telebot
import numpy as np
import talib
import os
import schedule
import pandas as pd
from plyer import notification
import traceback

# Конфигурация
# Безопасная конфигурация через переменные окружения
TINKOFF_TOKEN = config('TINKOFF_TOKEN')  # Берет из .env
ACCOUNT_ID = config('ACCOUNT_ID')
TELEGRAM_TOKEN = config('TELEGRAM_TOKEN')
CHANNEL_ID = config('CHANNEL_ID')

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Данные инструментов
COMPANY_NAMES = ['Артген', 'АбрауДюрсо', ...]  # Сокращенный список для примера
FIGIS = ['TCS10A0JNAB6', 'BBG002W2FT69', ...]
TICKERS = ['ABIO', 'ABRD', ...]

# Параметры торговли
PURCHASE_AMOUNT = 10100
MAX_POSITIONS = 10
ATR_PERIOD = 14
STOP_LOSS_COEF = 2
TAKE_PROFIT_COEF = 3
RSI_OVERBOUGHT = 60
RSI_OVERSOLD = 32

client = Client(TINKOFF_TOKEN)
purchased_shares_count = 0
daily_profit = 0

def money_value_to_float(value):
    return value.units + value.nano / 1e9

def count_purchased_shares(filename):
    try:
        with open(filename, 'r') as file:
            return len(file.readlines())
    except FileNotFoundError:
        print(f"File {filename} not found")
        return 0

def safe_read_file(filename):
    try:
        with open(filename, 'r') as file:
            return [line.strip().split(',') for line in file]
    except IOError as e:
        print(f"Error reading file: {e}")
        return []

def safe_write_file(data, filename):
    try:
        with open(filename, 'w') as file:
            for item in data:
                file.write(','.join(map(str, item)) + '\n')
    except IOError as e:
        print(f"Error writing file: {e}")

def execute_order(figi, quantity, direction):
    try:
        response = client.orders.post_order(
            order_id=str(datetime.utcnow().timestamp()),
            figi=figi,
            quantity=quantity,
            account_id=ACCOUNT_ID,
            direction=direction,
            order_type=OrderType.ORDER_TYPE_MARKET
        )
        return response
    except RequestError as e:
        print(f"Order execution error: {e}")
        return None

def calculate_atr(closes):
    true_ranges = []
    for i in range(1, len(closes)):
        high_low = abs(closes[i] - closes[i-1])
        true_range = max(high_low, abs(closes[i] - closes[i-1]))
        true_ranges.append(true_range)
    return np.mean(true_ranges[:ATR_PERIOD])

def calculate_trade_levels(entry_price, closes):
    atr = calculate_atr(closes)
    stop_loss = entry_price - STOP_LOSS_COEF * atr
    take_profit = entry_price + TAKE_PROFIT_COEF * atr
    return atr, stop_loss, take_profit

def get_last_price(figi):
    try:
        response = client.market_data.get_last_prices(figi=[figi])
        return money_value_to_float(response.last_prices[0].price)
    except RequestError as e:
        print(f"Price check error: {e}")
        return None

def buy_asset(figi, ticker):
    global purchased_shares_count
    cash = money_value_to_float(client.operations.get_positions(
        account_id=ACCOUNT_ID).money[0])
    
    if cash < PURCHASE_AMOUNT:
        print("Insufficient funds")
        return 0

    price = get_last_price(figi)
    if not price:
        return 0

    instrument = client.instruments.share_by(
        id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI,
        id=figi
    ).instrument

    lot_size = instrument.lot
    lots = int(PURCHASE_AMOUNT // (lot_size * price))
    
    response = execute_order(figi, lots, OrderDirection.ORDER_DIRECTION_BUY)
    if not response:
        return 0

    executed_lots = response.lots_executed
    if executed_lots > 0:
        purchased_shares_count += 1
        entry_time = datetime.now().strftime("%d.%m. %H.%M.%S")
        return executed_lots, price, entry_time
    return 0

def sell_asset(figi, quantity):
    global purchased_shares_count
    response = execute_order(figi, quantity, OrderDirection.ORDER_DIRECTION_SELL)
    if response and response.lots_executed > 0:
        purchased_shares_count -= 1
        return money_value_to_float(response.executed_order_price)
    return None

def analyze_market_conditions(data, ticker, figi):
    closes = np.array([c.close.units + c.close.nano/1e9 for c in data])
    if len(closes) < 2:
        return

    rsi = talib.RSI(closes)[-1]
    current_price = closes[-1]
    
    positions = safe_read_file('positions.txt')
    position_exists = any(ticker in pos for pos in positions)

    if not position_exists and rsi < RSI_OVERSOLD and purchased_shares_count < MAX_POSITIONS:
        return 'BUY', current_price
    
    if position_exists and (rsi > RSI_OVERBOUGHT or current_price >= 1.005 * entry_price):
        return 'SELL', current_price
    
    return None

def send_notification(message):
    disclaimer = "https://t.me/Signali_TA/6011"
    bot.send_message(
        chat_id=CHANNEL_ID,
        text=f"{message}\n\nНе ИИР\n‼️ [ОБЯЗАТЕЛЬНО К ПРОЧТЕНИЮ]({disclaimer})",
        parse_mode='MARKDOWN'
    )

def log_transaction(ticker, action, price, quantity):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open('transactions.log', 'a') as f:
        f.write(f"{timestamp},{ticker},{action},{price},{quantity}\n")

def main_trading_cycle():
    global daily_profit
    positions = safe_read_file('positions.txt')
    
    for figi, ticker in zip(FIGIS, TICKERS):
        candles = client.get_all_candles(
            figi=figi,
            interval=CandleInterval.CANDLE_INTERVAL_5_MIN,
            from_=datetime.now() - timedelta(days=1),
            to=datetime.now()
        )
        
        recommendation = analyze_market_conditions(list(candles), ticker, figi)
        
        if recommendation:
            action, price = recommendation
            if action == 'BUY':
                result = buy_asset(figi, ticker)
                if result:
                    lots, entry_price, time = result
                    log_transaction(ticker, 'BUY', entry_price, lots)
                    send_notification(f"🟢 Покупка {ticker} по {entry_price}")
            elif action == 'SELL':
                position = next(pos for pos in positions if pos[0] == ticker)
                sell_price = sell_asset(figi, int(position[3]))
                if sell_price:
                    profit = (sell_price - float(position[1])) / float(position[1]) * 100
                    daily_profit += profit
                    log_transaction(ticker, 'SELL', sell_price, position[3])
                    send_notification(f"🔴 Продажа {ticker} с прибылью {profit:.2f}%")

    if daily_profit < -5:
        notification.notify(
            title='ПРЕДУПРЕЖДЕНИЕ',
            message='Превышен дневной лимит убытков!'
        )

def schedule_shutdown():
    schedule.every().day.at("23:55").do(os.system, "shutdown /s /t 1")
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    try:
        purchased_shares_count = count_purchased_shares('positions.txt')
        while True:
            main_trading_cycle()
            time.sleep(300)  # Проверка каждые 5 минут
    except KeyboardInterrupt:
        print("Trading bot stopped")
