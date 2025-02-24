import pandas as pd
import yfinance as yf
from typing import List, Dict
from datetime import datetime, timedelta

class Backtester:
    def __init__(self, initial_capital: float, risk_per_trade: float = 0.02):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.risk_per_trade = risk_per_trade
    
    def calculate_position_size(self, entry_price: float, stop_loss: float) -> int:
        """Calculate position size based on risk percentage and available capital"""
        risk_amount = self.capital * self.risk_per_trade
        risk_per_share = entry_price - stop_loss
        
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
            # Fetch extra data to properly calculate indicators
            start_dt = datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=60)
            
            df = yf.download(symbol, start=start_dt, end=end_date)
            if df.empty:
                print(f"No data found for {symbol}")
                return None
                
            # Use shorter MAs for shorter timeframes
            df['MA_10'] = df['Close'].rolling(window=10).mean()
            df['MA_20'] = df['Close'].rolling(window=20).mean()
            df['Price_Change'] = df['Close'].pct_change()
            df['RSI'] = self.calculate_rsi(df['Close'], period=14)
            
            # Only return the requested date range
            return df[start_date:]
            
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            return None
    
    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def run_single_symbol(self, symbol: str, start_date: str, end_date: str) -> Dict:
        """Run backtest with more frequent entry signals"""
        print(f"Testing {symbol}...")
        
        df = self.fetch_data(symbol, start_date, end_date)
        if df is None or len(df) < 10:  # Require at least 10 days of data
            return {"symbol": symbol, "profit": 0, "trades": 0}
        
        position = None
        position_size = 0
        trades = 0
        total_profit = 0
        trailing_stop = None
        highest_price = None
        
        # Start after 10 bars instead of 50
        for i in range(10, len(df)):
            current_price = float(df['Close'].iloc[i])
            current_low = float(df['Low'].iloc[i])
            current_high = float(df['High'].iloc[i])
            current_ma10 = float(df['MA_10'].iloc[i])
            current_ma20 = float(df['MA_20'].iloc[i])
            price_change = float(df['Price_Change'].iloc[i])
            current_rsi = float(df['RSI'].iloc[i])
            
            # Entry conditions - More suitable for shorter timeframes
            if position is None:
                trend_condition = (
                    current_price > current_ma10 or  # Price above 10 MA
                    current_price > current_ma20     # OR price above 20 MA
                )
                
                pullback_condition = (
                    abs(current_price - current_ma10) / current_price < 0.02 or  # Within 2% of 10 MA
                    abs(current_price - current_ma20) / current_price < 0.03     # OR within 3% of 20 MA
                )
                
                momentum_condition = (
                    price_change > -0.02 or  # Allow more negative momentum
                    current_rsi < 40         # OR oversold condition
                )
                
                conditions_met = sum([trend_condition, pullback_condition, momentum_condition])
                
                if conditions_met >= 2:
                    position = current_price
                    trailing_stop = position * 0.98  # Keep 2% initial stop
                    
                    position_size = self.calculate_position_size(position, trailing_stop)
                    
                    if position_size > 0:  # Only take trade if we can size properly
                        highest_price = position
                        trades += 1
                        print(f"\nBuy {symbol}:")
                        print(f"Price: ${position:.2f}")
                        print(f"Position Size: {position_size} shares (${position_size * position:,.2f})")
                        print(f"Initial Stop Loss: ${trailing_stop:.2f}")
                    else:
                        position = None
                        trailing_stop = None
            
            # Position management - now using shorter MA for trend exit
            elif position is not None:
                # Check stops
                if current_low <= trailing_stop:
                    exit_price = trailing_stop
                    profit = (exit_price - position) * position_size
                    profit_percentage = (exit_price - position) / position * 100
                    total_profit += profit
                    self.capital += profit
                    
                    print(f"\nSell {symbol} (Trailing Stop):")
                    print(f"Exit Price: ${exit_price:.2f}")
                    print(f"Profit/Loss: ${profit:.2f} ({profit_percentage:.1f}%)")
                    print(f"Updated Capital: ${self.capital:,.2f}")
                    
                    position = None
                    position_size = 0
                    trailing_stop = None
                    highest_price = None
                    continue
                
                # Update trailing stops
                if current_high > highest_price:
                    highest_price = current_high
                    if current_high >= position * 1.03:
                        trailing_stop = max(position, trailing_stop)
                    if current_high >= position * 1.05:
                        trailing_stop = max(current_high * 0.97, trailing_stop)
                    if current_high >= position * 1.10:
                        trailing_stop = max(current_high * 0.95, trailing_stop)
                
                # Trend exit now uses 20 MA instead of 50 MA
                if current_price < current_ma20:  # Changed from MA_50 to MA_20
                    profit = (current_price - position) * position_size
                    profit_percentage = (current_price - position) / position * 100
                    total_profit += profit
                    self.capital += profit
                    
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
        """Run backtest for multiple symbols"""
        results = []
        total_profit = 0
        total_trades = 0
        
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