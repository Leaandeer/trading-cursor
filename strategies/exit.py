from dataclasses import dataclass
from typing import Optional, Tuple
import pandas as pd
import numpy as np

@dataclass
class ExitSignal:
    symbol: str
    exit_type: str  # 'stop_loss', 'take_profit', or 'technical'
    exit_price: float

class ExitStrategy:
    def __init__(self, config: 'TradingConfig'):
        self.config = config
    
    def update_trailing_stop(self, df: pd.DataFrame, current_stop: float) -> float:
        """Update trailing stop based on ATR"""
        latest = df.iloc[-1]
        atr_stop = latest['close'] - (latest['ATR'] * 2)
        return max(current_stop, atr_stop)
    
    def check_exit_signal(
        self, 
        df: pd.DataFrame, 
        entry_price: float,
        stop_loss: float,
        take_profit: float
    ) -> Optional[ExitSignal]:
        """
        Check if any exit conditions are met
        Returns None if no exit signal is found
        """
        if len(df) < 2:
            return None
            
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        symbol = df.index[-1]
        
        # Check stop loss
        if latest['low'] <= stop_loss:
            return ExitSignal(symbol=symbol, exit_type='stop_loss', exit_price=stop_loss)
        
        # Check take profit
        if latest['high'] >= take_profit:
            return ExitSignal(symbol=symbol, exit_type='take_profit', exit_price=take_profit)
        
        # Check technical exit conditions
        if (
            # MACD bearish crossover
            prev['MACD'] > prev['MACD_Signal'] and
            latest['MACD'] < latest['MACD_Signal'] and
            # RSI overbought
            latest['RSI'] > self.config.RSI_OVERBOUGHT
        ):
            return ExitSignal(symbol=symbol, exit_type='technical', exit_price=latest['close'])
        
        return None 