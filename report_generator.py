import pandas as pd
from datetime import datetime, timedelta
from typing import Optional

def generate_trade_report(period: str = 'all') -> Optional[pd.DataFrame]:
    """Generate and save trading report for specified period.
    
    Args:
        period: Reporting period - 'day', 'week', 'month', 
                'year', 'month_start', 'year_start', or 'all'
    
    Returns:
        Filtered DataFrame if successful, None otherwise
    """
    try:
        # Load and validate trade data
        trade_data = pd.read_excel('trade_results.xlsx')
        
        # Column name constants from previous refactoring
        SELL_TIME_COL = 'sell_time'
        PROFIT_PCT_COL = 'profit_percent'
        
        if SELL_TIME_COL not in trade_data.columns:
            print(f"Required column '{SELL_TIME_COL}' missing")
            return None

        # Convert sell time with proper format
        trade_data[SELL_TIME_COL] = pd.to_datetime(
            trade_data[SELL_TIME_COL],
            format='%d.%m. %H.%M.%S'
        )

        # Filter data based on period
        current_date = datetime.now()
        filter_conditions = {
            'day': trade_data[SELL_TIME_COL].dt.date == current_date.date(),
            'week': trade_data[SELL_TIME_COL] >= (current_date - timedelta(days=current_date.weekday())),
            'month': trade_data[SELL_TIME_COL].dt.month == current_date.month,
            'year': trade_data[SELL_TIME_COL].dt.year == current_date.year,
            'month_start': trade_data[SELL_TIME_COL].dt.is_month_start,
            'year_start': trade_data[SELL_TIME_COL].dt.is_year_start,
            'all': pd.Series([True] * len(trade_data))
        }

        filtered_data = trade_data.loc[filter_conditions.get(period, 'all')]

        # Calculate and display results
        total_profit = filtered_data[PROFIT_PCT_COL].sum()
        print(f"Total profit: {total_profit:.2f}%")
        print(filtered_data)

        # Save filtered report
        report_filename = f'trade_report_{period}.xlsx'
        filtered_data.to_excel(report_filename, index=False)
        print(f"Report saved to {report_filename}")
        
        return filtered_data

    except FileNotFoundError:
        print("Error: Trade results file not found")
        return None
    except Exception as e:
        print(f"Error generating report: {str(e)}")
        return None

# Example usage
if __name__ == "__main__":
    generate_trade_report('day')
