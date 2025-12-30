"""
Multi-Timeframe EMA Crossover Strategy.
THIS IS THE SINGLE SOURCE OF TRUTH FOR ALL TRADING LOGIC.
Used by both backtesting and live trading modules.
"""

from datetime import datetime
from typing import Optional, Dict, List
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.strategy_base import StrategyBase, BarData
from src.core.position_state import PositionState, PositionStatus
from src.core.trade_intent import TradeIntent, TradeSide, TradeReason
from config.config import (
    TIMEFRAME_ENTRY, TIMEFRAME_CONFIRMATION,
    EMA_FAST_ENTRY, EMA_SLOW_ENTRY, EMA_FAST_CONFIRMATION, EMA_SLOW_CONFIRMATION,
    POSITION_TIMEOUT_BARS, STOP_LOSS_PCT, TAKE_PROFIT_PCT
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class StrategyMultiTF(StrategyBase):
    """
    Multi-Timeframe EMA Crossover Strategy.
    
    SINGLE SOURCE OF TRUTH - This class is used by:
    - Backtesting module (via wrapper)
    - Live trading module (direct instantiation)
    
    Strategy Rules:
    ---------------
    ENTRY CONDITIONS:
    - Long Entry: Entry EMA Fast crosses ABOVE EMA Slow AND Conf EMA Fast > EMA Slow
    - Short Entry: Entry EMA Fast crosses BELOW EMA Slow AND Conf EMA Fast < EMA Slow
    
    EXIT CONDITIONS (evaluated BEFORE entry):
    - Stop Loss: Position loses more than STOP_LOSS_PCT
    - Take Profit: Position gains more than TAKE_PROFIT_PCT
    - Timeout: Position held longer than POSITION_TIMEOUT_BARS
    - Signal Exit: Opposite crossover on entry timeframe
    
    EMA State Management:
    ---------------------
    CRITICAL: Signal flow is:
    1. Calculate current EMA values
    2. Capture previous EMA values BEFORE update
    3. Evaluate exit conditions
    4. Evaluate entry conditions
    5. Update EMA state for next bar
    """
    
    def __init__(self, symbol: str, quantity: float):
        """
        Initialize strategy with parameters.
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            quantity: Position size
        """
        super().__init__(symbol, quantity)
        
        # EMA parameters
        self.ema_fast_entry_period = EMA_FAST_ENTRY
        self.ema_slow_entry_period = EMA_SLOW_ENTRY
        self.ema_fast_conf_period = EMA_FAST_CONFIRMATION
        self.ema_slow_conf_period = EMA_SLOW_CONFIRMATION
        
        # Position management parameters
        self.position_timeout_bars = POSITION_TIMEOUT_BARS
        self.stop_loss_pct = STOP_LOSS_PCT
        self.take_profit_pct = TAKE_PROFIT_PCT
        
        # EMA state - CURRENT values
        self._ema_fast_entry: Optional[float] = None
        self._ema_slow_entry: Optional[float] = None
        self._ema_fast_conf: Optional[float] = None
        self._ema_slow_conf: Optional[float] = None
        
        # EMA state - PREVIOUS values (for crossover detection)
        self._prev_ema_fast_entry: Optional[float] = None
        self._prev_ema_slow_entry: Optional[float] = None
        self._prev_ema_fast_conf: Optional[float] = None
        self._prev_ema_slow_conf: Optional[float] = None
        
        # Price history for initial EMA calculation
        self._prices_entry: List[float] = []
        self._prices_conf: List[float] = []
        
        # Tracking
        self._warmup_complete_entry = False
        self._warmup_complete_conf = False
        
        logger.info(f"StrategyMultiTF initialized: symbol={symbol}, quantity={quantity}")
        logger.info(f"EMA params: {TIMEFRAME_ENTRY}({self.ema_fast_entry_period}/{self.ema_slow_entry_period}), "
                   f"{TIMEFRAME_CONFIRMATION}({self.ema_fast_conf_period}/{self.ema_slow_conf_period})")
    
    def reset(self) -> None:
        """Reset strategy state for new backtest/session."""
        self.position = PositionState()
        self.bar_index = 0
        
        self._ema_fast_15m = None
        self._ema_slow_15m = None
        self._ema_fast_1h = None
        self._ema_slow_1h = None
        
        self._prev_ema_fast_entry = None
        self._prev_ema_slow_entry = None
        self._prev_ema_fast_conf = None
        self._prev_ema_slow_conf = None
        
        self._prices_entry = []
        self._prices_conf = []
        
        self._warmup_complete_entry = False
        self._warmup_complete_conf = False
        
        logger.info("Strategy state reset")
    
    def _calculate_ema(self, price: float, prev_ema: Optional[float], period: int) -> float:
        """
        Calculate EMA using standard formula.
        
        Args:
            price: Current price
            prev_ema: Previous EMA value (None for first calculation)
            period: EMA period
        
        Returns:
            New EMA value
        """
        multiplier = 2 / (period + 1)
        if prev_ema is None:
            return price
        return (price - prev_ema) * multiplier + prev_ema
    
    def _calculate_initial_sma(self, prices: List[float], period: int) -> Optional[float]:
        """
        Calculate initial SMA for EMA seeding.
        
        Args:
            prices: List of closing prices
            period: SMA period
        
        Returns:
            SMA value or None if insufficient data
        """
        if len(prices) < period:
            return None
        return sum(prices[-period:]) / period
    
    def _update_emas_entry(self, close_price: float) -> None:
        """
        Update entry timeframe EMA values.
        
        CRITICAL: Previous values must be captured BEFORE this call.
        """
        self._prices_entry.append(close_price)
        
        # Check if we have enough data for initial SMA
        if not self._warmup_complete_entry:
            if len(self._prices_entry) >= self.ema_slow_entry_period:
                # Initialize with SMA
                self._ema_fast_entry = self._calculate_initial_sma(
                    self._prices_entry, self.ema_fast_entry_period
                )
                self._ema_slow_entry = self._calculate_initial_sma(
                    self._prices_entry, self.ema_slow_entry_period
                )
                self._warmup_complete_entry = True
                logger.debug(f"Entry EMA warmup complete: fast={self._ema_fast_entry:.2f}, slow={self._ema_slow_entry:.2f}")
            return
        
        # Update EMAs incrementally
        self._ema_fast_entry = self._calculate_ema(
            close_price, self._ema_fast_entry, self.ema_fast_entry_period
        )
        self._ema_slow_entry = self._calculate_ema(
            close_price, self._ema_slow_entry, self.ema_slow_entry_period
        )
    
    def _update_emas_conf(self, close_price: float) -> None:
        """
        Update confirmation timeframe EMA values.
        
        CRITICAL: Previous values must be captured BEFORE this call.
        """
        self._prices_conf.append(close_price)
        
        # Check if we have enough data for initial SMA
        if not self._warmup_complete_conf:
            if len(self._prices_conf) >= self.ema_slow_conf_period:
                # Initialize with SMA
                self._ema_fast_conf = self._calculate_initial_sma(
                    self._prices_conf, self.ema_fast_conf_period
                )
                self._ema_slow_conf = self._calculate_initial_sma(
                    self._prices_conf, self.ema_slow_conf_period
                )
                self._warmup_complete_conf = True
                logger.debug(f"Confirmation EMA warmup complete: fast={self._ema_fast_conf:.2f}, slow={self._ema_slow_conf:.2f}")
            return
        
        # Update EMAs incrementally
        self._ema_fast_conf = self._calculate_ema(
            close_price, self._ema_fast_conf, self.ema_fast_conf_period
        )
        self._ema_slow_conf = self._calculate_ema(
            close_price, self._ema_slow_conf, self.ema_slow_conf_period
        )
    
    def on_bar(self, bar_entry: BarData, bar_conf: Optional[BarData] = None) -> Optional[TradeIntent]:
        """
        Process new bar data and generate trade signals.
        
        This is the main entry point called by both backtest and live runners.
        
        Args:
            bar_entry: Entry timeframe bar data
            bar_conf: Confirmation timeframe bar data (optional, may lag)
        
        Returns:
            TradeIntent if a trade should be executed
        """
        logger.debug(f"on_bar: bar_index={self.bar_index}, close={bar_entry.close:.2f}")
        
        # STEP 1: Capture previous EMA values BEFORE any updates
        self._prev_ema_fast_entry = self._ema_fast_entry
        self._prev_ema_slow_entry = self._ema_slow_entry
        self._prev_ema_fast_conf = self._ema_fast_conf
        self._prev_ema_slow_conf = self._ema_slow_conf
        
        # STEP 2: Update entry EMAs
        self._update_emas_entry(bar_entry.close)
        
        # STEP 3: Update confirmation EMAs if new bar provided
        if bar_conf is not None:
            self._update_emas_conf(bar_conf.close)
        
        # STEP 4: Evaluate signals using _evaluate_signals (SINGLE SOURCE OF TRUTH)
        trade_intent = self._evaluate_signals(bar_entry, bar_conf)
        
        # STEP 5: Increment bar counter
        self.increment_bar_index()
        
        return trade_intent
    
    def _evaluate_signals(self, bar_entry: BarData, bar_conf: Optional[BarData]) -> Optional[TradeIntent]:
        """
        Evaluate trading signals and return TradeIntent.
        """
        # 1. Warmup check
        if not self.is_warmup_complete():
            return None

        # 2. EXIT check
        if not self.position.is_flat():
            # SAME-BAR EXIT PROTECTION: Must hold for at least 1 bar
            # This prevents exiting on the same bar as entry, ensuring:
            # - Deterministic, bar-close-based exit decisions
            # - Live/backtest parity
            # - No zero-PnL trades with identical timestamps
            if self.position.bars_held(self.bar_index) < 1:
                logger.debug(f"Exit blocked: position opened this bar (bar_index={self.bar_index})")
                return None
            
            exit_reason = self.should_exit(bar_entry, self.position)
            if exit_reason:
                # Calculate metrics BEFORE closing position
                pnl_pct = self.position.unrealized_pnl_pct(bar_entry.close)
                pnl = pnl_pct * self.position.entry_price * self.position.quantity
                duration = self.position.bars_held(self.bar_index)
                
                side = TradeSide.SELL if self.position.is_long() else TradeSide.BUY
                intent = TradeIntent(
                    symbol=self.symbol,
                    side=side,
                    quantity=self.quantity,
                    reason=exit_reason,
                    timestamp=bar_entry.timestamp,
                    price=bar_entry.close,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    duration_bars=duration
                )
                self.position.close()
                return intent

        # 3. ENTRY check
        if self.position.is_flat():
            if self.should_enter_long(bar_entry, bar_conf):
                self.position.open_long(bar_entry.close, bar_entry.timestamp, self.bar_index, self.quantity)
                return TradeIntent(
                    symbol=self.symbol,
                    side=TradeSide.BUY,
                    quantity=self.quantity,
                    reason=TradeReason.ENTRY_LONG,
                    timestamp=bar_entry.timestamp,
                    price=bar_entry.close
                )
            
            if self.should_enter_short(bar_entry, bar_conf):
                self.position.open_short(bar_entry.close, bar_entry.timestamp, self.bar_index, self.quantity)
                return TradeIntent(
                    symbol=self.symbol,
                    side=TradeSide.SELL,
                    quantity=self.quantity,
                    reason=TradeReason.ENTRY_SHORT,
                    timestamp=bar_entry.timestamp,
                    price=bar_entry.close
                )
        
        return None

    def should_enter_long(self, bar_entry: BarData, bar_conf: Optional[BarData]) -> bool:
        """
        Long Entry: Entry EMA Fast crosses ABOVE EMA Slow AND confirmation trend is bullish
        """
        if bar_conf is None: return False
        
        trend_bullish = self._ema_fast_conf > self._ema_slow_conf
        bullish_crossover = (
            self._prev_ema_fast_entry is not None and
            self._prev_ema_slow_entry is not None and
            self._prev_ema_fast_entry <= self._prev_ema_slow_entry and
            self._ema_fast_entry > self._ema_slow_entry
        )
        
        if bullish_crossover and trend_bullish:
            logger.info(f"SIGNAL LONG: Crossover + Bullish Trend ({TIMEFRAME_CONFIRMATION})")
            return True
        return False

    def should_enter_short(self, bar_entry: BarData, bar_conf: Optional[BarData]) -> bool:
        """
        Short Entry: Entry EMA Fast crosses BELOW EMA Slow AND confirmation trend is bearish
        """
        if bar_conf is None: return False

        trend_bearish = self._ema_fast_conf < self._ema_slow_conf
        bearish_crossover = (
            self._prev_ema_fast_entry is not None and
            self._prev_ema_slow_entry is not None and
            self._prev_ema_fast_entry >= self._prev_ema_slow_entry and
            self._ema_fast_entry < self._ema_slow_entry
        )

        if bearish_crossover and trend_bearish:
            logger.info(f"SIGNAL SHORT: Crossover + Bearish Trend ({TIMEFRAME_CONFIRMATION})")
            return True
        return False

    def should_exit(self, bar_entry: BarData, position: PositionState) -> Optional[TradeReason]:
        """
        Check for exit signals.
        """
        current_price = bar_entry.close
        pnl_pct = position.unrealized_pnl_pct(current_price)
        bars_held = position.bars_held(self.bar_index)

        # 1. Stop Loss
        if pnl_pct <= -self.stop_loss_pct:
            return TradeReason.EXIT_STOP_LOSS

        # 2. Take Profit
        if pnl_pct >= self.take_profit_pct:
            return TradeReason.EXIT_TAKE_PROFIT

        # 3. Timeout
        if bars_held >= self.position_timeout_bars:
            return TradeReason.EXIT_TIMEOUT

        # 4. Signal Exit (Opposite Crossover)
        if position.is_long():
            # Exit long if bearish crossover
            if (self._prev_ema_fast_entry > self._prev_ema_slow_entry and 
                self._ema_fast_entry <= self._ema_slow_entry):
                return TradeReason.EXIT_SIGNAL
        else: # Short
            # Exit short if bullish crossover
            if (self._prev_ema_fast_entry < self._prev_ema_slow_entry and 
                self._ema_fast_entry >= self._ema_slow_entry):
                return TradeReason.EXIT_SIGNAL

        return None
        
        return None
    
    def get_ema_state(self) -> Dict:
        """Get current EMA state for debugging/logging."""
        return {
            'ema_fast_entry': self._ema_fast_entry,
            'ema_slow_entry': self._ema_slow_entry,
            'ema_fast_conf': self._ema_fast_conf,
            'ema_slow_conf': self._ema_slow_conf,
            'warmup_complete_entry': self._warmup_complete_entry,
            'warmup_complete_conf': self._warmup_complete_conf,
            'prices_entry_count': len(self._prices_entry),
            'prices_conf_count': len(self._prices_conf)
        }
    
    def is_warmup_complete(self) -> bool:
        """Check if both timeframes have completed warmup."""
        return self._warmup_complete_entry and self._warmup_complete_conf
