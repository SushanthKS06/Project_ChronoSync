"""
Structured Logger for Numatix-Quant Trading System.
Provides unified logging format across all modules.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


# Create logs directory
LOGS_DIR = Path(__file__).parent.parent.parent / 'logs'
LOGS_DIR.mkdir(parents=True, exist_ok=True)


class StructuredFormatter(logging.Formatter):
    """
    Custom formatter for structured logging.
    Format: [TIMESTAMP] [LEVEL] [MODULE] MESSAGE
    """
    
    def format(self, record: logging.LogRecord) -> str:
        # Add custom timestamp format
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        # Module name (last part of logger name)
        module = record.name.split('.')[-1] if '.' in record.name else record.name
        
        # Format the message
        formatted = f"[{timestamp}] [{record.levelname:8}] [{module:20}] {record.getMessage()}"
        
        # Add exception info if present
        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"
        
        return formatted


def get_logger(name: str, level: int = logging.DEBUG) -> logging.Logger:
    """
    Get a configured logger instance.
    
    Args:
        name: Logger name (typically __name__)
        level: Logging level (default DEBUG)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(StructuredFormatter())
    logger.addHandler(console_handler)
    
    # File handler
    log_file = LOGS_DIR / f'numatix_{datetime.now().strftime("%Y%m%d")}.log'
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(StructuredFormatter())
    logger.addHandler(file_handler)
    
    return logger


def log_data_arrival(logger: logging.Logger, symbol: str, timeframe: str, timestamp: datetime, close: float) -> None:
    """Log data arrival event."""
    logger.info(f"DATA ARRIVAL: {symbol} {timeframe} @ {timestamp} close={close:.2f}")


def log_signal(logger: logging.Logger, signal_type: str, details: str) -> None:
    """Log signal generation event."""
    logger.info(f"SIGNAL: {signal_type} - {details}")


def log_order(logger: logging.Logger, side: str, symbol: str, quantity: float, price: Optional[float] = None) -> None:
    """Log order placement event."""
    price_str = f"@ {price:.2f}" if price else "MARKET"
    logger.info(f"ORDER: {side} {quantity} {symbol} {price_str}")


def log_fill(logger: logging.Logger, side: str, symbol: str, quantity: float, fill_price: float) -> None:
    """Log order fill event."""
    logger.info(f"FILL: {side} {quantity} {symbol} @ {fill_price:.2f}")


def get_live_logger(name: str = "LIVE") -> logging.Logger:
    """
    Get a logger specifically for live trading with simplified format.
    
    Format: TIMESTAMP - NAME - LEVEL - message
    Example: 2025-12-29 06:31:23,936 - LIVE - INFO - Starting live trading
    
    Args:
        name: Logger name (default 'LIVE')
    
    Returns:
        Configured logger instance for live trading
    """
    logger = logging.getLogger(name)
    
    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.DEBUG)
    
    # Simple format: timestamp - name - level - message
    simple_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_format)
    logger.addHandler(console_handler)
    
    # File handler
    log_file = LOGS_DIR / f'live_{datetime.now().strftime("%Y%m%d")}.log'
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(simple_format)
    logger.addHandler(file_handler)
    
    return logger
