from backtesting.forward_test import ForwardTester

def main():
    tester = ForwardTester(initial_capital=5000)
    
    symbols = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'META']
    
    # Run daily
    signals = tester.check_for_signals(symbols)
    tester.print_daily_report(signals)

if __name__ == "__main__":
    main() 