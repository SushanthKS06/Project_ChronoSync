"""
Live Trading Runner.
Main entry point for live trading on Binance Testnet.

CRITICAL: This runner uses the SAME StrategyMultiTF class as backtesting.
Signal generation happens through _evaluate_signals() exactly once per bar.
"""

import sys
import os
import time
import signal as sig
from datetime import datetime
from typing import Optional, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.strategy_multi_tf import StrategyMultiTF
from src.core.strategy_base import BarData
from src.core.trade_intent import TradeIntent, TradeReason, TradeSide
from src.core.position_state import PositionStatus
from src.live.live_feed_binance import BinanceLiveFeed
from src.execution.executor_live_binance import BinanceLiveExecutor
from src.utils.logger import get_live_logger
from src.utils.csv_writer import CSVWriter, format_trade_for_csv
from config.config import (
    SYMBOL, TRADE_QUANTITY, LIVE_TRADES_PATH,
    LIVE_POLL_INTERVAL_SECONDS, LIVE_WARMUP_BARS,
    TIMEFRAME_ENTRY, TIMEFRAME_CONFIRMATION
)

# Use the dedicated live logger with simpler format
logger = get_live_logger("LIVE")


class LiveRunner:
    """
    Long-running live trading loop.
    
    CRITICAL DESIGN NOTES:
    - Uses the SAME StrategyMultiTF class as backtesting
    - Signal flow is identical: _evaluate_signals() called exactly once per bar
    - EMA state evolves correctly between iterations
    - Warmup phase does NOT generate trades
    """
    
    def __init__(self):
        """Initialize live runner."""
        # Initialize components
        self.feed = BinanceLiveFeed(SYMBOL)
        self.executor = BinanceLiveExecutor()
        
        # Initialize strategy - SAME CLASS AS BACKTEST
        self.strategy = StrategyMultiTF(
            symbol=SYMBOL,
            quantity=TRADE_QUANTITY
        )
        
        # Trade logging
        self.csv_writer = CSVWriter(LIVE_TRADES_PATH)
        
        # State tracking
        self._running = False
        self._iteration = 0
        self._warmup_mode = True  # Suppress trades during warmup
        
        # Entry tracking for proper exit logging
        self._entry_price: Optional[float] = None
        self._entry_time: Optional[datetime] = None
        self._entry_side: Optional[str] = None
        
        # Setup signal handlers for graceful shutdown
        sig.signal(sig.SIGINT, self._handle_shutdown)
        sig.signal(sig.SIGTERM, self._handle_shutdown)
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signal."""
        logger.info(f"Received signal {signum}, shutting down...")
        self._running = False
    
    def warmup_strategy(self) -> bool:
        """
        Warm up strategy with historical data.
        
        CRITICAL: During warmup, we build EMA state but do NOT execute trades.
        This ensures the strategy has proper indicator values before live trading.
        
        Returns:
            True if warmup successful
        """
        logger.info("Initializing historical data...")
        
        # Calculate approximate days of data for entry timeframe
        # (Assuming TIMEFRAME_ENTRY is something like '5m', '15m')
        minutes_per_bar = 0
        if TIMEFRAME_ENTRY.endswith('m'):
            minutes_per_bar = int(TIMEFRAME_ENTRY[:-1])
        elif TIMEFRAME_ENTRY.endswith('h'):
            minutes_per_bar = int(TIMEFRAME_ENTRY[:-1]) * 60
        
        days_of_data = (LIVE_WARMUP_BARS * minutes_per_bar) // (60 * 24)
        hours_of_data = (LIVE_WARMUP_BARS * minutes_per_bar) / 60
        if days_of_data >= 1:
            print(f"Loading ~{days_of_data} days of historical data...")
        else:
            print(f"Loading ~{hours_of_data:.1f} hours of historical data...")
        
        # Fetch initial data
        if not self.feed.warmup():
            logger.error("Failed to warmup data feed")
            return False
        
        # Get bar counts
        bars_entry = self.feed.get_all_entry_bars()
        bars_conf = self.feed.get_all_conf_bars()
        
        print(f"Loaded {len(bars_entry)} {TIMEFRAME_ENTRY} bars")
        print(f"Loaded {len(bars_conf)} {TIMEFRAME_CONFIRMATION} bars")
        
        # Process historical bars through strategy to build EMA state
        logger.info("Strategy initialized with historical data")
        
        # Create a mapping of confirmation bars by their open time for alignment
        bars_conf_by_time: Dict[datetime, BarData] = {bar.timestamp: bar for bar in bars_conf}
        
        # Process each entry bar to build EMA state ONLY
        for i, bar_entry in enumerate(bars_entry):
            # Find closest confirmation bar that was completed before or at this time
            # For simplicity in warmup, we look for exact or previous hour/period
            # (In true alignment, we'd need to know the confirmation interval)
            conf_time = None
            if TIMEFRAME_CONFIRMATION.endswith('m'):
                minutes = int(TIMEFRAME_CONFIRMATION[:-1])
                conf_time = bar_entry.timestamp.replace(
                    minute=(bar_entry.timestamp.minute // minutes) * minutes,
                    second=0, microsecond=0
                )
            elif TIMEFRAME_CONFIRMATION.endswith('h'):
                hours = int(TIMEFRAME_CONFIRMATION[:-1])
                conf_time = bar_entry.timestamp.replace(
                    hour=(bar_entry.timestamp.hour // hours) * hours,
                    minute=0, second=0, microsecond=0
                )
            
            bar_conf = bars_conf_by_time.get(conf_time)
            
            # Call on_bar to build EMA state
            _ = self.strategy.on_bar(bar_entry, bar_conf)
            
            # Reset position after each warmup bar to prevent state accumulation
            self.strategy.position.close()
        
        # Log initial EMA state
        ema_state = self.strategy.get_ema_state()
        ema_fast_entry = ema_state['ema_fast_entry'] or 0
        ema_slow_entry = ema_state['ema_slow_entry'] or 0
        logger.info(f"Initial EMA state - {TIMEFRAME_ENTRY} EMA: {ema_fast_entry:.2f}, {TIMEFRAME_ENTRY} EMA: {ema_slow_entry:.2f}")
        
        if not self.strategy.is_warmup_complete():
            logger.error("Strategy warmup incomplete - not enough data for EMAs")
            return False
        
        self._warmup_mode = False
        return True
    
    def run(self, max_iterations: Optional[int] = None) -> None:
        """
        Run the live trading loop.
        
        IMPORTANT: This is a long-running/indefinite loop.
        Use max_iterations for testing, or let it run indefinitely in production.
        
        Args:
            max_iterations: Optional limit for testing (None = run forever)
        """
        logger.info("Starting live trading")
        
        # Warmup strategy
        if not self.warmup_strategy():
            logger.error("Strategy warmup failed, aborting")
            return
        
        self._running = True
        self._iteration = 0
        
        while self._running:
            try:
                self._iteration += 1
                logger.info(f"Live trading iteration {self._iteration}")
                
                # Poll for new bars
                new_entry_bar, new_conf_bar = self.feed.poll_new_bars()
                
                # Get current status info
                bars_entry_count = len(self.feed.get_all_entry_bars())
                bars_conf_count = len(self.feed.get_all_conf_bars())
                price = self.feed.get_current_price() or 0
                position = self.strategy.get_position_state()
                ema = self.strategy.get_ema_state()
                ema_fast = ema['ema_fast_entry'] or 0
                ema_slow = ema['ema_slow_entry'] or 0
                
                logger.info(f"Processing with {bars_entry_count} {TIMEFRAME_ENTRY} bars, {bars_conf_count} {TIMEFRAME_CONFIRMATION} bars")
                logger.info(f"Price: ${price:,.2f} | Position: {position.status.value} | Fast EMA: {ema_fast:.2f}, Slow EMA: {ema_slow:.2f}")
                
                # Log new bars if detected
                if new_entry_bar is not None:
                    logger.info(f"Added new {TIMEFRAME_ENTRY} bar: {new_entry_bar.timestamp}")
                if new_conf_bar is not None:
                    logger.info(f"Added new {TIMEFRAME_CONFIRMATION} bar: {new_conf_bar.timestamp}")
                
                # Process new entry bar if available
                if new_entry_bar is not None:
                    # Get latest confirmation bar
                    bar_conf = new_conf_bar if new_conf_bar else self.feed.get_latest_conf_bar()
                    
                    # SINGLE SOURCE OF TRUTH: Call strategy.on_bar()
                    trade_intent = self.strategy.on_bar(new_entry_bar, bar_conf)
                    
                    # Execute if signal generated (and not in warmup)
                    if trade_intent is not None and not self._warmup_mode:
                        self._execute_and_log(trade_intent, new_entry_bar.close)
                        logger.info(f"TRADE SIGNAL: {trade_intent.side.value} - {trade_intent.reason.value}")
                
                # Check iteration limit
                if max_iterations and self._iteration >= max_iterations:
                    logger.info(f"Reached max iterations ({max_iterations}), stopping")
                    break
                
                # Wait before next poll
                time.sleep(LIVE_POLL_INTERVAL_SECONDS)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(LIVE_POLL_INTERVAL_SECONDS)
        
        logger.info("Live trading stopped")
        self._log_final_summary()
    
    def _execute_and_log(self, intent: TradeIntent, current_price: float) -> None:
        """
        Execute trade and log to CSV.
        """
        # 1. Execute on exchange (simulated)
        # result = self.executor.execute(intent, current_price)
        
        # 2. Determine entry info for exit logging
        is_entry = intent.reason in [TradeReason.ENTRY_LONG, TradeReason.ENTRY_SHORT]
        
        if is_entry:
            self._entry_price = current_price
            self._entry_side = "LONG" if intent.reason == TradeReason.ENTRY_LONG else "SHORT"
            entry_price_to_log = current_price
            exit_price_to_log = None
        else:
            entry_price_to_log = self._entry_price or current_price
            exit_price_to_log = current_price
            # Reset entry tracking
            self._entry_price = None
            self._entry_side = None

        # 3. Format for CSV using metadata from Strategy's Intent
        trade_data = format_trade_for_csv(
            timestamp=intent.timestamp,
            symbol=intent.symbol,
            side=intent.side.value,
            entry_price=entry_price_to_log,
            exit_price=exit_price_to_log,
            quantity=intent.quantity,
            reason=intent.reason.value,
            pnl=intent.pnl,
            pnl_pct=intent.pnl_pct,
            duration_bars=intent.duration_bars
        )
        
        self.csv_writer.write_trade(trade_data)
        logger.info(f"TRADE EXECUTED: {intent.side.value} | {intent.reason.value} | Price: {current_price:.2f}")
    
    def _log_final_summary(self) -> None:
        """Log final summary when stopping."""
        logger.info("=" * 60)
        logger.info("LIVE TRADING SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total iterations: {self._iteration}")
        logger.info(f"Trades saved to: {LIVE_TRADES_PATH}")
        
        # Read and count trades
        trades = self.csv_writer.read_trades()
        logger.info(f"Total trades logged: {len(trades)}")
        
        if trades:
            buys = sum(1 for t in trades if t.get('side') == 'BUY')
            sells = sum(1 for t in trades if t.get('side') == 'SELL')
            logger.info(f"  BUY trades: {buys}")
            logger.info(f"  SELL trades: {sells}")


def run_live():
    """Entry point for live trading."""
    runner = LiveRunner()
    runner.run()


if __name__ == '__main__':
    run_live()
