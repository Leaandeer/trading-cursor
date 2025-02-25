from backtesting.backtest import Backtester

# Define initial capital in one place
INITIAL_CAPITAL = 100  # Change this value to your desired starting capital

def main():
    risk_levels = [0.02]  
    
    for risk in risk_levels:
        print(f"\nTesting with {risk*100}% risk per trade")
        print("=" * 50)
        
        backtester = Backtester(
            initial_capital=INITIAL_CAPITAL,
            risk_per_trade=risk
        )
        
        symbols = ['AAPL', 'MSFT', 'GOOG', 'TSLA', 'NVDA', 'META', 'AMZN', 'NFLX', 'GOOG', 'TSLA', 'NVDA', 'META', 'AMZN', 'NFLX' ] 
        start_date = '2023-01-01'
        end_date = '2024-12-31'
        
        results = backtester.run(symbols, start_date, end_date)
        print("\n" + "=" * 50 + "\n")

if __name__ == "__main__":
    main() 