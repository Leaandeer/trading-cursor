from trading.live_trader import LiveTrader
import os
from dotenv import load_dotenv

def main():
    # Load environment variables
    load_dotenv()
    
    # Get API credentials from environment variables
    API_KEY = os.getenv('ALPACA_API_KEY')
    API_SECRET = os.getenv('ALPACA_API_SECRET')
    BASE_URL = 'https://paper-api.alpaca.markets'  # Paper trading URL
    
    if not API_KEY or not API_SECRET:
        raise ValueError("Please set ALPACA_API_KEY and ALPACA_API_SECRET in your .env file")
    
    trader = LiveTrader(
        api_key=API_KEY,
        api_secret=API_SECRET,
        base_url=BASE_URL,
        risk_per_trade=0.02  # Risk 2% per trade
    )
    
    symbols = ['AAPL', 'MSFT', 'GOOG', 'TSLA', 'NVDA', 'META', 'AMZN', 'NFLX']
    
    trader.run(symbols)

if __name__ == "__main__":
    main() 