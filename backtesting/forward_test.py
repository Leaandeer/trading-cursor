import pandas as pd
import yfinance as yf
from typing import List, Dict
from datetime import datetime, timedelta

class ForwardTester:
    def __init__(self, initial_capital: float, risk_per_trade: float = 0.02):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.risk_per_trade = risk_per_trade
        self.open_positions = {}  # Track open positions
        
    def get_latest_data(self, symbol: str) -> pd.DataFrame:
        """Get latest data for analysis"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)  # Get 30 days of data
        
        try:
            df = yf.download(symbol, start=start_date, end=end_date)
            if df.empty:
                print(f"No data found for {symbol}")
                return None
                
            df['MA_10'] = df['Close'].rolling(window=10).mean()
            df['MA_20'] = df['Close'].rolling(window=20).mean()
            df['Price_Change'] = df['Close'].pct_change()
            df['RSI'] = self.calculate_rsi(df['Close'], period=14)
            
            return df
            
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            return None
    
    def check_for_signals(self, symbols: List[str]) -> Dict:
        """Check for entry and exit signals"""
        signals = {
            'entries': [],
            'exits': []
        }
        
        for symbol in symbols:
            df = self.get_latest_data(symbol)
            if df is None or len(df) < 20:
                continue
            
            latest = df.iloc[-1]
            
            # Check exit signals for open positions
            if symbol in self.open_positions:
                position = self.open_positions[symbol]
                
                # Check stops
                if latest['Low'] <= position['trailing_stop']:
                    signals['exits'].append({
                        'symbol': symbol,
                        'type': 'stop_loss',
                        'price': position['trailing_stop'],
                        'position': position
                    })
                
                # Check trend exit
                elif latest['Close'] < latest['MA_20']:
                    signals['exits'].append({
                        'symbol': symbol,
                        'type': 'trend_exit',
                        'price': latest['Close'],
                        'position': position
                    })
                
                # Update trailing stops
                else:
                    if latest['High'] > position['highest_price']:
                        position['highest_price'] = latest['High']
                        if latest['High'] >= position['entry'] * 1.03:
                            position['trailing_stop'] = max(position['entry'], position['trailing_stop'])
                        if latest['High'] >= position['entry'] * 1.05:
                            position['trailing_stop'] = max(latest['High'] * 0.97, position['trailing_stop'])
                        if latest['High'] >= position['entry'] * 1.10:
                            position['trailing_stop'] = max(latest['High'] * 0.95, position['trailing_stop'])
            
            # Check entry signals for non-positions
            else:
                trend_condition = (
                    latest['Close'] > latest['MA_10'] or
                    latest['Close'] > latest['MA_20']
                )
                
                pullback_condition = (
                    abs(latest['Close'] - latest['MA_10']) / latest['Close'] < 0.02 or
                    abs(latest['Close'] - latest['MA_20']) / latest['Close'] < 0.03
                )
                
                momentum_condition = (
                    latest['Price_Change'] > -0.02 or
                    latest['RSI'] < 40
                )
                
                conditions_met = sum([trend_condition, pullback_condition, momentum_condition])
                
                if conditions_met >= 2:
                    stop_loss = latest['Close'] * 0.98
                    position_size = self.calculate_position_size(latest['Close'], stop_loss)
                    
                    if position_size > 0:
                        signals['entries'].append({
                            'symbol': symbol,
                            'entry_price': latest['Close'],
                            'stop_loss': stop_loss,
                            'position_size': position_size
                        })
        
        return signals
    
    def print_daily_report(self, signals: Dict):
        """Print daily trading signals"""
        print("\nDaily Trading Report")
        print("===================")
        print(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
        print(f"Current Capital: ${self.capital:,.2f}")
        
        if signals['entries']:
            print("\nEntry Signals:")
            for entry in signals['entries']:
                print(f"\n{entry['symbol']}:")
                print(f"Entry Price: ${entry['entry_price']:.2f}")
                print(f"Position Size: {entry['position_size']} shares")
                print(f"Stop Loss: ${entry['stop_loss']:.2f}")
        
        if signals['exits']:
            print("\nExit Signals:")
            for exit in signals['exits']:
                print(f"\n{exit['symbol']}:")
                print(f"Exit Type: {exit['type']}")
                print(f"Exit Price: ${exit['price']:.2f}")
        
        if self.open_positions:
            print("\nOpen Positions:")
            for symbol, pos in self.open_positions.items():
                print(f"\n{symbol}:")
                print(f"Entry: ${pos['entry']:.2f}")
                print(f"Current Stop: ${pos['trailing_stop']:.2f}")
                print(f"Size: {pos['size']} shares") 