"""
Position State Management.
Tracks current position status and entry details.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class PositionStatus(Enum):
    """Current position status."""
    FLAT = "FLAT"
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class PositionState:
    """
    Tracks the current position status and entry details.
    Used by strategy to determine exit conditions and prevent duplicate entries.
    """
    status: PositionStatus = PositionStatus.FLAT
    entry_price: Optional[float] = None
    entry_time: Optional[datetime] = None
    entry_bar_index: Optional[int] = None
    quantity: float = 0.0
    
    def is_flat(self) -> bool:
        """Check if position is flat (no open position)."""
        return self.status == PositionStatus.FLAT
    
    def is_long(self) -> bool:
        """Check if in a long position."""
        return self.status == PositionStatus.LONG
    
    def is_short(self) -> bool:
        """Check if in a short position."""
        return self.status == PositionStatus.SHORT
    
    def open_long(self, price: float, time: datetime, bar_index: int, quantity: float) -> None:
        """Open a long position."""
        self.status = PositionStatus.LONG
        self.entry_price = price
        self.entry_time = time
        self.entry_bar_index = bar_index
        self.quantity = quantity
    
    def open_short(self, price: float, time: datetime, bar_index: int, quantity: float) -> None:
        """Open a short position."""
        self.status = PositionStatus.SHORT
        self.entry_price = price
        self.entry_time = time
        self.entry_bar_index = bar_index
        self.quantity = quantity
    
    def close(self) -> None:
        """Close current position and reset to flat."""
        self.status = PositionStatus.FLAT
        self.entry_price = None
        self.entry_time = None
        self.entry_bar_index = None
        self.quantity = 0.0
    
    def bars_held(self, current_bar_index: int) -> int:
        """Calculate number of bars position has been held."""
        if self.entry_bar_index is None:
            return 0
        return current_bar_index - self.entry_bar_index
    
    def unrealized_pnl_pct(self, current_price: float) -> float:
        """Calculate unrealized PnL percentage."""
        if self.entry_price is None or self.entry_price == 0:
            return 0.0
        
        if self.is_long():
            return (current_price - self.entry_price) / self.entry_price
        elif self.is_short():
            return (self.entry_price - current_price) / self.entry_price
        return 0.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary for logging."""
        return {
            'status': self.status.value,
            'entry_price': self.entry_price,
            'entry_time': self.entry_time.isoformat() if self.entry_time else None,
            'entry_bar_index': self.entry_bar_index,
            'quantity': self.quantity
        }
