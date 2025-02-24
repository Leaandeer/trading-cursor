from dataclasses import dataclass
from typing import Dict

@dataclass
class AlpacaConfig:
    API_KEY: str
    API_SECRET: str
    BASE_URL: str = "https://paper-api.alpaca.markets/v2"  # Paper trading by default
    DATA_URL: str = "https://data.alpaca.markets"

@dataclass
class TradingConfig:
    RISK_PER_TRADE: float = 0.02  # 2% risk per trade
    MAX_DAILY_DRAWDOWN: float = 0.10  # 10% max daily drawdown
    MIN_VOLUME: int = 500000  # Minimum average daily volume
    MIN_PRICE: float = 10.0  # Minimum stock price
    MAX_PRICE: float = 500.0  # Maximum stock price
    
    # Technical indicators parameters
    MA_FAST: int = 50  # 50-day moving average
    MA_SLOW: int = 200  # 200-day moving average
    RSI_PERIOD: int = 14
    RSI_OVERSOLD: int = 40
    RSI_OVERBOUGHT: int = 60
    MACD_FAST: int = 12
    MACD_SLOW: int = 26
    MACD_SIGNAL: int = 9
    ATR_PERIOD: int = 14

    # Fibonacci levels
    FIB_LEVELS: Dict[str, float] = {
        "0.382": 0.382,
        "0.618": 0.618,
        "1.000": 1.000,
        "1.618": 1.618
    } 