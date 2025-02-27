import alpaca_trade_api as tradeapi
import pandas as pd
from datetime import datetime, timedelta, time
import time as time_lib
import logging
from typing import Dict, List, Optional, Tuple
import pytz
import numpy as np

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
        
        try:
            # Initialize API and get account info
            self.api = tradeapi.REST(api_key, api_secret, base_url, api_version='v2')
            
            # Validate connection by getting account info
            account = self.api.get_account()
            self.risk_per_trade = risk_per_trade
            self.logger.info(f"Starting with account balance: ${float(account.equity):,.2f}")
            
            # Store state information
            self.last_known_positions = {}  # Speichert den letzten bekannten Zustand
            self.reconnect_attempts = 3     # Anzahl der Wiederverbindungsversuche
            self.max_loss_per_trade = 0.02  # 2% maximaler Verlust pro Trade
            self.trailing_stop_levels = {
                1.03: 0,       # Bei 3% Gewinn: Stop auf Break-Even
                1.05: 0.97,    # Bei 5% Gewinn: Stop auf 3% unter aktuellem Preis
                1.10: 0.95     # Bei 10% Gewinn: Stop auf 5% unter aktuellem Preis
            }
            
            self.logger.info("LiveTrader initialized successfully")
            print("LiveTrader initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Error initializing LiveTrader: {e}")
            print(f"Error initializing LiveTrader: {e}")
            raise
    
    def get_current_est_time(self) -> datetime:
        """Get current time in EST"""
        return datetime.now(self.est_tz)
    
    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator with safe division"""
        try:
            delta = prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            
            # Avoid division by zero
            rs = gain / loss.replace(0, 1e-9)
            return 100 - (100 / (1 + rs))
        except Exception as e:
            self.logger.error(f"Error calculating RSI: {e}")
            # Return a Series of 50s (neutral) with the same length as prices
            return pd.Series(50, index=prices.index)
    
    def get_current_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Get latest market data with error handling"""
        for attempt in range(3):  # Try up to 3 times
            try:
                # Get last 100 bars of 5-minute data
                bars = self.api.get_bars(
                    symbol,
                    '5Min',
                    limit=100,
                    adjustment='raw'
                ).df
                
                if bars.empty:
                    self.logger.warning(f"No data returned for {symbol}")
                    return None
                
                # Calculate indicators
                bars['MA_10'] = bars['close'].rolling(window=10).mean()
                bars['MA_20'] = bars['close'].rolling(window=20).mean()
                bars['Price_Change'] = bars['close'].pct_change() * 100  # As percentage
                bars['RSI'] = self.calculate_rsi(bars['close'], period=14)
                
                return bars
            except Exception as e:
                self.logger.error(f"Error getting data for {symbol} (attempt {attempt+1}): {e}")
                if attempt < 2:  # Don't sleep on the last attempt
                    time_lib.sleep(5)  # Wait 5 seconds before retrying
        
        return None
    
    def check_entry_conditions(self, df: pd.DataFrame) -> bool:
        """Check if entry conditions are met based on price action and indicators"""
        try:
            if len(df) < 20:
                return False
                
            # Get latest values
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            # Get scalar values to avoid Series comparisons
            current_price = float(latest['close'])
            ma10 = float(latest['MA_10']) if not pd.isna(latest['MA_10']) else 0
            ma20 = float(latest['MA_20']) if not pd.isna(latest['MA_20']) else 0
            rsi = float(latest['RSI']) if not pd.isna(latest['RSI']) else 50
            price_change = float(latest['Price_Change']) if not pd.isna(latest['Price_Change']) else 0
            
            # Entry conditions - converted to scalar comparisons
            # 1. Price is above both moving averages
            condition1 = current_price > ma10 and ma10 > ma20
            
            # 2. RSI shows bullish momentum (between 40-70)
            condition2 = 40 < rsi < 70
            
            # 3. Recent price change is positive
            condition3 = price_change > 0.3
            
            # Combine conditions with AND (all must be true)
            entry_signal = condition1 and condition2 and condition3
            
            if entry_signal:
                self.logger.info(f"Entry signal triggered: Price: ${current_price:.2f}, RSI: {rsi:.1f}, Change: {price_change:.2f}%")
            
            return entry_signal
            
        except Exception as e:
            self.logger.error(f"Error checking entry conditions: {e}")
            return False
    
    def calculate_position_size(self, current_price: float, stop_loss: float) -> int:
        """Calculate position size based on risk management rules"""
        try:
            account = self.api.get_account()
            equity = float(account.equity)
            
            # Calculate dollar risk
            risk_amount = equity * self.risk_per_trade
            
            # Calculate price difference to stop loss
            price_difference = abs(current_price - stop_loss)
            
            # If stop is too tight, adjust it
            if price_difference < (current_price * 0.01):  # If less than 1% movement
                price_difference = current_price * 0.02  # Default to 2% movement
                self.logger.warning(f"Stop loss too tight, adjusted to 2% (${price_difference:.2f})")
            
            # Calculate share quantity based on risk
            shares = int(risk_amount / price_difference)
            
            # Cap position size based on available buying power (with margin)
            buying_power = float(account.buying_power) * 0.95  # Use 95% of buying power
            max_shares_by_capital = int(buying_power / current_price)
            
            # Take the smaller of the two
            final_shares = min(shares, max_shares_by_capital)
            
            # Additional safety check - ensure we're not using more than 10% of equity per position
            max_position_value = equity * 0.1  # 10% max allocation per position
            max_shares_by_allocation = int(max_position_value / current_price)
            final_shares = min(final_shares, max_shares_by_allocation)
            
            # Final sanity check
            if final_shares <= 0:
                self.logger.warning("Calculated position size is 0 or negative")
                return 0
                
            self.logger.info(f"Position size: {final_shares} shares (${final_shares * current_price:.2f}, {(final_shares * current_price / equity * 100):.1f}% of portfolio)")
            return final_shares
            
        except Exception as e:
            self.logger.error(f"Error calculating position size: {e}")
            return 0
    
    def execute_trade(self, symbol: str, side: str, qty: int) -> bool:
        """Execute a trade with error handling"""
        if qty <= 0:
            self.logger.warning(f"Invalid quantity ({qty}) for {symbol} {side} order")
            return False
            
        try:
            # Submit market order
            order = self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                type='market',
                time_in_force='day'
            )
            
            self.logger.info(f"Order placed: {side} {qty} shares of {symbol} (ID: {order.id})")
            
            # Wait for order to fill
            filled = False
            for _ in range(5):  # Try 5 times
                time_lib.sleep(2)  # Wait 2 seconds
                order_status = self.api.get_order(order.id)
                if order_status.status == 'filled':
                    filled = True
                    self.logger.info(f"Order filled: {side} {qty} shares of {symbol} at ${float(order_status.filled_avg_price):.2f}")
                    
                    # Update position tracking
                    if side == 'buy':
                        self.last_known_positions[symbol] = {
                            'size': qty,
                            'entry_price': float(order_status.filled_avg_price),
                            'current_price': float(order_status.filled_avg_price),
                            'profit_loss': 0.0
                        }
                    elif side == 'sell' and symbol in self.last_known_positions:
                        del self.last_known_positions[symbol]
                    
                    break
                    
            if not filled:
                self.logger.warning(f"Order not filled after waiting: {side} {qty} shares of {symbol}")
            
            return filled
            
        except Exception as e:
            self.logger.error(f"Error executing {side} order for {symbol}: {e}")
            return False
    
    def manage_positions(self):
        """Check and manage open positions with error handling"""
        try:
            positions = self.api.list_positions()
            
            for position in positions:
                symbol = position.symbol
                entry_price = float(position.avg_entry_price)
                position_size = int(position.qty)
                
                # Get current data
                df = self.get_current_data(symbol)
                if df is None or df.empty:
                    self.logger.warning(f"No data available for {symbol}, skipping position management")
                    continue
                
                # Get latest price data as scalar values
                latest = df.iloc[-1]
                current_price = float(latest['close'])
                current_low = float(latest['low'])
                ma20 = float(latest['MA_20']) if not pd.isna(latest['MA_20']) else 0
                
                # Calculate initial stop loss (2% below entry)
                stop_loss = entry_price * (1 - self.max_loss_per_trade)
                
                # Track whether we've updated the stop
                trailing_stop_updated = False
                original_stop = stop_loss
                
                # Apply trailing stop rules based on profit levels
                for profit_level, stop_multiplier in sorted(self.trailing_stop_levels.items()):
                    if current_price >= entry_price * profit_level:
                        new_stop = entry_price if stop_multiplier == 0 else current_price * stop_multiplier
                        if new_stop > stop_loss:
                            stop_loss = new_stop
                            trailing_stop_updated = True
                            profit_pct = (profit_level - 1) * 100
                            self.logger.info(f"{symbol}: Trailing stop raised to ${stop_loss:.2f} ({profit_pct:.0f}% profit reached)")
                
                # Log position status
                profit_pct = (current_price - entry_price) / entry_price * 100
                self.logger.info(f"{symbol} position status: Entry: ${entry_price:.2f}, Current: ${current_price:.2f}, P/L: {profit_pct:.2f}%, Stop: ${stop_loss:.2f}")
                
                # Check exit conditions (price below stop or MA20)
                exit_reason = None
                if current_low <= stop_loss:
                    exit_reason = f"Stop loss triggered at ${stop_loss:.2f} (Current low: ${current_low:.2f})"
                elif current_price < ma20:
                    exit_reason = f"Trend exit triggered - price ${current_price:.2f} below MA20 ${ma20:.2f}"
                
                # Execute exit if needed
                if exit_reason:
                    self.logger.info(f"{symbol}: {exit_reason}")
                    print(f"\n*** SELLING {symbol}: {exit_reason} ***")
                    self.execute_trade(symbol, 'sell', position_size)
        
        except Exception as e:
            self.logger.error(f"Error in manage_positions: {e}")
    
    def wait_for_market_open(self):
        """Wait for market to open with better user feedback"""
        try:
            clock = self.api.get_clock()
            if not clock.is_open:
                current_time = self.get_current_est_time()
                next_market_open = clock.next_open.astimezone(self.est_tz)
                
                time_to_open = (next_market_open - current_time).total_seconds()
                hours, remainder = divmod(time_to_open, 3600)
                minutes, seconds = divmod(remainder, 60)
                
                print(f"\nMarket is closed. Next open: {next_market_open.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                print(f"Waiting {int(hours)}h {int(minutes)}m {int(seconds)}s until market open...")
                
                self.logger.info(f"Waiting for market open at {next_market_open.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                
                # Sleep in shorter intervals with updates
                while time_to_open > 0:
                    sleep_time = min(900, time_to_open)  # Sleep at most 15 minutes at a time
                    time_lib.sleep(sleep_time)
                    time_to_open -= sleep_time
                    
                    # Update remaining time every 15 minutes
                    if time_to_open > 0:
                        hours, remainder = divmod(time_to_open, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        print(f"Still waiting... {int(hours)}h {int(minutes)}m remaining until market open")
                
                print("Market is now open!")
                self.logger.info("Market is now open")
                return True
            return True
        except Exception as e:
            self.logger.error(f"Error waiting for market open: {e}")
            time_lib.sleep(60)  # Wait 1 minute and let caller retry
            return False
    
    def is_trading_time(self) -> bool:
        """Check if current time is suitable for trading"""
        try:
            now = self.get_current_est_time()
            current_time = now.time()
            
            # Define trading hours (9:30 AM to 4:00 PM EST)
            # We'll avoid trading in the first 15 minutes and last 5 minutes
            market_open = time(9, 45)  # 15 mins after open
            market_close = time(15, 55)  # 5 mins before close
            
            trading_time = market_open <= current_time <= market_close
            
            if not trading_time:
                if current_time < market_open:
                    self.logger.info(f"Too early to trade ({current_time.strftime('%H:%M')}). Trading starts at {market_open.strftime('%H:%M')}")
                else:
                    self.logger.info(f"Too late to trade ({current_time.strftime('%H:%M')}). Trading ends at {market_close.strftime('%H:%M')}")
            
            return trading_time
        except Exception as e:
            self.logger.error(f"Error checking trading time: {e}")
            return False  # Default to not trading if there's an error
    
    def reconnect(self) -> bool:
        """Versucht die Verbindung wiederherzustellen mit besserer Fehlerbehandlung"""
        for attempt in range(self.reconnect_attempts):
            try:
                print(f"\nVerbindungsversuch {attempt + 1}/{self.reconnect_attempts}...")
                self.logger.info(f"Reconnect attempt {attempt + 1}/{self.reconnect_attempts}")
                
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
                self.logger.error(f"Reconnect attempt {attempt + 1} failed: {e}")
                time_lib.sleep(30)  # 30 Sekunden warten vor nächstem Versuch
                
        print("Alle Wiederverbindungsversuche fehlgeschlagen!")
        self.logger.error("All reconnection attempts failed")
        return False
        
    def sync_positions(self, current_positions):
        """Synchronisiert den aktuellen Positionsstatus mit verbesserter Fehlerbehandlung"""
        try:
            print("\nSynchronisiere Positionen...")
            
            # Aktuelle Positionen in Dictionary umwandeln
            current_pos_dict = {}
            for p in current_positions:
                try:
                    current_pos_dict[p.symbol] = {
                        'size': int(p.qty),
                        'entry_price': float(p.avg_entry_price),
                        'current_price': float(p.current_price),
                        'profit_loss': float(p.unrealized_pl)
                    }
                except Exception as e:
                    self.logger.error(f"Error processing position for {p.symbol}: {e}")
            
            # Vergleich mit letztem bekannten Status
            for symbol in set(self.last_known_positions.keys()) | set(current_pos_dict.keys()):
                old_pos = self.last_known_positions.get(symbol)
                new_pos = current_pos_dict.get(symbol)
                
                if old_pos and not new_pos:
                    print(f"{symbol}: Position wurde geschlossen während der Unterbrechung")
                    self.logger.info(f"{symbol}: Position closed during connection loss")
                elif not old_pos and new_pos:
                    print(f"{symbol}: Neue Position gefunden: {new_pos['size']} Aktien @ ${new_pos['entry_price']:.2f}")
                    self.logger.info(f"{symbol}: New position found during reconnect: {new_pos['size']} shares @ ${new_pos['entry_price']:.2f}")
                elif old_pos and new_pos:
                    if old_pos['size'] != new_pos['size']:
                        print(f"{symbol}: Positionsgröße geändert von {old_pos['size']} zu {new_pos['size']}")
                        self.logger.info(f"{symbol}: Position size changed from {old_pos['size']} to {new_pos['size']}")
                    print(f"{symbol}: Aktueller P/L: ${new_pos['profit_loss']:.2f}")
            
            # Status aktualisieren
            self.last_known_positions = current_pos_dict
            print("Positionen synchronisiert!")
            self.logger.info("Positions synchronized successfully")
            
        except Exception as e:
            self.logger.error(f"Error synchronizing positions: {e}")
            print(f"Fehler beim Synchronisieren der Positionen: {e}")
    
    def print_current_status(self):
        """Zeigt aktuellen Status aller Positionen und Account-Informationen mit verbesserter Fehlerbehandlung"""
        try:
            # Account Information
            account = self.api.get_account()
            
            print("\n=== ACCOUNT STATUS ===")
            print(f"Equity: ${float(account.equity):,.2f}")
            print(f"Buying Power: ${float(account.buying_power):,.2f}")
            print(f"Day Trading Buying Power: ${float(account.daytrading_buying_power):,.2f}")
            print(f"Cash: ${float(account.cash):,.2f}")
            
            # Tägliche P&L
            try:
                last_equity = float(account.last_equity) if account.last_equity and float(account.last_equity) > 0 else float(account.equity)
                daily_pl = float(account.equity) - last_equity
                daily_pl_pct = (daily_pl / last_equity * 100) if last_equity > 0 else 0
                print(f"\nToday's P&L: ${daily_pl:,.2f} ({daily_pl_pct:.2f}%)")
            except Exception as e:
                self.logger.error(f"Error calculating daily P&L: {e}")
                print("Today's P&L: Not available")
            
            # Offene Positionen
            try:
                positions = self.api.list_positions()
                
                if positions:
                    print("\n=== OPEN POSITIONS ===")
                    print(f"{'Symbol':<6} {'Shares':<7} {'Entry':<10} {'Current':<10} {'P&L $':<10} {'P&L %':<8} {'Stop':<10}")
                    print("-" * 65)
                    
                    total_pl = 0
                    for pos in positions:
                        try:
                            symbol = pos.symbol
                            shares = int(pos.qty)
                            entry = float(pos.avg_entry_price)
                            current = float(pos.current_price)
                            pl_dollar = float(pos.unrealized_pl)
                            pl_percent = float(pos.unrealized_plpc) * 100
                            stop = entry * 0.98  # 2% stop loss - simplified
                            
                            total_pl += pl_dollar
                            
                            print(f"{symbol:<6} {shares:<7} ${entry:<9.2f} ${current:<9.2f} " +
                                  f"${pl_dollar:<9.2f} {pl_percent:<7.2f}% ${stop:<9.2f}")
                        except Exception as e:
                            self.logger.error(f"Error processing position data for {getattr(pos, 'symbol', 'unknown')}: {e}")
                    
                    print("-" * 65)
                    print(f"Total P&L: ${total_pl:,.2f}")
                else:
                    print("\nNo open positions")
            except Exception as e:
                self.logger.error(f"Error getting positions: {e}")
                print("\nError getting positions")
            
            # Recent Orders
            try:
                print("\n=== RECENT ORDERS ===")
                orders = self.api.list_orders(status='all', limit=5)
                if orders:
                    for order in orders:
                        filled_price = order.filled_avg_price if order.filled_avg_price else order.limit_price
                        if filled_price:
                            price_str = f"@ ${float(filled_price):.2f}"
                        else:
                            price_str = ""
                        print(f"{order.symbol}: {order.side} {order.qty} {price_str} - {order.status}")
                else:
                    print("No recent orders")
            except Exception as e:
                self.logger.error(f"Error getting recent orders: {e}")
                print("Error getting recent orders")
            
        except Exception as e:
            self.logger.error(f"Error getting status: {e}")
            print(f"Error getting status: {e}")
    
    def generate_daily_summary(self) -> str:
        """Generate end-of-day trading summary with improved error handling"""
        try:
            # Get account info
            account = self.api.get_account()
            
            # Get current date and time
            now = self.get_current_est_time()
            
            # Build summary
            summary = [
                f"Trading Summary - {now.strftime('%Y-%m-%d')}",
                "====================================",
                "",
                "Account Summary:",
                "---------------",
                f"Equity: ${float(account.equity):,.2f}",
                f"Cash: ${float(account.cash):,.2f}",
                f"Buying Power: ${float(account.buying_power):,.2f}"
            ]
            
            # Daily P&L
            try:
                if hasattr(account, 'last_equity') and account.last_equity:
                    last_equity = float(account.last_equity)
                    daily_pl = float(account.equity) - last_equity
                    daily_pl_pct = (daily_pl / last_equity * 100)
                    summary.append(f"Today's P&L: ${daily_pl:,.2f} ({daily_pl_pct:.2f}%)")
                else:
                    summary.append("Today's P&L: Not available")
            except Exception as e:
                self.logger.error(f"Error calculating daily P&L for summary: {e}")
                summary.append("Today's P&L: Error calculating")
            
            # Get today's orders
            try:
                today_str = now.strftime('%Y-%m-%d')
                orders = self.api.list_orders(
                    status='closed',
                    after=f"{today_str}T00:00:00Z"
                )
                
                if orders:
                    summary.extend([
                        "",
                        "Today's Trades:",
                        "--------------"
                    ])
                    
                    for order in orders:
                        try:
                            filled_price = f"${float(order.filled_avg_price):.2f}" if order.filled_avg_price else "N/A"
                            summary.append(
                                f"{order.symbol}: {order.side} {order.qty} shares @ {filled_price} - {order.status}"
                            )
                        except Exception as e:
                            self.logger.error(f"Error processing order for summary: {e}")
                else:
                    summary.append("\nNo trades executed today")
            except Exception as e:
                self.logger.error(f"Error getting today's orders for summary: {e}")
                summary.append("\nError retrieving today's trades")
            
            # Add current open positions
            try:
                positions = self.api.list_positions()
                
                if positions:
                    summary.extend([
                        "",
                        "Open Positions:",
                        "---------------"
                    ])
                    
                    for pos in positions:
                        try:
                            summary.append(
                                f"{pos.symbol}: {pos.qty} shares, " +
                                f"Entry: ${float(pos.avg_entry_price):.2f}, " +
                                f"Current: ${float(pos.current_price):.2f}, " +
                                f"P&L: ${float(pos.unrealized_pl):.2f} ({float(pos.unrealized_plpc)*100:.1f}%)"
                            )
                        except Exception as e:
                            self.logger.error(f"Error processing position for summary: {e}")
                else:
                    summary.append("\nNo open positions")
            except Exception as e:
                self.logger.error(f"Error getting positions for summary: {e}")
                summary.append("\nError retrieving open positions")
            
            summary.extend([
                "",
                "====================================",
                f"Generated at: {self.get_current_est_time().strftime('%H:%M:%S %Z')}",
                "===================================="
            ])
            
            return "\n".join(summary)
            
        except Exception as e:
            self.logger.error(f"Error generating daily summary: {e}")
            return f"Error generating daily summary: {e}"
    
    def check_end_of_day(self) -> bool:
        """Check if it's end of day and perform EOD tasks"""
        try:
            now = self.get_current_est_time()
            current_time = now.time()
            
            # Check if it's near market close (3:58 PM or later)
            if current_time >= time(15, 58):
                print("\n=== END OF DAY PROCEDURES ===")
                self.logger.info("Starting end of day procedures")
                
                # Generate daily summary
                summary = self.generate_daily_summary()
                print(summary)
                self.logger.info("\n" + summary)
                
                print("\n=== END OF DAY COMPLETE ===")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error in check_end_of_day: {e}")
            return False
    
    def run(self, symbols: List[str]):
        """Main trading loop with improved error handling and recovery"""
        print("\n=== Starting Trading Bot ===")
        print(f"Monitoring symbols: {', '.join(symbols)}")
        self.logger.info(f"Starting trading bot... Monitoring: {', '.join(symbols)}")
        
        last_eod_date = None
        
        while True:
            try:
                # Get market clock
                clock = self.api.get_clock()
                now = self.get_current_est_time()
                current_date = now.date()
                
                # Print current status
                self.print_current_status()
                
                # Check for end of day summary (only once per day)
                if current_date != last_eod_date and self.check_end_of_day():
                    last_eod_date = current_date
                
                # Wait for market open if needed
                if not clock.is_open:
                    time_to_open = (clock.next_open.astimezone(self.est_tz) - now).total_seconds()
                    print(f"\nMarket is closed. Sleeping until next market open.")
                    print(f"Current EST time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                    print(f"Next market open: {clock.next_open.astimezone(self.est_tz).strftime('%Y-%m-%d %H:%M:%S %Z')}")
                    
                    # If it's a long wait, sleep in chunks
                    if time_to_open > 3600:  # more than an hour
                        hours, remainder = divmod(time_to_open, 3600)
                        minutes, _ = divmod(remainder, 60)
                        print(f"Waiting {int(hours)} hours and {int(minutes)} minutes...")
                        
                        # Sleep in 1-hour chunks with updates
                        while time_to_open > 0:
                            sleep_time = min(3600, time_to_open)
                            time_lib.sleep(sleep_time)
                            time_to_open -= sleep_time
                            if time_to_open > 0:
                                now = self.get_current_est_time()
                                print(f"Still waiting... Current time: {now.strftime('%H:%M:%S')}")
                    else:
                        # Just sleep until open
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
                
                # Manage existing positions
                positions = self.api.list_positions()
                if positions:
                    print(f"Managing {len(positions)} open positions...")
                self.manage_positions()
                
                # Check for new trade setups
                print("Scanning for new trade setups...")
                for symbol in symbols:
                    # Skip if already in position
                    if any(p.symbol == symbol for p in positions):
                        print(f"{symbol}: Already in position, skipping...")
                        continue
                    
                    # Get and analyze data
                    df = self.get_current_data(symbol)
                    if df is None or df.empty:
                        print(f"{symbol}: No data available, skipping...")
                        continue
                    
                    # Check entry conditions
                    if self.check_entry_conditions(df):
                        print(f"\nEntry signal found for {symbol}!")
                        
                        # Get current price as scalar
                        current_price = float(df.iloc[-1]['close'])
                        stop_loss = current_price * (1 - self.max_loss_per_trade)
                        
                        # Calculate position size
                        position_size = self.calculate_position_size(current_price, stop_loss)
                        
                        # Execute trade if position size is valid
                        if position_size > 0:
                            success = self.execute_trade(symbol, 'buy', position_size)
                            if success:
                                print(f"Entered {symbol} with {position_size} shares at ${current_price:.2f}")
                                self.logger.info(f"Entered {symbol} with {position_size} shares at ${current_price:.2f}")
                            else:
                                print(f"Failed to enter {symbol}")
                        else:
                            print(f"Skipping {symbol} - calculated position size too small")
                    else:
                        print(f"{symbol}: No entry signal")
                
                # Sleep until next check
                print(f"\nSleeping for 60 seconds until next check...")
                time_lib.sleep(60)
                
            except KeyboardInterrupt:
                print("\n\nTrading bot stopped by user")
                self.logger.info("Trading bot stopped by user")
                break
                
            except Exception as e:
                print(f"\nError in main loop: {e}")
                self.logger.error(f"Error in main loop: {e}")
                
                if "connection" in str(e).lower() or "network" in str(e).lower():
                    print("\nConnection lost. Attempting to reconnect...")
                    if not self.reconnect():
                        print("Failed to reconnect. Exiting.")
                        break
                    continue
                
                # Sleep after error to avoid rapid retries
                time_lib.sleep(60) 