import alpaca_trade_api as tradeapi
import pandas as pd
from datetime import datetime, timedelta, time
import time as time_lib
import logging
from typing import Dict, List
import pytz

class LiveTrader:
    def __init__(self, api_key: str, api_secret: str, base_url: str, risk_per_trade: float = 0.02):
        # Setup logging first
        logging.basicConfig(
            filename=f'trading_log_{datetime.now().strftime("%Y%m%d")}.txt',
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger()
        
        # Initialize timezone
        self.est_tz = pytz.timezone('America/New_York')
        
        # Initialize API and get account info
        self.api = tradeapi.REST(api_key, api_secret, base_url, api_version='v2')
        self.risk_per_trade = risk_per_trade
        
        # Get account information
        account = self.api.get_account()
        self.logger.info(f"Starting with account balance: ${float(account.equity):,.2f}")
        
        self.last_known_positions = {}  # Speichert den letzten bekannten Zustand
        self.reconnect_attempts = 3     # Anzahl der Wiederverbindungsversuche
    
    def get_current_est_time(self) -> datetime:
        """Get current time in EST"""
        return datetime.now(self.est_tz)
    
    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def get_current_data(self, symbol: str) -> pd.DataFrame:
        """Get latest market data"""
        try:
            # Get last 100 bars of 5-minute data
            bars = self.api.get_bars(
                symbol,
                '5Min',
                limit=100,
                adjustment='raw'
            ).df
            
            # Calculate indicators
            bars['MA_10'] = bars['close'].rolling(window=10).mean()
            bars['MA_20'] = bars['close'].rolling(window=20).mean()
            bars['Price_Change'] = bars['close'].pct_change()
            bars['RSI'] = self.calculate_rsi(bars['close'], period=14)
            
            return bars
        except Exception as e:
            self.logger.error(f"Error getting data for {symbol}: {e}")
            return None
    
    def check_entry_conditions(self, df: pd.DataFrame) -> bool:
        """Check if entry conditions are met"""
        if len(df) < 20:  # Need enough bars for indicators
            return False
            
        latest = df.iloc[-1]
        
        # Print current values for debugging
        print(f"\nCurrent Indicators:")
        print(f"Price: ${latest['close']:.2f}")
        print(f"MA_10: ${latest['MA_10']:.2f}")
        print(f"MA_20: ${latest['MA_20']:.2f}")
        print(f"RSI: {latest['RSI']:.1f}")
        print(f"Price Change: {latest['Price_Change']*100:.2f}%")
        
        trend_condition = (
            latest['close'] > latest['MA_10'] or
            latest['close'] > latest['MA_20']
        )
        
        pullback_condition = (
            abs(latest['close'] - latest['MA_10']) / latest['close'] < 0.02 or
            abs(latest['close'] - latest['MA_20']) / latest['close'] < 0.03
        )
        
        momentum_condition = (
            latest['Price_Change'] > -0.02 or
            latest['RSI'] < 40
        )
        
        conditions_met = sum([trend_condition, pullback_condition, momentum_condition])
        
        # Print which conditions are met
        print("\nConditions Check:")
        print(f"Trend: {'✓' if trend_condition else '✗'}")
        print(f"Pullback: {'✓' if pullback_condition else '✗'}")
        print(f"Momentum: {'✓' if momentum_condition else '✗'}")
        
        return conditions_met >= 2
    
    def calculate_position_size(self, price: float, stop_loss: float) -> int:
        """Calculate position size based on risk"""
        account = self.api.get_account()
        equity = float(account.equity)
        
        risk_amount = equity * self.risk_per_trade
        risk_per_share = price - stop_loss
        
        position_size = int(risk_amount / risk_per_share)
        
        # Make sure we don't exceed buying power
        buying_power = float(account.buying_power)
        max_shares = int(buying_power / price)
        
        return min(position_size, max_shares)
    
    def execute_trade(self, symbol: str, side: str, qty: int) -> bool:
        """Execute trade through Alpaca"""
        try:
            self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                type='market',
                time_in_force='day'
            )
            self.logger.info(f"Executed {side} order for {qty} shares of {symbol}")
            return True
        except Exception as e:
            self.logger.error(f"Error executing trade: {e}")
            return False
    
    def manage_positions(self):
        """Check and manage open positions"""
        positions = self.api.list_positions()
        
        for position in positions:
            symbol = position.symbol
            df = self.get_current_data(symbol)
            if df is None:
                continue
            
            latest = df.iloc[-1]
            entry_price = float(position.avg_entry_price)
            current_price = float(latest['close'])
            
            # Check stop loss (2% below entry)
            stop_loss = entry_price * 0.98
            
            # Check trailing stop
            if current_price >= entry_price * 1.03:  # Up 3%
                stop_loss = max(entry_price, stop_loss)
            if current_price >= entry_price * 1.05:  # Up 5%
                stop_loss = max(current_price * 0.97, stop_loss)
            if current_price >= entry_price * 1.10:  # Up 10%
                stop_loss = max(current_price * 0.95, stop_loss)
            
            # Exit if price below stop or MA20
            if latest['low'] <= stop_loss or current_price < latest['MA_20']:
                self.execute_trade(symbol, 'sell', position.qty)
    
    def wait_for_market_open(self):
        """Wait for market to open"""
        clock = self.api.get_clock()
        now = self.get_current_est_time()
        
        if not clock.is_open:
            next_open = clock.next_open.astimezone(self.est_tz)
            time_until_open = (next_open - now).total_seconds()
            
            print(f"\nMarket is closed.")
            print(f"Current EST time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"Next market open: {next_open.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            
            if time_until_open < 24 * 60 * 60:  # less than 24 hours
                hours = int(time_until_open / 3600)
                minutes = int((time_until_open % 3600) / 60)
                print(f"Sleeping for {hours} hours and {minutes} minutes until market open...")
            else:
                print("Market opens next trading day. Going to sleep...")
            
            # Sleep until 1 minute before market open
            sleep_time = max(0, time_until_open - 60)
            time_lib.sleep(sleep_time)
            
            print("\nMarket is about to open!")
            self.logger.info("Market about to open")
            return True
        return False

    def is_trading_time(self) -> bool:
        """Check if it's currently trading hours"""
        clock = self.api.get_clock()
        if not clock.is_open:
            return False
        
        # Optional: Avoid trading in first 15 minutes and last 5 minutes of the day
        current_time = datetime.now().time()
        market_open = datetime.strptime('09:45', '%H:%M').time()  # 15 mins after open
        market_close = datetime.strptime('15:55', '%H:%M').time() # 5 mins before close
        
        return market_open <= current_time <= market_close

    def reconnect(self) -> bool:
        """Versucht die Verbindung wiederherzustellen"""
        for attempt in range(self.reconnect_attempts):
            try:
                print(f"\nVerbindungsversuch {attempt + 1}/{self.reconnect_attempts}...")
                # Verbindung testen
                self.api.get_account()
                
                # Positionen synchronisieren
                current_positions = self.api.list_positions()
                self.sync_positions(current_positions)
                
                print("Verbindung wiederhergestellt!")
                self.logger.info("Verbindung wiederhergestellt nach Unterbrechung")
                return True
                
            except Exception as e:
                print(f"Wiederverbindung fehlgeschlagen: {e}")
                time_lib.sleep(30)  # 30 Sekunden warten vor nächstem Versuch
                
        return False
        
    def sync_positions(self, current_positions):
        """Synchronisiert den aktuellen Positionsstatus"""
        print("\nSynchronisiere Positionen...")
        
        # Aktuelle Positionen in Dictionary umwandeln
        current_pos_dict = {p.symbol: {
            'size': int(p.qty),
            'entry_price': float(p.avg_entry_price),
            'current_price': float(p.current_price),
            'profit_loss': float(p.unrealized_pl)
        } for p in current_positions}
        
        # Vergleich mit letztem bekannten Status
        for symbol in set(self.last_known_positions.keys()) | set(current_pos_dict.keys()):
            old_pos = self.last_known_positions.get(symbol)
            new_pos = current_pos_dict.get(symbol)
            
            if old_pos and not new_pos:
                print(f"{symbol}: Position wurde geschlossen während der Unterbrechung")
            elif not old_pos and new_pos:
                print(f"{symbol}: Neue Position gefunden: {new_pos['size']} Aktien @ ${new_pos['entry_price']:.2f}")
            elif old_pos and new_pos:
                if old_pos['size'] != new_pos['size']:
                    print(f"{symbol}: Positionsgröße geändert von {old_pos['size']} zu {new_pos['size']}")
                print(f"{symbol}: Aktueller P/L: ${new_pos['profit_loss']:.2f}")
        
        # Status aktualisieren
        self.last_known_positions = current_pos_dict
        print("Positionen synchronisiert!")

    def print_current_status(self):
        """Zeigt aktuellen Status aller Positionen und Account-Informationen"""
        try:
            # Account Information
            account = self.api.get_account()
            
            print("\n=== ACCOUNT STATUS ===")
            print(f"Equity: ${float(account.equity):,.2f}")
            print(f"Buying Power: ${float(account.buying_power):,.2f}")
            print(f"Day Trading Buying Power: ${float(account.daytrading_buying_power):,.2f}")
            print(f"Cash: ${float(account.cash):,.2f}")
            
            # Tägliche P&L
            print(f"\nToday's P&L: ${float(account.equity) - float(account.last_equity):,.2f} " +
                  f"({((float(account.equity) - float(account.last_equity)) / float(account.last_equity) * 100):.2f}%)")
            
            # Offene Positionen
            positions = self.api.list_positions()
            
            if positions:
                print("\n=== OPEN POSITIONS ===")
                print(f"{'Symbol':<6} {'Shares':<7} {'Entry':<10} {'Current':<10} {'P&L $':<10} {'P&L %':<8} {'Stop':<10}")
                print("-" * 65)
                
                total_pl = 0
                for pos in positions:
                    symbol = pos.symbol
                    shares = int(pos.qty)
                    entry = float(pos.avg_entry_price)
                    current = float(pos.current_price)
                    pl_dollar = float(pos.unrealized_pl)
                    pl_percent = float(pos.unrealized_plpc) * 100
                    stop = entry * 0.98  # 2% stop loss
                    
                    total_pl += pl_dollar
                    
                    print(f"{symbol:<6} {shares:<7} ${entry:<9.2f} ${current:<9.2f} " +
                          f"${pl_dollar:<9.2f} {pl_percent:<7.2f}% ${stop:<9.2f}")
                
                print("-" * 65)
                print(f"Total P&L: ${total_pl:,.2f}")
            else:
                print("\nNo open positions")
            
            print("\n=== RECENT ORDERS ===")
            orders = self.api.list_orders(status='all', limit=5)
            if orders:
                for order in orders:
                    print(f"{order.symbol}: {order.side} {order.qty} @ ${float(order.filled_avg_price if order.filled_avg_price else order.limit_price):.2f} - {order.status}")
            else:
                print("No recent orders")
            
        except Exception as e:
            print(f"Error getting status: {e}")

    def generate_daily_summary(self) -> str:
        """Generate end-of-day trading summary"""
        try:
            account = self.api.get_account()
            today = self.get_current_est_time().strftime('%Y-%m-%d')
            
            # Get all of today's orders
            orders = self.api.list_orders(
                status='all',
                after=f"{today}T00:00:00-04:00",
                until=f"{today}T23:59:59-04:00"
            )
            
            # Calculate daily statistics
            total_trades = len([o for o in orders if o.status == 'filled'])
            winning_trades = len([o for o in orders if o.status == 'filled' and float(o.filled_avg_price or 0) > float(o.limit_price or 0)])
            
            summary = [
                "\n====================================",
                f"DAILY TRADING SUMMARY - {today}",
                "====================================",
                f"Account Balance: ${float(account.equity):,.2f}",
                f"Daily P&L: ${float(account.equity) - float(account.last_equity):,.2f}",
                f"Daily Return: {((float(account.equity) - float(account.last_equity)) / float(account.last_equity) * 100):.2f}%",
                f"Total Trades: {total_trades}",
                f"Winning Trades: {winning_trades}",
                f"Win Rate: {(winning_trades/total_trades*100):.1f}%" if total_trades > 0 else "Win Rate: N/A",
                "\nClosed Positions Today:",
                "------------------------"
            ]
            
            # Add closed positions details
            closed_positions = [o for o in orders if o.status == 'filled' and o.side == 'sell']
            for pos in closed_positions:
                entry_order = next((o for o in orders if o.symbol == pos.symbol and o.side == 'buy'), None)
                if entry_order:
                    entry_price = float(entry_order.filled_avg_price or entry_order.limit_price or 0)
                    exit_price = float(pos.filled_avg_price or pos.limit_price or 0)
                    pl_dollar = (exit_price - entry_price) * float(pos.qty)
                    pl_percent = ((exit_price - entry_price) / entry_price * 100)
                    
                    summary.append(
                        f"{pos.symbol}: {pos.qty} shares, " +
                        f"Entry: ${entry_price:.2f}, Exit: ${exit_price:.2f}, " +
                        f"P&L: ${pl_dollar:.2f} ({pl_percent:.1f}%)"
                    )
            
            # Add current open positions
            summary.extend([
                "\nOpen Positions:",
                "---------------"
            ])
            
            positions = self.api.list_positions()
            for pos in positions:
                summary.append(
                    f"{pos.symbol}: {pos.qty} shares, " +
                    f"Entry: ${float(pos.avg_entry_price):.2f}, " +
                    f"Current: ${float(pos.current_price):.2f}, " +
                    f"P&L: ${float(pos.unrealized_pl):.2f} ({float(pos.unrealized_plpc)*100:.1f}%)"
                )
            
            summary.extend([
                "\n====================================",
                f"Generated at: {self.get_current_est_time().strftime('%H:%M:%S %Z')}",
                "====================================\n"
            ])
            
            return "\n".join(summary)
        except Exception as e:
            self.logger.error(f"Error generating daily summary: {e}")
            return f"Error generating daily summary: {e}"

    def check_end_of_day(self):
        """Check if it's end of trading day and log summary"""
        try:
            current_time = self.get_current_est_time().time()
            market_close = time(15, 55)  # 3:55 PM EST
            
            if current_time >= market_close:
                summary = self.generate_daily_summary()
                self.logger.info(summary)
                print("\nEnd of day summary has been logged to file.")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error checking end of day: {e}")
            return False

    def run(self, symbols: List[str]):
        """Main trading loop"""
        print("\n=== Starting Trading Bot ===")
        print(f"Monitoring symbols: {', '.join(symbols)}")
        self.logger.info("Starting trading bot...")
        
        last_eod_date = None
        
        while True:
            try:
                clock = self.api.get_clock()
                now = self.get_current_est_time()
                current_date = now.date()
                
                # Print current status
                self.print_current_status()
                
                # Check for end of day summary (only once per day)
                if current_date != last_eod_date and self.check_end_of_day():
                    last_eod_date = current_date
                
                # Rest of the existing run() code...
                if not clock.is_open:
                    time_to_open = (clock.next_open.astimezone(self.est_tz) - now).total_seconds()
                    print(f"\nMarket is closed. Sleeping until next market open.")
                    print(f"Current EST time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                    print(f"Next market open: {clock.next_open.astimezone(self.est_tz).strftime('%Y-%m-%d %H:%M:%S %Z')}")
                    
                    time_lib.sleep(time_to_open)
                    continue
                
                # Check if it's too early or too late in the trading day
                current_time = now.time()
                market_open = time(9, 45)  # 15 mins after open
                market_close = time(15, 55)  # 5 mins before close
                
                if current_time < market_open:
                    wait_seconds = (datetime.combine(datetime.today(), market_open) - 
                                  datetime.combine(datetime.today(), current_time)).total_seconds()
                    print(f"\nToo early to trade. Sleeping for {int(wait_seconds/60)} minutes...")
                    time_lib.sleep(wait_seconds)
                    continue
                    
                if current_time > market_close:
                    print("\nMarket closing soon. Waiting for next trading day...")
                    time_to_next_open = (clock.next_open.astimezone(self.est_tz) - now).total_seconds()
                    time_lib.sleep(time_to_next_open)
                    continue
                
                print(f"\n=== Checking positions and signals at {now.strftime('%H:%M:%S %Z')} ===")
                
                # Rest of the trading logic...
                positions = self.api.list_positions()
                if positions:
                    print(f"Managing {len(positions)} open positions...")
                self.manage_positions()
                
                print("Scanning for new trade setups...")
                for symbol in symbols:
                    if any(p.symbol == symbol for p in positions):
                        print(f"{symbol}: Already in position, skipping...")
                        continue
                    
                    df = self.get_current_data(symbol)
                    if df is None:
                        continue
                    
                    if self.check_entry_conditions(df):
                        print(f"\nEntry signal found for {symbol}!")
                        current_price = df.iloc[-1]['close']
                        stop_loss = current_price * 0.98
                        position_size = self.calculate_position_size(current_price, stop_loss)
                        
                        if position_size > 0:
                            success = self.execute_trade(symbol, 'buy', position_size)
                            if success:
                                print(f"Entered {symbol} with {position_size} shares at {current_price}")
                                self.logger.info(f"Entered {symbol} with {position_size} shares at {current_price}")
                    else:
                        print(f"{symbol}: No entry signal")
                
                print(f"\nSleeping for 60 seconds until next check...")
                time_lib.sleep(60)
                
            except Exception as e:
                print(f"\nError in main loop: {e}")
                self.logger.error(f"Error in main loop: {e}")
                if "connection" in str(e).lower():
                    print("\nConnection lost. Attempting to reconnect...")
                    if not self.reconnect():
                        print("Failed to reconnect. Exiting.")
                        break
                    continue
                time_lib.sleep(60) 