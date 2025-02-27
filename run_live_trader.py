from trading.live_trader import LiveTrader
import os
import sys
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dotenv import load_dotenv
import time
import json
import traceback

def create_trading_report(trades, risk_level, timestamp):
    """Create a detailed trading report similar to backtest reports"""
    # Create results directory if it doesn't exist
    results_dir = "trading_results"
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)
    
    if not trades:
        print("No trades to report")
        return None
    
    # Convert trades list to DataFrame
    trades_df = pd.DataFrame(trades)
    
    # Save complete trade data
    trades_file = f"{results_dir}/live_trades_{timestamp}.csv"
    trades_df.to_csv(trades_file, index=False)
    print(f"Trade data saved to {trades_file}")
    
    # Create performance summary
    if not trades_df.empty:
        # Calculate performance metrics
        winning_trades = trades_df[trades_df['profit'] > 0]
        win_rate = len(winning_trades) / len(trades_df) * 100 if len(trades_df) > 0 else 0
        
        summary = {
            'Risk Level (%)': [risk_level * 100],
            'Start Time': [trades_df['entry_time'].min() if 'entry_time' in trades_df.columns else 'N/A'],
            'End Time': [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            'Total Trades': [len(trades_df)],
            'Winning Trades': [len(winning_trades)],
            'Losing Trades': [len(trades_df) - len(winning_trades)],
            'Win Rate (%)': [win_rate],
            'Total Profit ($)': [trades_df['profit'].sum()],
            'Average Trade ($)': [trades_df['profit'].mean()],
            'Largest Win ($)': [trades_df['profit'].max()],
            'Largest Loss ($)': [trades_df['profit'].min()],
        }
        
        # Save summary
        summary_df = pd.DataFrame(summary)
        summary_file = f"{results_dir}/performance_summary_{timestamp}.csv"
        summary_df.to_csv(summary_file, index=False)
        print(f"Performance summary saved to {summary_file}")
        
        # Symbol performance
        if 'symbol' in trades_df.columns:
            symbol_stats = trades_df.groupby('symbol').agg({
                'profit': ['sum', 'mean', 'count'],
            }).reset_index()
            
            # Flatten the multi-level columns
            symbol_stats.columns = ['_'.join(col).strip('_') for col in symbol_stats.columns.values]
            
            # Add win rate per symbol
            symbol_win_rates = []
            for symbol in symbol_stats['symbol']:
                symbol_trades = trades_df[trades_df['symbol'] == symbol]
                symbol_wins = len(symbol_trades[symbol_trades['profit'] > 0])
                win_rate = symbol_wins / len(symbol_trades) * 100 if len(symbol_trades) > 0 else 0
                symbol_win_rates.append(win_rate)
            
            symbol_stats['win_rate'] = symbol_win_rates
            
            # Save symbol performance
            symbol_file = f"{results_dir}/symbol_performance_{timestamp}.csv"
            symbol_stats.to_csv(symbol_file, index=False)
            print(f"Symbol performance saved to {symbol_file}")
    
    return trades_file

def monitor_trader_status(trader, stop_event=None):
    """Periodically check trader status and write to status file"""
    try:
        status_dir = "trading_status"
        if not os.path.exists(status_dir):
            os.makedirs(status_dir)
            
        status_file = f"{status_dir}/status_{datetime.now().strftime('%Y%m%d')}.json"
        
        while True:
            if stop_event and stop_event.is_set():
                break
                
            # Get current status
            status = trader.get_current_status()
            
            # Add timestamp
            status['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Write to file (append)
            with open(status_file, 'a') as f:
                f.write(json.dumps(status) + '\n')
                
            # Sleep for 5 minutes
            time.sleep(300)
            
    except Exception as e:
        print(f"Error in status monitoring: {e}")
        traceback.print_exc()

def main():
    """
    Main function to run the live trading bot with configurable parameters
    via command line arguments, optimized for server operation.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Run live trading bot with Alpaca API')
    parser.add_argument('--risk', type=float, default=0.02, 
                        help='Risk per trade (default: 0.02 = 2%%)')
    parser.add_argument('--paper', action='store_true', 
                        help='Use paper trading (default)')
    parser.add_argument('--live', action='store_true', 
                        help='Use live trading (use with caution!)')
    parser.add_argument('--symbols', type=str, 
                        default='AAPL,MSFT,GOOG,TSLA,NVDA,META,AMZN,NFLX',
                        help='Comma-separated list of symbols to monitor')
    parser.add_argument('--duration', type=int, default=0,
                        help='Trading duration in hours (0 = run until manually stopped)')
    parser.add_argument('--server', action='store_true',
                        help='Run in server mode (reduced output, more logging)')
    args = parser.parse_args()
    
    # Create timestamp for this run
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Load environment variables
    load_dotenv()
    
    # Get API credentials from environment variables
    API_KEY = os.getenv('ALPACA_API_KEY')
    API_SECRET = os.getenv('ALPACA_API_SECRET')
    
    # Validate API credentials
    if not API_KEY or not API_SECRET:
        print("ERROR: Please set ALPACA_API_KEY and ALPACA_API_SECRET in your .env file")
        sys.exit(1)
    
    # Set the base URL based on paper/live setting
    if args.live:
        if args.paper:
            print("ERROR: Cannot specify both --paper and --live. Using paper trading.")
            BASE_URL = 'https://paper-api.alpaca.markets'
        else:
            # Extra safety check for live trading
            if not args.server:  # Skip confirmation in server mode
                confirm = input("\n*** WARNING: You are about to use LIVE TRADING with REAL MONEY! ***\n"
                               "Type 'CONFIRM' to proceed or anything else to abort: ")
                if confirm != 'CONFIRM':
                    print("Aborting live trading.")
                    sys.exit(0)
                    
            BASE_URL = 'https://api.alpaca.markets'
            print("\n*** LIVE TRADING MODE ACTIVATED - USING REAL MONEY ***\n")
    else:
        # Default to paper trading
        BASE_URL = 'https://paper-api.alpaca.markets'
        print("\nUsing PAPER TRADING mode (simulated trading, no real money)\n")
    
    # Parse symbols list
    symbols = [s.strip() for s in args.symbols.split(',')]
    
    # Print configuration summary
    print("\n===== TRADING BOT CONFIGURATION =====")
    print(f"Mode: {'LIVE TRADING' if args.live and not args.paper else 'PAPER TRADING'}")
    print(f"Risk per trade: {args.risk * 100}%")
    print(f"Monitoring {len(symbols)} symbols: {', '.join(symbols)}")
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if args.duration > 0:
        end_time = datetime.now() + timedelta(hours=args.duration)
        print(f"Scheduled end time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Running in {'server' if args.server else 'interactive'} mode")
    print("=====================================\n")
    
    # Set up log directory
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    try:
        # Initialize trader
        trader = LiveTrader(
            api_key=API_KEY,
            api_secret=API_SECRET,
            base_url=BASE_URL,
            risk_per_trade=args.risk
        )
        
        # Start status monitoring in server mode
        if args.server:
            import threading
            stop_event = threading.Event()
            status_thread = threading.Thread(
                target=monitor_trader_status,
                args=(trader, stop_event)
            )
            status_thread.daemon = True
            status_thread.start()
        
        # Set up end time if duration specified
        end_time = None
        if args.duration > 0:
            end_time = datetime.now() + timedelta(hours=args.duration)
            print(f"\nTrading will run until: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Run the trading bot
        trades = trader.run(symbols)
        
        # Generate reports at the end
        if trades:
            create_trading_report(trades, args.risk, timestamp)
        
        # Stop status monitoring if running
        if args.server and 'stop_event' in locals():
            stop_event.set()
            status_thread.join(timeout=5)
        
        # Generate end-of-day summary
        if hasattr(trader, 'generate_daily_summary'):
            summary = trader.generate_daily_summary()
            print("\n" + summary)
            
            # Save summary to file
            with open(f"logs/trading_summary_{timestamp}.txt", "w") as f:
                f.write(summary)
        
    except KeyboardInterrupt:
        print("\nTrading bot manually stopped by user")
        
        # Save any collected trade data
        if 'trader' in locals() and hasattr(trader, 'completed_trades'):
            create_trading_report(trader.completed_trades, args.risk, timestamp)
            
        # Stop status monitoring if running
        if args.server and 'stop_event' in locals():
            stop_event.set()
            status_thread.join(timeout=5)
            
    except Exception as e:
        print(f"\nCritical error: {e}")
        print("Trading bot stopped due to error")
        
        # Log detailed error information
        error_log = f"logs/error_{timestamp}.txt"
        with open(error_log, "w") as f:
            f.write(f"Error occurred at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Error message: {str(e)}\n\n")
            f.write("Traceback:\n")
            traceback.print_exc(file=f)
            
        print(f"Error details saved to {error_log}")
        
        # Try to save any trade data if available
        if 'trader' in locals() and hasattr(trader, 'completed_trades'):
            create_trading_report(trader.completed_trades, args.risk, timestamp)
            
        sys.exit(1)

if __name__ == "__main__":
    main()