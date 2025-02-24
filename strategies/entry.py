from dataclasses import dataclass
from typing import Optional, Tuple
import pandas as pd
import numpy as np
from utils.indicators import TechnicalIndicators

@dataclass
class EntrySignal:
    symbol: str
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: int

class EntryStrategy:
    def __init__(self, config: 'TradingConfig'):
        self.config = config
        self.indicators = TechnicalIndicators()
    
    def check_pullback(self, df: pd.DataFrame) -> bool:
        """Check if price is pulling back to MA or Fibonacci levels"""
        latest = df.iloc[-1]
        ma_50 = latest[f'MA_{self.config.MA_FAST}']
        close = latest['close']
        
        # Check if price is near MA_50 (within 2% range)
        ma_proximity = abs(close - ma_50) / ma_50 <= 0.02
        
        # Calculate distance from recent swing high
        high_point = df['high'][-20:].max()
        retracement = (high_point - close) / (high_point - df['low'][-20:].min())
        
        # Check if retracement is near Fibonacci levels (within 2% range)
        fib_proximity = any(
            abs(retracement - fib_level) <= 0.02 
            for fib_level in self.config.FIB_LEVELS.values()
        )
        
        return ma_proximity or fib_proximity
    
    def check_confirmation(self, df: pd.DataFrame) -> bool:
        """Check for entry confirmation using RSI and MACD"""
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # RSI conditions
        rsi_oversold = self.config.RSI_OVERSOLD <= latest['RSI'] <= self.config.RSI_OVERBOUGHT
        
        # MACD crossover
        macd_crossover = (
            prev['MACD'] < prev['MACD_Signal'] and 
            latest['MACD'] > latest['MACD_Signal']
        )
        
        return rsi_oversold and macd_crossover
    
    def calculate_stop_loss(self, df: pd.DataFrame) -> float:
        """Calculate stop loss based on recent swing low and ATR"""
        latest = df.iloc[-1]
        swing_low = df['low'][-20:].min()
        atr_stop = latest['close'] - (latest['ATR'] * 2)
        return max(swing_low, atr_stop)
    
    def calculate_take_profit(self, entry_price: float, stop_loss: float) -> float:
        """Calculate take profit based on risk:reward ratio"""
        risk = entry_price - stop_loss
        return entry_price + (risk * 2)  # 1:2 risk:reward ratio
    
    def find_entry_signal(self, symbol: str, df: pd.DataFrame, available_capital: float) -> Optional[EntrySignal]:
        """
        Analyze price action and indicators to generate entry signals
        Returns None if no valid entry signal is found
        """
        if len(df) < 200:
            return None
            
        df = self.indicators.add_all_indicators(df)
        latest = df.iloc[-1]
        
        # Check if stock is in uptrend
        if not (latest['close'] > latest[f'MA_{self.config.MA_FAST}'] > latest[f'MA_{self.config.MA_SLOW}']):
            return None
        
        # Check for valid entry conditions
        if not (self.check_pullback(df) and self.check_confirmation(df)):
            return None
        
        entry_price = latest['close']
        stop_loss = self.calculate_stop_loss(df)
        take_profit = self.calculate_take_profit(entry_price, stop_loss)
        
        # Calculate position size based on risk management
        risk_amount = available_capital * self.config.RISK_PER_TRADE
        risk_per_share = entry_price - stop_loss
        position_size = int(risk_amount / risk_per_share)
        
        return EntrySignal(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size
        ) 