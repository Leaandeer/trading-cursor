from typing import List
import pandas as pd
import alpaca_trade_api as tradeapi
from utils.indicators import TechnicalIndicators

class StockScanner:
    def __init__(self, alpaca_api: tradeapi.REST, config: 'TradingConfig'):
        self.api = alpaca_api
        self.config = config
        self.indicators = TechnicalIndicators()
    
    def get_tradeable_stocks(self) -> List[str]:
        """
        Fetch and filter stocks based on volume, price, and trend criteria
        """
        assets = self.api.list_assets(status='active')
        tradeable_stocks = []
        
        for asset in assets:
            if not asset.tradable or asset.status != 'active':
                continue
                
            # Get historical data
            bars = self.api.get_bars(
                asset.symbol,
                timeframe='1D',
                start=(pd.Timestamp.now() - pd.Timedelta(days=220)).isoformat(),
                end=pd.Timestamp.now().isoformat()
            ).df
            
            if len(bars) < 200:  # Need at least 200 days of data
                continue
                
            # Calculate indicators
            bars = self.indicators.add_all_indicators(bars)
            
            # Check trading criteria
            latest = bars.iloc[-1]
            if (
                latest['volume'] >= self.config.MIN_VOLUME and
                self.config.MIN_PRICE <= latest['close'] <= self.config.MAX_PRICE and
                latest['close'] > latest[f'MA_{self.config.MA_FAST}'] > latest[f'MA_{self.config.MA_SLOW}']
            ):
                tradeable_stocks.append(asset.symbol)
                
        return tradeable_stocks 