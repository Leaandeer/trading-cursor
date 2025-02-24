from typing import Dict, Optional
import pandas as pd

class RiskManager:
    def __init__(self, config: 'TradingConfig'):
        self.config = config
        self.daily_pl = 0
        self.positions: Dict[str, Dict] = {}
    
    def can_open_position(self, portfolio_value: float, risk_per_share: float, price: float) -> Optional[int]:
        """
        Determine if a new position can be opened and calculate its size
        Returns position size if trade is allowed, None otherwise
        """
        # Check daily drawdown limit
        if self.daily_pl <= -portfolio_value * self.config.MAX_DAILY_DRAWDOWN:
            return None
        
        # Calculate maximum position size based on risk per trade
        risk_amount = portfolio_value * self.config.RISK_PER_TRADE
        max_shares = int(risk_amount / risk_per_share)
        
        # Ensure minimum position size
        if max_shares * price < 1000:  # Minimum $1000 position
            return None
            
        return max_shares
    
    def update_daily_pl(self, pl: float) -> None:
        """Update daily profit/loss"""
        self.daily_pl += pl
    
    def reset_daily_pl(self) -> None:
        """Reset daily profit/loss (call at market open)"""
        self.daily_pl = 0
    
    def add_position(self, symbol: str, entry_price: float, stop_loss: float, 
                    take_profit: float, size: int) -> None:
        """Track new position"""
        self.positions[symbol] = {
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'size': size
        }
    
    def remove_position(self, symbol: str) -> None:
        """Remove closed position"""
        if symbol in self.positions:
            del self.positions[symbol] 