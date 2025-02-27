from backtesting.backtest import Backtester
import pandas as pd
from datetime import datetime, timedelta
import os
import numpy as np

# Define initial capital to a realistic value
INITIAL_CAPITAL = 1000  # $10,000 starting capital for more realistic position sizing

def create_summary_report(backtest_results, risk_level, initial_capital, final_capital, timestamp):
    """Create a detailed summary report with trade stats and metrics"""
    # Create results directory if it doesn't exist
    results_dir = "backtest_results"
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)
    
    # 1. Overall Performance Summary
    performance = {
        'Risk Level': [risk_level * 100],
        'Initial Capital': [initial_capital],
        'Final Capital': [final_capital],
        'Absolute Return': [final_capital - initial_capital],
        'Percent Return': [((final_capital - initial_capital) / initial_capital * 100)],
        'Total Trades': [sum(r['trades'] for r in backtest_results)],
        'Winning Trades': [sum(r['wins'] for r in backtest_results)],
        'Losing Trades': [sum(r['losses'] for r in backtest_results)],
        'Win Rate': [sum(r['wins'] for r in backtest_results) / sum(r['trades'] for r in backtest_results) * 100 if sum(r['trades'] for r in backtest_results) > 0 else 0],
        'Total Profit': [sum(r['profit'] for r in backtest_results)],
        'Timestamp': [timestamp]
    }
    
    # 2. Symbol-by-Symbol Performance
    symbol_data = []
    for result in backtest_results:
        symbol_data.append({
            'Symbol': result['symbol'],
            'Trades': result['trades'],
            'Wins': result.get('wins', 0),
            'Losses': result.get('losses', 0),
            'Win Rate (%)': result.get('win_rate', 0),
            'Profit ($)': result.get('profit', 0),
            'Avg Profit/Trade ($)': result.get('profit', 0) / result['trades'] if result['trades'] > 0 else 0
        })
    
    # 3. Save performance summary
    perf_df = pd.DataFrame(performance)
    perf_df.to_csv(f"{results_dir}/performance_summary_{timestamp}.csv", index=False)
    
    # 4. Save symbol performance
    symbol_df = pd.DataFrame(symbol_data)
    symbol_df.to_csv(f"{results_dir}/symbol_performance_{timestamp}.csv", index=False)
    
    print(f"\nPerformance summary saved to {results_dir}/performance_summary_{timestamp}.csv")
    print(f"Symbol performance saved to {results_dir}/symbol_performance_{timestamp}.csv")
    
    return perf_df, symbol_df

def analyze_trades_data(trades_file_path):
    """Analyze the trades data csv to extract useful insights"""
    if not os.path.exists(trades_file_path):
        print(f"Trades file not found: {trades_file_path}")
        return
    
    try:
        trades_df = pd.read_csv(trades_file_path)
        
        # Check if file is empty or has no data
        if trades_df.empty:
            print(f"No trades found in {trades_file_path}")
            return
        
        # Convert date columns to datetime
        trades_df['Entry Date'] = pd.to_datetime(trades_df['Entry Date'])
        trades_df['Exit Date'] = pd.to_datetime(trades_df['Exit Date'])
        
        # Calculate additional metrics
        trades_df['Is Winning'] = trades_df['Profit/Loss $'] > 0
        
        # Group by symbols
        symbol_stats = trades_df.groupby('Symbol').agg({
            'Profit/Loss $': ['sum', 'mean', 'count'],
            'Profit/Loss %': ['mean', 'min', 'max'],
            'Is Winning': 'mean',
            'Trade Duration': 'mean'
        }).reset_index()
        
        # Flatten the multi-level columns
        symbol_stats.columns = ['_'.join(col).strip('_') for col in symbol_stats.columns.values]
        symbol_stats.rename(columns={'Is_Winning_mean': 'Win_Rate'}, inplace=True)
        
        # Group by exit reason
        reason_stats = trades_df.groupby('Exit Reason').agg({
            'Profit/Loss $': ['sum', 'mean', 'count'],
            'Profit/Loss %': 'mean',
            'Is Winning': 'mean'
        }).reset_index()
        reason_stats.columns = ['_'.join(col).strip('_') for col in reason_stats.columns.values]
        reason_stats.rename(columns={'Is_Winning_mean': 'Win_Rate'}, inplace=True)
        
        # Calculate monthly performance
        trades_df['Month'] = trades_df['Exit Date'].dt.to_period('M')
        monthly_stats = trades_df.groupby('Month').agg({
            'Profit/Loss $': 'sum',
            'Is Winning': 'mean',
            'Symbol': 'count'
        }).reset_index()
        monthly_stats.rename(columns={'Symbol': 'Trade_Count', 'Is_Winning': 'Win_Rate'}, inplace=True)
        
        # Save analysis results
        results_dir = os.path.dirname(trades_file_path)
        base_name = os.path.splitext(os.path.basename(trades_file_path))[0]
        
        symbol_stats.to_csv(f"{results_dir}/{base_name}_symbol_analysis.csv", index=False)
        reason_stats.to_csv(f"{results_dir}/{base_name}_exit_reason_analysis.csv", index=False)
        monthly_stats.to_csv(f"{results_dir}/{base_name}_monthly_analysis.csv", index=False)
        
        print(f"\nAnalysis results saved to {results_dir}/{base_name}_*.csv")
        
        return symbol_stats, reason_stats, monthly_stats
    except Exception as e:
        print(f"Error analyzing trades data: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None

def main():
    """Run a comprehensive backtest with different risk levels"""
    print("BACKTESTING TRADING STRATEGY")
    print("============================")
    
    # Create timestamp for output files
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create results directory if it doesn't exist
    results_dir = "backtest_results"
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)
    
    # Define risk levels to test
    risk_levels = [0.03]  # Test 1%, 2%, and 3% risk per trade
    
    results = []
    trade_files = []
    
    for risk in risk_levels:
        print(f"\nTesting with {risk*100}% risk per trade")
        print("=" * 60)
        
        backtester = Backtester(
            initial_capital=INITIAL_CAPITAL,
            risk_per_trade=risk
        )
        
        # Use a comprehensive set of symbols for more data points
        symbols = ['AAPL', 'MSFT', 'GOOG', 'TSLA', 'NVDA', 'META', 'AMZN', 'NFLX', 
                  'AMD', 'INTC', 'V', 'JPM', 'DIS', 'KO', 'JNJ', 'PG']

        # Use real historical data
        end_date = datetime.now() - timedelta(days=1)  # Yesterday
        start_date = end_date - timedelta(days=365)    # One year of data
        
        # Format dates as strings
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')
        
        print(f"Backtesting from {start_date_str} to {end_date_str}")
        
        backtest_results = backtester.run(symbols, start_date_str, end_date_str)
        
        # Create detailed summary reports
        perf_df, symbol_df = create_summary_report(
            backtest_results,
            risk,
            INITIAL_CAPITAL,
            backtester.capital,
            timestamp
        )
        
        # Store the last trades file for analysis
        for file in os.listdir():
            if file.startswith('trades_report_') and file.endswith('.csv'):
                # Move the file to results directory with risk level in the name
                new_file = f"{results_dir}/trades_report_{risk*100:.0f}pct_risk_{timestamp}.csv"
                os.rename(file, new_file)
                trade_files.append(new_file)
                break
        
        # Store summary for comparison
        results.append({
            'Risk Level (%)': risk * 100,
            'Final Capital ($)': backtester.capital,
            'Return (%)': ((backtester.capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100),
            'Total Trades': sum(r['trades'] for r in backtest_results),
            'Win Rate (%)': sum(r['wins'] for r in backtest_results) / sum(r['trades'] for r in backtest_results) * 100 if sum(r['trades'] for r in backtest_results) > 0 else 0,
            'Average Trade ($)': sum(r['profit'] for r in backtest_results) / sum(r['trades'] for r in backtest_results) if sum(r['trades'] for r in backtest_results) > 0 else 0
        })
        
        print("\n" + "=" * 60 + "\n")
    
    # Compare results from different risk levels
    print("\nRISK LEVEL COMPARISON")
    print("=" * 80)
    
    # Convert to DataFrame for better display
    results_df = pd.DataFrame(results)
    print(results_df.to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    
    # Save complete results to CSV
    results_df.to_csv(f"{results_dir}/risk_comparison_{timestamp}.csv", index=False)
    print(f"\nRisk comparison saved to {results_dir}/risk_comparison_{timestamp}.csv")
    
    # Analyze the trade data for each risk level
    for trade_file in trade_files:
        analyze_trades_data(trade_file)
    
    print("\nAnalysis completed successfully - All data saved to CSV files")

if __name__ == "__main__":
    main() 