import logging
import time
from datetime import datetime, timedelta
import alpaca_trade_api as tradeapi
import pandas as pd
from dotenv import load_dotenv
import os

from config.config import AlpacaConfig, TradingConfig
from models.stock_scanner import StockScanner
from strategies.entry import EntryStrategy
from strategies.exit import ExitStrategy
from utils.risk_manager import RiskManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Load environment variables
load_dotenv()

class SwingTrader:
    def __init__(self, alpaca_config: AlpacaConfig, trading_config: TradingConfig):
        self.api = tradeapi.REST(
            alpaca_config.API_KEY,
            alpaca_config.API_SECRET,
            base_url=alpaca_config.BASE_URL
        )
        self.trading_config = trading_config
        
        # Initialize components
        self.scanner = StockScanner(self.api, trading_config)
        self.entry_strategy = EntryStrategy(trading_config)
        self.exit_strategy = ExitStrategy(trading_config)
        self.risk_manager = RiskManager(trading_config)
        
    def get_historical_data(self, symbol: str, days: int = 200) -> pd.DataFrame:
        """Fetch historical data for analysis"""
        try:
            bars = self.api.get_bars(
                symbol,
                timeframe='1D',
                start=(datetime.now() - timedelta(days=days)).isoformat(),
                end=datetime.now().isoformat()
            ).df
            return bars
        except Exception as e:
            logging.error(f"Error fetching data for {symbol}: {str(e)}")
            return pd.DataFrame()

    def execute_entry(self, signal) -> bool:
        """Execute entry order"""
        try:
            self.api.submit_order(
                symbol=signal.symbol,
                qty=signal.position_size,
                side='buy',
                type='limit',
                time_in_force='day',
                limit_price=signal.entry_price
            )
            
            self.risk_manager.add_position(
                symbol=signal.symbol,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                size=signal.position_size
            )
            
            logging.info(f"Entry order submitted for {signal.symbol}")
            return True
            
        except Exception as e:
            logging.error(f"Entry order failed for {signal.symbol}: {str(e)}")
            return False

    def execute_exit(self, signal) -> bool:
        """Execute exit order"""
        try:
            position = self.risk_manager.positions.get(signal.symbol)
            if not position:
                return False
                
            self.api.submit_order(
                symbol=signal.symbol,
                qty=position['size'],
                side='sell',
                type='limit',
                time_in_force='day',
                limit_price=signal.exit_price
            )
            
            self.risk_manager.remove_position(signal.symbol)
            logging.info(f"Exit order submitted for {signal.symbol} - Type: {signal.exit_type}")
            return True
            
        except Exception as e:
            logging.error(f"Exit order failed for {signal.symbol}: {str(e)}")
            return False

    def manage_positions(self):
        """Monitor and manage existing positions"""
        account = self.api.get_account()
        
        for symbol in list(self.risk_manager.positions.keys()):
            position = self.risk_manager.positions[symbol]
            bars = self.get_historical_data(symbol, days=5)  # Recent data is enough
            
            if bars.empty:
                continue
                
            exit_signal = self.exit_strategy.check_exit_signal(
                bars,
                position['entry_price'],
                position['stop_loss'],
                position['take_profit']
            )
            
            if exit_signal:
                self.execute_exit(exit_signal)

    def find_new_entries(self):
        """Scan for new entry opportunities"""
        account = self.api.get_account()
        portfolio_value = float(account.portfolio_value)
        
        tradeable_stocks = self.scanner.get_tradeable_stocks()
        logging.info(f"Found {len(tradeable_stocks)} tradeable stocks")
        
        for symbol in tradeable_stocks:
            if symbol in self.risk_manager.positions:
                continue
                
            bars = self.get_historical_data(symbol)
            if bars.empty:
                continue
                
            entry_signal = self.entry_strategy.find_entry_signal(
                symbol,
                bars,
                portfolio_value
            )
            
            if entry_signal:
                self.execute_entry(entry_signal)

    def run(self):
        """Main trading loop"""
        logging.info("Starting swing trader...")
        
        while True:
            try:
                clock = self.api.get_clock()
                
                # Only trade during market hours
                if clock.is_open:
                    # Reset daily P&L at market open
                    if datetime.now().hour == 9 and datetime.now().minute == 30:
                        self.risk_manager.reset_daily_pl()
                    
                    self.manage_positions()
                    self.find_new_entries()
                
                # Sleep for 5 minutes
                time.sleep(300)
                
            except Exception as e:
                logging.error(f"Error in main loop: {str(e)}")
                time.sleep(60)

if __name__ == "__main__":
    # Load configuration from environment variables
    alpaca_config = AlpacaConfig(
        API_KEY=os.getenv("ALPACA_API_KEY"),
        API_SECRET=os.getenv("ALPACA_API_SECRET")
    )
    trading_config = TradingConfig()
    
    # Initialize and run trader
    trader = SwingTrader(alpaca_config, trading_config)
    trader.run() 