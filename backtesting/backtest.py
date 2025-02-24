import pandas as pd
import yfinance as yf
from typing import List, Dict

class Backtester:
    def __init__(self, initial_capital: float, risk_per_trade: float = 0.02):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.risk_per_trade = risk_per_trade  # 0.02 = 2% risk per trade
    
    def calculate_position_size(self, entry_price: float, stop_loss: float) -> int:
        """Calculate position size based on risk percentage and available capital"""
        risk_amount = self.capital * self.risk_per_trade  # How much money we're willing to risk
        risk_per_share = entry_price - stop_loss  # How much we risk per share
        
        # Calculate position size based on risk
        position_size = int(risk_amount / risk_per_share)
        
        # Check if we have enough capital
        total_cost = position_size * entry_price
        if total_cost > self.capital:
            # If not enough capital, calculate max shares we can buy
            position_size = int(self.capital / entry_price)
            print(f"Warning: Position size reduced due to capital constraints")
            print(f"Available capital: ${self.capital:,.2f}")
        
        # Ensure at least 1 share if we have enough capital
        if position_size < 1 and self.capital >= entry_price:
            position_size = 1
        
        # Final check if we can afford even 1 share
        if entry_price > self.capital:
            print(f"Warning: Not enough capital for even 1 share")
            position_size = 0
            
        return position_size
    
    def fetch_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Fetch and prepare data with shorter-term indicators"""
        try:
            df = yf.download(symbol, start=start_date, end=end_date)
            if df.empty:
                print(f"No data found for {symbol}")
                return None
                
            # Add shorter-term moving averages for more signals
            df['MA_20'] = df['Close'].rolling(window=20).mean()
            df['MA_50'] = df['Close'].rolling(window=50).mean()
            df['Price_Change'] = df['Close'].pct_change()
            
            return df
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            return None
    
    def run_single_symbol(self, symbol: str, start_date: str, end_date: str) -> Dict:
        """Run backtest with trailing stop loss and position sizing"""
        print(f"Testing {symbol}...")
        
        df = self.fetch_data(symbol, start_date, end_date)
        if df is None:
            return {"symbol": symbol, "profit": 0, "trades": 0}
        
        position = None
        position_size = 0
        trades = 0
        total_profit = 0
        trailing_stop = None
        highest_price = None
        
        for i in range(50, len(df)):
            current_price = float(df['Close'].iloc[i])
            current_low = float(df['Low'].iloc[i])
            current_high = float(df['High'].iloc[i])
            current_ma20 = float(df['MA_20'].iloc[i])
            current_ma50 = float(df['MA_50'].iloc[i])
            price_change = float(df['Price_Change'].iloc[i])
            
            # Entry conditions
            if position is None:
                trend_up = current_price > current_ma50
                pullback = abs(current_price - current_ma20) / current_price < 0.01
                momentum_positive = price_change > -0.01
                
                if trend_up and (pullback or momentum_positive):
                    position = current_price
                    trailing_stop = position * 0.98  # Initial 2% stop loss
                    
                    # Calculate position size based on risk
                    position_size = self.calculate_position_size(position, trailing_stop)
                    
                    highest_price = position
                    trades += 1
                    print(f"\nBuy {symbol}:")
                    print(f"Price: ${position:.2f}")
                    print(f"Position Size: {position_size} shares (${position_size * position:,.2f})")
                    print(f"Initial Stop Loss: ${trailing_stop:.2f}")
                    print(f"Risk per share: ${position - trailing_stop:.2f}")
                    print(f"Total risk: ${(position - trailing_stop) * position_size:.2f} ({self.risk_per_trade*100:.1f}% of capital)")
            
            # Position management
            elif position is not None:
                # First check if stop was hit
                if current_low <= trailing_stop:
                    exit_price = trailing_stop
                    profit = (exit_price - position) * position_size
                    profit_percentage = (exit_price - position) / position * 100
                    total_profit += profit
                    self.capital += profit  # Update capital
                    
                    print(f"\nSell {symbol} (Trailing Stop):")
                    print(f"Exit Price: ${exit_price:.2f}")
                    print(f"Profit/Loss: ${profit:.2f} ({profit_percentage:.1f}%)")
                    print(f"Updated Capital: ${self.capital:,.2f}")
                    
                    position = None
                    position_size = 0
                    trailing_stop = None
                    highest_price = None
                    continue
                
                # Update highest price and trailing stop
                if current_high > highest_price:
                    highest_price = current_high
                    # Update trailing stop to lock in profits
                    if current_high >= position * 1.03:  # Up 3%
                        trailing_stop = max(position, trailing_stop)
                    if current_high >= position * 1.05:  # Up 5%
                        trailing_stop = max(current_high * 0.97, trailing_stop)
                    if current_high >= position * 1.10:  # Up 10%
                        trailing_stop = max(current_high * 0.95, trailing_stop)
                
                # Check trend exit
                if current_price < current_ma50:
                    profit = (current_price - position) * position_size
                    profit_percentage = (current_price - position) / position * 100
                    total_profit += profit
                    self.capital += profit  # Update capital
                    
                    print(f"\nSell {symbol} (Trend Exit):")
                    print(f"Exit Price: ${current_price:.2f}")
                    print(f"Profit/Loss: ${profit:.2f} ({profit_percentage:.1f}%)")
                    print(f"Updated Capital: ${self.capital:,.2f}")
                    
                    position = None
                    position_size = 0
                    trailing_stop = None
                    highest_price = None
        
        return {
            "symbol": symbol,
            "profit": total_profit,
            "trades": trades,
            "final_capital": self.capital
        }
    
    def run(self, symbols: List[str], start_date: str, end_date: str):
        """Run backtest for multiple symbols with comprehensive summary"""
        results = []
        total_profit = 0
        total_trades = 0
        winning_trades = 0
        losing_trades = 0
        
        print("\nRunning backtest...")
        print(f"Initial Capital: ${self.initial_capital:,.2f}")
        print("-------------------")
        
        for symbol in symbols:
            result = self.run_single_symbol(symbol, start_date, end_date)
            results.append(result)
            
            total_profit += result['profit']
            total_trades += result['trades']
            
            print(f"\nResults for {symbol}:")
            print(f"Total profit: ${result['profit']:,.2f}")
            print(f"Number of trades: {result['trades']}")
            if result['trades'] > 0:
                print(f"Average profit per trade: ${result['profit']/result['trades']:,.2f}")
            print("-------------------")
        
        print("\nFINAL BACKTEST RESULTS")
        print("======================")
        print(f"Initial Capital: ${self.initial_capital:,.2f}")
        print(f"Final Capital: ${self.capital:,.2f}")
        print(f"Total Return: {((self.capital - self.initial_capital) / self.initial_capital * 100):,.2f}%")
        print(f"Total Profit/Loss: ${total_profit:,.2f}")
        print(f"Total Number of Trades: {total_trades}")
        if total_trades > 0:
            print(f"Average Profit per Trade: ${total_profit/total_trades:,.2f}")
        print("======================")
        
        return results 