from backtesting.backtest import Backtester

# Define initial capital in one place
INITIAL_CAPITAL = 5000  # Set to $1,000

def main():
    # Use the defined initial capital
    backtester = Backtester(
        initial_capital=INITIAL_CAPITAL,
        risk_per_trade=0.02
    )
    
    symbols = ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'GOOGL', 'AMZN', 'GOOG', 'META', 'TSM', 'NFLX']
    start_date = '2024-01-01'
    end_date = '2024-12-31'
    
    results = backtester.run(symbols, start_date, end_date)

if __name__ == "__main__":
    main() 