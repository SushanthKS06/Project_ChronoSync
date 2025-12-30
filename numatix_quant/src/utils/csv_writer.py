"""
CSV Writer Utilities for Trade Logging.
Handles writing trade data to CSV files.
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.utils.logger import get_logger

logger = get_logger(__name__)


# CSV Headers - Unified for Backtest & Live
TRADE_CSV_HEADERS = [
    'timestamp',
    'symbol', 
    'side',
    'entry_price',
    'exit_price',
    'quantity',
    'reason',
    'pnl',
    'pnl_pct',
    'duration_bars'
]


class CSVWriter:
    """
    Handles CSV file writing for trade logs.
    """
    
    def __init__(self, filepath: Path):
        """
        Initialize CSV writer.
        
        Args:
            filepath: Path to CSV file
        """
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_headers()
    
    def _ensure_headers(self) -> None:
        """Ensure CSV file has headers."""
        if not self.filepath.exists():
            with open(self.filepath, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=TRADE_CSV_HEADERS)
                writer.writeheader()
            logger.info(f"Created CSV file with headers: {self.filepath}")
    
    def write_trade(self, trade_data: Dict) -> None:
        """
        Write a single trade to CSV.
        
        Args:
            trade_data: Dictionary with trade fields
        """
        with open(self.filepath, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=TRADE_CSV_HEADERS)
            
            # Ensure all required fields exist
            row = {header: trade_data.get(header, '') for header in TRADE_CSV_HEADERS}
            writer.writerow(row)
        
        logger.debug(f"Wrote trade to CSV: {trade_data.get('side')} {trade_data.get('symbol')}")
    
    def write_trades(self, trades: List[Dict]) -> None:
        """
        Write multiple trades to CSV.
        
        Args:
            trades: List of trade dictionaries
        """
        with open(self.filepath, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=TRADE_CSV_HEADERS)
            
            for trade_data in trades:
                row = {header: trade_data.get(header, '') for header in TRADE_CSV_HEADERS}
                writer.writerow(row)
        
        logger.info(f"Wrote {len(trades)} trades to CSV: {self.filepath}")
    
    def read_trades(self) -> List[Dict]:
        """
        Read all trades from CSV.
        
        Returns:
            List of trade dictionaries
        """
        if not self.filepath.exists():
            return []
        
        trades = []
        with open(self.filepath, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                trades.append(dict(row))
        
        logger.debug(f"Read {len(trades)} trades from CSV: {self.filepath}")
        return trades
    
    def clear(self) -> None:
        """Clear the CSV file and rewrite headers."""
        with open(self.filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=TRADE_CSV_HEADERS)
            writer.writeheader()
        logger.info(f"Cleared CSV file: {self.filepath}")


def format_trade_for_csv(
    timestamp: datetime,
    symbol: str,
    side: str,
    entry_price: float,
    exit_price: Optional[float] = None,
    quantity: float = 0.0,
    reason: str = '',
    pnl: Optional[float] = None,
    pnl_pct: Optional[float] = None,
    duration_bars: Optional[int] = None
) -> Dict:
    """
    Format trade data for CSV writing.
    """
    return {
        'timestamp': timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp),
        'symbol': symbol,
        'side': side,
        'entry_price': f"{entry_price:.8f}" if entry_price else '0.00000000',
        'exit_price': f"{exit_price:.8f}" if exit_price else '0.00000000',
        'quantity': f"{quantity:.8f}" if quantity else '0.00000000',
        'reason': reason,
        'pnl': f"{pnl:.8f}" if pnl is not None else '0.00000000',
        'pnl_pct': f"{pnl_pct:.4f}" if pnl_pct is not None else '0.0000',
        'duration_bars': str(duration_bars) if duration_bars is not None else '0'
    }
