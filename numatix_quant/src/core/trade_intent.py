"""
Trade Intent and Trade Result data structures.
Defines the data classes used for communicating trade signals and results.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class TradeSide(Enum):
    """Trade direction enumeration."""
    BUY = "BUY"
    SELL = "SELL"


class TradeReason(Enum):
    """Reason for trade execution."""
    ENTRY_LONG = "ENTRY_LONG"
    ENTRY_SHORT = "ENTRY_SHORT"
    EXIT_STOP_LOSS = "EXIT_STOP_LOSS"
    EXIT_TAKE_PROFIT = "EXIT_TAKE_PROFIT"
    EXIT_TIMEOUT = "EXIT_TIMEOUT"
    EXIT_SIGNAL = "EXIT_SIGNAL"
    CLOSE_LONG = "CLOSE_LONG"
    CLOSE_SHORT = "CLOSE_SHORT"


@dataclass
class TradeIntent:
    """
    Represents intention to execute a trade.
    """
    symbol: str
    side: TradeSide
    quantity: float
    reason: TradeReason
    timestamp: datetime
    price: Optional[float] = None  # execution price
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    duration_bars: Optional[int] = None
    
    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'side': self.side.value,
            'quantity': self.quantity,
            'reason': self.reason.value,
            'timestamp': self.timestamp.isoformat(),
            'price': self.price,
            'pnl': self.pnl,
            'pnl_pct': self.pnl_pct,
            'duration_bars': self.duration_bars
        }


@dataclass
class TradeResult:
    """
    Result of an executed trade.
    """
    timestamp: datetime
    symbol: str
    side: str
    entry_price: float
    exit_price: Optional[float]
    quantity: float
    reason: str
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    duration_bars: Optional[int] = None
    
    def to_csv_row(self) -> dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'symbol': self.symbol,
            'side': self.side,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price if self.exit_price else '',
            'quantity': self.quantity,
            'reason': self.reason,
            'pnl': self.pnl if self.pnl is not None else '',
            'pnl_pct': self.pnl_pct if self.pnl_pct is not None else '',
            'duration_bars': self.duration_bars if duration_bars is not None else ''
        }
