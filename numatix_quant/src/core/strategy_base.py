"""
Abstract Strategy Base Class.
Defines the interface that all strategy implementations must follow.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

import pandas as pd

from src.core.position_state import PositionState
from src.core.trade_intent import TradeIntent, TradeReason


@dataclass
class BarData:
    """
    Represents a single OHLCV bar.
    """
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    @classmethod
    def from_dict(cls, data: dict) -> 'BarData':
        """Create BarData from dictionary."""
        return cls(
            timestamp=data['timestamp'] if isinstance(data['timestamp'], datetime) else pd.to_datetime(data['timestamp']),
            open=float(data['open']),
            high=float(data['high']),
            low=float(data['low']),
            close=float(data['close']),
            volume=float(data['volume'])
        )


class StrategyBase(ABC):
    """
    Abstract base class for trading strategies.
    All strategy implementations must inherit from this class.
    """
    
    def __init__(self, symbol: str, quantity: float):
        """
        Initialize strategy.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            quantity: Position size for trades
        """
        self.symbol = symbol
        self.quantity = quantity
        self.position = PositionState()
        self.bar_index = 0
    
    @abstractmethod
    def on_bar(self, bar_entry: BarData, bar_conf: Optional[BarData] = None) -> Optional[TradeIntent]:
        """
        Called on each new bar. Main entry point for strategy logic.
        """
        pass
    
    @abstractmethod
    def _evaluate_signals(self, bar_entry: BarData, bar_conf: Optional[BarData]) -> Optional[TradeIntent]:
        """
        Evaluate trading signals and return TradeIntent.
        """
        pass

    @abstractmethod
    def should_enter_long(self, bar_entry: BarData, bar_conf: Optional[BarData]) -> bool:
        """Check for long entry signal."""
        pass

    @abstractmethod
    def should_enter_short(self, bar_entry: BarData, bar_conf: Optional[BarData]) -> bool:
        """Check for short entry signal."""
        pass

    @abstractmethod
    def should_exit(self, bar_entry: BarData, position: PositionState) -> Optional[TradeReason]:
        """Check for exit signal."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset strategy state for new backtest/session."""
        pass
    
    def get_position_state(self) -> PositionState:
        """Get current position state."""
        return self.position
    
    def increment_bar_index(self) -> None:
        """Increment internal bar counter."""
        self.bar_index += 1
