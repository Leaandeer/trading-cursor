import pandas as pd
import yfinance as yf
from typing import List, Dict
from datetime import datetime, timedelta
import os
import numpy as np

class Backtester:
    def __init__(self, initial_capital: float, risk_per_trade: float = 0.02):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.risk_per_trade = risk_per_trade
        
        # Create a list to store all trades for CSV export
        self.all_trades = []
    
    def calculate_position_size(self, entry_price: float, stop_loss: float, symbol: str = "Unknown") -> float:
        """Calculate position size based on risk percentage and available capital"""
        # Calculate risk amount (percentage of total capital)
        risk_amount = self.capital * self.risk_per_trade
        
        # Calculate risk per share
        risk_per_share = abs(entry_price - stop_loss)  # Use abs() to handle potential errors
        
        if risk_per_share <= 0:
            print(f"Warning: Invalid risk per share: {risk_per_share}. Using 1% of price as risk.")
            risk_per_share = entry_price * 0.01  # Fallback to 1% of price
        
        # Calculate position size based on risk - allow fractional shares
        position_size = risk_amount / risk_per_share
        
        # Calculate position value
        position_value = position_size * entry_price
        
        # Apply constraints in the correct order:
        
        # 1. First, limit to max 20% of capital per position
        max_position_value = self.capital * 0.1
        if position_value > max_position_value:
            position_size = max_position_value / entry_price
            position_value = position_size * entry_price  # Recalculate after adjustment
            print(f"Warning: Position size reduced to 20% of capital (${max_position_value:.2f})")
        
        # 2. Then, ensure we don't exceed available capital
        if position_value > self.capital:
            position_size = self.capital * 0.95 / entry_price  # Use 95% of capital to leave some buffer
            position_value = position_size * entry_price  # Recalculate after adjustment
            print(f"Warning: Position size reduced to 95% of available capital")
        
        # 3. Finally, ensure minimum position size (0.01 shares for fractional trading)
        if position_size < 0.01:
            print(f"Warning: Position size too small, setting to minimum")
            position_size = 0.01
            position_value = position_size * entry_price  # Recalculate after adjustment
        
        # Print position sizing details
        print(f"Position sizing calculation:")
        print(f"  - Available capital: ${self.capital:,.2f}")
        print(f"  - Risk amount (${self.risk_per_trade*100}%): ${risk_amount:,.2f}")
        print(f"  - Entry price: ${entry_price:.2f}, Stop loss: ${stop_loss:.2f}")
        print(f"  - Risk per share: ${risk_per_share:.2f}")
        print(f"  - Position size: {position_size:.2f} shares")
        print(f"  - Position value: ${position_value:.2f} ({(position_value / self.capital * 100):.2f}% of capital)")
        
        # Calculate percentages for risk management summary
        stop_loss_pct = ((entry_price - stop_loss) / entry_price * 100)
        take_profit_pct = stop_loss_pct * 2  # Assuming 2:1 reward-to-risk ratio
        
        print(f"\n=== Risikomanagement für {symbol} ===")
        print(f"Risikoparameter: {self.risk_per_trade*100:.1f}% des Kapitals pro Trade")
        print(f"Maximale Position: 2% des Kapitals (${max_position_value:.2f})")
        print(f"Stop-Loss: {stop_loss_pct:.1f}% unter Einstiegspreis")
        print(f"Take-Profit: {take_profit_pct:.1f}% über Einstiegspreis")
        print(f"Reward-to-Risk Ratio: 2:1")
        
        return position_size
    
    def fetch_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Fetch historical price data and calculate some basic indicators"""
        try:
            # Fetch data
            df = yf.download(symbol, start=start_date, end=end_date, progress=False)
            
            # Ensure there's enough data
            if len(df) < 20:
                print(f"Not enough data for {symbol}")
                return None
                
            # Calculate some basic indicators
            # Moving Averages
            df['MA_10'] = df['Close'].rolling(window=10).mean()
            df['MA_20'] = df['Close'].rolling(window=20).mean()
            
            # RSI (14)
            delta = df['Close'].diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.rolling(window=14).mean()
            avg_loss = loss.rolling(window=14).mean()
            rs = avg_gain / avg_loss.replace(0, 1e-10)  # Avoid division by zero
            df['RSI'] = 100 - (100 / (1 + rs))
            
            return df
            
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            return None
    
    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def calculate_indicators(self, df):
        """Calculate basic indicators - completely rewritten for reliability"""
        try:
            # Create a copy to avoid SettingWithCopyWarning
            result_df = df.copy()
            
            # Basic Moving Averages - simple and reliable
            result_df['MA_10'] = result_df['Close'].rolling(window=10).mean()
            result_df['MA_20'] = result_df['Close'].rolling(window=20).mean()
            
            # RSI calculation - simplified and robust
            delta = result_df['Close'].diff()
            gain = delta.clip(lower=0)  # All negative values become 0
            loss = -delta.clip(upper=0)  # All positive values become 0
            
            # First Average
            avg_gain = gain.rolling(window=14).mean()
            avg_loss = loss.rolling(window=14).mean()
            
            # Calculate RS
            # Add small number to prevent division by zero
            rs = avg_gain / (avg_loss + 1e-10)  
            result_df['RSI'] = 100 - (100 / (1 + rs))
            
            # Only add Volume_Ratio if Volume exists in the dataframe
            if 'Volume' in result_df.columns:
                result_df['Volume_MA'] = result_df['Volume'].rolling(window=20).mean()
                # Ensure we're working with Series not DataFrames for the division
                vol_series = result_df['Volume'].squeeze()
                vol_ma_series = result_df['Volume_MA'].squeeze()
                # Add epsilon to avoid division by zero
                result_df['Volume_Ratio'] = vol_series / (vol_ma_series + 1e-10)
            
            print("Indicators calculated successfully")
            return result_df
            
        except Exception as e:
            print(f"Error calculating indicators: {e}")
            # Return original dataframe with at least RSI calculated manually
            try:
                # Attempt a more basic calculation
                df['MA_10'] = df['Close'].rolling(window=10).mean()
                df['MA_20'] = df['Close'].rolling(window=20).mean()
                
                # Extremely basic RSI calculation
                up = df['Close'].diff().clip(lower=0)
                down = -df['Close'].diff().clip(upper=0)
                ma_up = up.rolling(window=14).mean()
                ma_down = down.rolling(window=14).mean()
                rsi = 100 - (100 / (1 + ma_up / (ma_down + 1e-10)))
                df['RSI'] = rsi
                
                print("Fallback indicator calculation successful")
                return df
            except:
                print("Even fallback indicator calculation failed")
                return df
    
    def run_single_symbol(self, symbol: str, start_date: str, end_date: str) -> Dict:
        """Run backtest for a single symbol with ultra-robust scalar value approach"""
        print(f"\nBacktesting {symbol} from {start_date} to {end_date}")
        
        try:
            # Load data
            df = self.fetch_data(symbol, start_date, end_date)
            if df is None or len(df) < 20:
                print(f"Not enough data for {symbol} (only {len(df) if df is not None else 0} days).")
                return {"symbol": symbol, "trades": 0, "wins": 0, "losses": 0, "win_rate": 0, "profit": 0}
            
            print(f"Data loaded for {symbol}: {len(df)} trading days")
            
            # Trading variables
            position = None
            position_size = 0
            trailing_stop = 0
            take_profit = 0
            trades = 0
            wins = 0
            losses = 0
            total_profit = 0
            highest_price = 0
            entry_date = None
            
            # Start after indicators are calculated
            start_index = 20
            
            # Iterate through price data using iterrows to avoid Series comparison issues
            for i in range(start_index, len(df)):
                try:
                    # Get scalar values for the current bar - no Series objects!
                    current_date = df.index[i]
                    current_price = float(df['Close'].iloc[i])
                    current_high = float(df['High'].iloc[i])
                    current_low = float(df['Low'].iloc[i])
                    prev_price = float(df['Close'].iloc[i-1])
                    
                    # Calculate price change as scalar value
                    price_change = (current_price - prev_price) / prev_price * 100
                    
                    # Safely extract indicator values as scalars
                    ma10 = float(df['MA_10'].iloc[i]) if not pd.isna(df['MA_10'].iloc[i]) else 0
                    ma20 = float(df['MA_20'].iloc[i]) if not pd.isna(df['MA_20'].iloc[i]) else 0
                    rsi = float(df['RSI'].iloc[i]) if not pd.isna(df['RSI'].iloc[i]) else 50
                    
                    # Check for entry if not in a position
                    if position is None:
                        # Simple entry condition using scalars
                        if price_change > 0.3 and current_price > ma10 and ma10 > ma20:
                            position = current_price
                            entry_date = current_date
                            
                            # Calculate position size
                            risk_amount = self.capital * self.risk_per_trade
                            stop_loss_pct = 2.0
                            stop_loss_price = position * (1 - stop_loss_pct/100)
                            position_size = risk_amount / (position - stop_loss_price)
                            
                            # Set stops and targets as scalar values
                            trailing_stop = stop_loss_price
                            take_profit = position * 1.04
                            
                            # Log entry
                            print(f"\nENTRY {symbol} on {entry_date.strftime('%Y-%m-%d')} at ${position:.2f}")
                            print(f"Stop Loss: ${trailing_stop:.2f}, Take Profit: ${take_profit:.2f}")
                            
                            trades += 1
                    
                    # Check for exit if in a position
                    elif position is not None:
                        exit_price = None
                        exit_reason = ""
                        
                        # Update highest price seen (scalar)
                        if current_high > highest_price:
                            highest_price = current_high
                        
                        # Exit conditions (all scalar comparisons)
                        if current_low <= trailing_stop:
                            exit_price = trailing_stop
                            exit_reason = "Stop Loss"
                        elif current_high >= take_profit:
                            exit_price = take_profit
                            exit_reason = "Take Profit"
                        
                        # Process exit if triggered
                        if exit_price is not None:
                            trade_profit = (exit_price - position) * position_size
                            profit_pct = (exit_price - position) / position * 100
                            
                            self.capital += trade_profit
                            total_profit += trade_profit
                            
                            exit_date = current_date
                            
                            print(f"\nEXIT {symbol} on {exit_date.strftime('%Y-%m-%d')} via {exit_reason}")
                            print(f"Profit: ${trade_profit:.2f} ({profit_pct:.2f}%)")
                            
                            # Record trade
                            self.all_trades.append({
                                'Symbol': symbol,
                                'Entry Date': entry_date,
                                'Exit Date': exit_date,
                                'Entry Price': position,
                                'Exit Price': exit_price,
                                'Position Size': position_size,
                                'Stop Loss': trailing_stop,
                                'Take Profit': take_profit,
                                'Exit Reason': exit_reason,
                                'Profit/Loss $': trade_profit,
                                'Profit/Loss %': profit_pct,
                                'Capital After Trade': self.capital,
                                'Trade Duration': (exit_date - entry_date).days
                            })
                            
                            # Update stats
                            if trade_profit > 0:
                                wins += 1
                            else:
                                losses += 1
                                
                            # Reset position
                            position = None
                            trailing_stop = 0
                            take_profit = 0
                            highest_price = 0
                            entry_date = None
                
                except Exception as e:
                    print(f"Error processing bar {i}: {e}")
                    continue
            
            # Final Trade Stats
            win_rate = wins / trades * 100 if trades > 0 else 0
            
            print(f"\n=== {symbol} Trading Summary ===")
            print(f"Total Trades: {trades}")
            print(f"Win Rate: {win_rate:.1f}% ({wins} wins, {losses} losses)")
            print(f"Total Profit: ${total_profit:.2f}")
            print(f"==============================")
            
            return {
                "symbol": symbol,
                "trades": trades,
                "wins": wins,
                "losses": losses,
                "win_rate": win_rate,
                "profit": total_profit
            }
        
        except Exception as e:
            print(f"Error in backtest for {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return {
                "symbol": symbol,
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0,
                "profit": 0
            }
    
    def run(self, symbols: List[str], start_date: str, end_date: str):
        """Run backtest for multiple symbols"""
        results = []
        total_profit = 0
        total_trades = 0
        winning_trades = 0
        losing_trades = 0
        max_drawdown = 0
        peak_capital = self.initial_capital
        
        print("\nBacktest gestartet...")
        print(f"Startkapital: ${self.initial_capital:,.2f}")
        print(f"Zeitraum: {start_date} bis {end_date}")
        print("-------------------")
        
        # Clear previous trades for this backtest run
        self.all_trades = []
        
        # Tracking für Equity-Kurve
        equity_curve = []
        dates = []
        
        for symbol in symbols:
            try:
                symbol_result = self.run_single_symbol(symbol, start_date, end_date)
                results.append(symbol_result)
                
                total_profit += symbol_result.get('profit', 0)
                total_trades += symbol_result.get('trades', 0)
                winning_trades += symbol_result.get('wins', 0)
                losing_trades += symbol_result.get('losses', 0)
                
                # Drawdown berechnen
                if self.capital > peak_capital:
                    peak_capital = self.capital
                current_drawdown = (peak_capital - self.capital) / peak_capital * 100
                max_drawdown = max(max_drawdown, current_drawdown)
                
                # Equity-Kurve aktualisieren
                equity_curve.append(self.capital)
                dates.append(end_date)  # Vereinfachung - in der Praxis würden wir das genaue Datum verwenden
            except Exception as e:
                print(f"Error processing {symbol}: {e}")
                results.append({
                    "symbol": symbol,
                    "trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "win_rate": 0,
                    "profit": 0
                })
        
        # Ensure all results have consistent keys
        for result in results:
            result.setdefault('wins', 0)
            result.setdefault('losses', 0)
            result.setdefault('win_rate', 0)
        
        # Berechnung der Kennzahlen
        win_rate = winning_trades / total_trades * 100 if total_trades > 0 else 0
        profit_factor = abs(sum([r.get('profit', 0) for r in results if r.get('profit', 0) > 0])) / abs(sum([r.get('profit', 0) for r in results if r.get('profit', 0) < 0])) if sum([r.get('profit', 0) for r in results if r.get('profit', 0) < 0]) != 0 else float('inf')
        
        print("\nGESAMTERGEBNIS DES BACKTESTS")
        print("============================")
        print(f"Startkapital: ${self.initial_capital:,.2f}")
        print(f"Endkapital: ${self.capital:,.2f}")
        print(f"Gesamtrendite: {((self.capital - self.initial_capital) / self.initial_capital * 100):,.2f}%")
        print(f"Gewinn/Verlust: ${total_profit:,.2f}")
        print(f"Anzahl der Trades: {total_trades}")
        print(f"Gewonnene Trades: {winning_trades} ({win_rate:.1f}%)")
        print(f"Verlorene Trades: {losing_trades} ({100-win_rate:.1f}%)")
        print(f"Maximaler Drawdown: {max_drawdown:.2f}%")
        print(f"Profit-Faktor: {profit_factor:.2f}")
        print("============================")
        
        # Export all trades to CSV file
        if self.all_trades:
            # Create a timestamp for the CSV filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            trades_filename = f"trades_report_{timestamp}.csv"
            
            # Convert the list of trade dictionaries to a DataFrame and save to CSV
            trades_df = pd.DataFrame(self.all_trades)
            trades_df.to_csv(trades_filename, index=False)
            print(f"\nDetaillierte Trade-Daten wurden in '{trades_filename}' gespeichert.")
            print(f"Anzahl erfasster Trades: {len(self.all_trades)}")
        else:
            print("\nKeine Trades wurden ausgeführt - keine CSV-Datei erstellt.")
        
        # Optional: Equity-Kurve als Grafik speichern
        try:
            import matplotlib.pyplot as plt
            plt.figure(figsize=(10, 6))
            plt.plot(dates, equity_curve)
            plt.title('Equity-Kurve')
            plt.xlabel('Datum')
            plt.ylabel('Kapital ($)')
            plt.grid(True)
            plt.savefig(f'equity_curve_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png')
            print("Equity-Kurve wurde als Grafik gespeichert.")
        except ImportError:
            print("Matplotlib nicht installiert - keine Equity-Kurve erstellt.")
        
        return results 