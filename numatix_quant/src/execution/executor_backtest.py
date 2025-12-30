"""
Backtest Executor - Wrapper for backtesting.py framework.
Adapts the StrategyMultiTF class to work with backtesting.py.

CRITICAL: This wrapper does NOT duplicate strategy logic.
It delegates ALL signal generation to StrategyMultiTF._evaluate_signals().
"""

import sys
import os
from datetime import datetime
from typing import List, Dict, Optional

import pandas as pd
import numpy as np
from backtesting import Strategy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.strategy_base import BarData
from src.core.strategy_multi_tf import StrategyMultiTF
from src.core.trade_intent import TradeIntent, TradeSide, TradeReason
from src.core.position_state import PositionStatus
from src.utils.logger import get_logger, log_signal, log_order, log_fill
from src.utils.csv_writer import format_trade_for_csv
from config.config import (
    SYMBOL, TRADE_QUANTITY, TIMEFRAME_ENTRY, TIMEFRAME_CONFIRMATION,
    EMA_FAST_ENTRY, EMA_SLOW_ENTRY, EMA_FAST_CONFIRMATION, EMA_SLOW_CONFIRMATION,
    STOP_LOSS_PCT, TAKE_PROFIT_PCT, POSITION_TIMEOUT_BARS
)

logger = get_logger(__name__)


class BacktestStrategyWrapper(Strategy):
    """
    Wrapper class that adapts StrategyMultiTF to backtesting.py framework.
    
    CRITICAL DESIGN:
    - ALL signal logic is delegated to StrategyMultiTF
    - This wrapper only handles translation between frameworks
    - Position tracking is synced between backtesting.py and strategy
    """
    
    # Class-level parameters
    ema_fast_entry = EMA_FAST_ENTRY
    ema_slow_entry = EMA_SLOW_ENTRY
    ema_fast_conf = EMA_FAST_CONFIRMATION
    ema_slow_conf = EMA_SLOW_CONFIRMATION
    stop_loss_pct = STOP_LOSS_PCT
    take_profit_pct = TAKE_PROFIT_PCT
    position_timeout = POSITION_TIMEOUT_BARS
    
    # Shared state (class-level for access after backtest)
    _strategy_instance: Optional[StrategyMultiTF] = None
    _trade_log: List[Dict] = []
    _conf_data: Optional[pd.DataFrame] = None
    _last_conf_bar_time: Optional[datetime] = None
    _current_conf_bar: Optional[BarData] = None
    
    def init(self):
        """Initialize strategy wrapper."""
        # Create fresh strategy instance
        self._strategy = StrategyMultiTF(
            symbol=SYMBOL,
            quantity=TRADE_QUANTITY
        )
        
        # Store for external access
        BacktestStrategyWrapper._strategy_instance = self._strategy
        BacktestStrategyWrapper._trade_log = []
        BacktestStrategyWrapper._last_conf_bar_time = None
        BacktestStrategyWrapper._current_conf_bar = None
        
        # Track entry for proper exit logging
        self._entry_price: Optional[float] = None
        self._entry_time: Optional[datetime] = None
        
        logger.info("BacktestStrategyWrapper initialized")
    
    def next(self):
        """
        Called on each bar by backtesting.py.
        Delegates to StrategyMultiTF.on_bar() for signal generation.
        """
        # Get current timestamp
        current_time = self.data.index[-1]
        if hasattr(current_time, 'to_pydatetime'):
            current_time = current_time.to_pydatetime()
        
        # Create BarData for entry timeframe
        bar_entry = BarData(
            timestamp=current_time,
            open=self.data.Open[-1],
            high=self.data.High[-1],
            low=self.data.Low[-1],
            close=self.data.Close[-1],
            volume=self.data.Volume[-1] if hasattr(self.data, 'Volume') and len(self.data.Volume) > 0 else 0
        )
        
        # Get corresponding confirmation bar with proper alignment
        bar_conf = self._get_aligned_conf_bar(current_time)
        
        # SINGLE SOURCE OF TRUTH: Call strategy.on_bar()
        trade_intent = self._strategy.on_bar(bar_entry, bar_conf)
        
        # Execute trade if signal generated
        if trade_intent is not None:
            self._execute_trade(trade_intent, bar_entry)
    
    def _get_aligned_conf_bar(self, timestamp_entry: datetime) -> Optional[BarData]:
        """
        Get the most recent completed confirmation bar for a given entry timestamp.
        """
        if BacktestStrategyWrapper._conf_data is None or BacktestStrategyWrapper._conf_data.empty:
            return None
        
        # Use proper alignment based on configured confirmation interval
        conf_time = None
        if TIMEFRAME_CONFIRMATION.endswith('m'):
            minutes = int(TIMEFRAME_CONFIRMATION[:-1])
            conf_time = timestamp_entry.replace(
                minute=(timestamp_entry.minute // minutes) * minutes,
                second=0, microsecond=0
            )
        elif TIMEFRAME_CONFIRMATION.endswith('h'):
            hours = int(TIMEFRAME_CONFIRMATION[:-1])
            conf_time = timestamp_entry.replace(
                hour=(timestamp_entry.hour // hours) * hours,
                minute=0, second=0, microsecond=0
            )
        else:
            conf_time = timestamp_entry
        
        try:
            # Get bars up to and including the current period
            mask = BacktestStrategyWrapper._conf_data.index <= conf_time
            valid_bars = BacktestStrategyWrapper._conf_data[mask]
            
            if valid_bars.empty:
                return None
            
            # Get the most recent completed bar
            latest_bar_time = valid_bars.index[-1]
            
            # Only update if this is a new bar (optimization)
            if BacktestStrategyWrapper._last_conf_bar_time != latest_bar_time:
                BacktestStrategyWrapper._last_conf_bar_time = latest_bar_time
                row = valid_bars.iloc[-1]
                
                BacktestStrategyWrapper._current_conf_bar = BarData(
                    timestamp=latest_bar_time.to_pydatetime() if hasattr(latest_bar_time, 'to_pydatetime') else latest_bar_time,
                    open=float(row['Open']),
                    high=float(row['High']),
                    low=float(row['Low']),
                    close=float(row['Close']),
                    volume=float(row.get('Volume', 0))
                )
            
            return BacktestStrategyWrapper._current_conf_bar
            
        except Exception as e:
            logger.debug(f"Error getting confirmation bar: {e}")
            return BacktestStrategyWrapper._current_conf_bar
    
    def _execute_trade(self, intent: TradeIntent, bar: BarData) -> None:
        """
        Execute trade based on intent.
        """
        log_signal(logger, intent.reason.value, f"{intent.side.value} {intent.symbol}")
        
        is_entry = intent.reason in [TradeReason.ENTRY_LONG, TradeReason.ENTRY_SHORT]
        
        if is_entry:
            log_order(logger, intent.side.value, intent.symbol, intent.quantity, bar.close)
            if intent.reason == TradeReason.ENTRY_LONG:
                self.buy()
            else:
                self.sell()
            
            # Only log if backtesting.py actually filled the order
            if self.position:
                log_fill(logger, intent.side.value, intent.symbol, intent.quantity, bar.close)
                
                self._entry_price = bar.close
                self._entry_time = intent.timestamp
                
                self._log_trade(
                    timestamp=intent.timestamp,
                    side=intent.side.value,
                    entry_price=bar.close,
                    exit_price=None,
                    reason=intent.reason.value,
                    pnl=None,
                    pnl_pct=None,
                    duration_bars=None
                )
            else:
                logger.warning(f"Order rejected by backtesting.py (likely insufficient margin): {intent.side.value} @ {bar.close}")
        else:
            # Only log exit if we actually have a position to close
            if self.position and self._entry_price:
                log_order(logger, intent.side.value, intent.symbol, intent.quantity, bar.close)
                self.position.close()
                log_fill(logger, intent.side.value, intent.symbol, intent.quantity, bar.close)
                
                entry_price = self._entry_price
                
                self._log_trade(
                    timestamp=intent.timestamp,
                    side=intent.side.value,
                    entry_price=entry_price,
                    exit_price=bar.close,
                    reason=intent.reason.value,
                    pnl=intent.pnl,
                    pnl_pct=intent.pnl_pct,
                    duration_bars=intent.duration_bars
                )
                
                self._entry_price = None
                self._entry_time = None
            else:
                logger.warning(f"Exit signal ignored - no active position to close")
    
    def _log_trade(
        self,
        timestamp: datetime,
        side: str,
        entry_price: float,
        exit_price: Optional[float],
        reason: str,
        pnl: Optional[float],
        pnl_pct: Optional[float] = None,
        duration_bars: Optional[int] = None
    ) -> None:
        """Log trade with extended metadata."""
        trade_data = format_trade_for_csv(
            timestamp=timestamp,
            symbol=SYMBOL,
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=TRADE_QUANTITY,
            reason=reason,
            pnl=pnl,
            pnl_pct=pnl_pct,
            duration_bars=duration_bars
        )
        BacktestStrategyWrapper._trade_log.append(trade_data)
        logger.debug(f"Logged trade: {side} {reason}")
    
    @classmethod
    def get_trade_log(cls) -> List[Dict]:
        """Get all logged trades."""
        return cls._trade_log
    
    @classmethod
    def set_conf_data(cls, data: pd.DataFrame) -> None:
        """Set confirmation timeframe data for multi-timeframe analysis."""
        cls._conf_data = data
        cls._last_conf_bar_time = None
        cls._current_conf_bar = None
        logger.info(f"Set confirmation data with {len(data)} bars")
    
    @classmethod
    def clear_state(cls) -> None:
        """Clear all class-level state."""
        cls._strategy_instance = None
        cls._trade_log = []
        cls._conf_data = None
        cls._last_conf_bar_time = None
        cls._current_conf_bar = None
