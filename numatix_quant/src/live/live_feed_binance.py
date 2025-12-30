"""
Binance Live Data Feed.
Handles fetching real-time and historical data from Binance Testnet.
"""

import sys
import os
import time
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Tuple
from urllib.parse import urlencode

import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.strategy_base import BarData
from src.utils.logger import get_logger, log_data_arrival
from config.config import (
    BINANCE_API_BASE_URL, BINANCE_TESTNET_API_KEY, BINANCE_TESTNET_API_SECRET,
    SYMBOL, TIMEFRAME_ENTRY, TIMEFRAME_CONFIRMATION, LIVE_WARMUP_BARS
)

logger = get_logger(__name__)


class BinanceLiveFeed:
    """
    Handles live data fetching from Binance Testnet.
    
    Features:
    - Fetches historical klines for warmup
    - Polls for new klines
    - Maintains rolling data buffers
    """
    
    def __init__(self, symbol: str = SYMBOL):
        """
        Initialize Binance feed.
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
        """
        self.symbol = symbol
        self.base_url = BINANCE_API_BASE_URL
        self.api_key = BINANCE_TESTNET_API_KEY
        self.api_secret = BINANCE_TESTNET_API_SECRET
        
        # Rolling data buffers
        self._bars_entry: List[BarData] = []
        self._bars_conf: List[BarData] = []
        
        # Track last bar timestamps to detect new bars
        self._last_entry_timestamp: Optional[datetime] = None
        self._last_conf_timestamp: Optional[datetime] = None
        
        logger.info(f"BinanceLiveFeed initialized for {symbol}")
    
    def _sign_request(self, params: Dict) -> Dict:
        """Sign request with HMAC-SHA256."""
        if not self.api_secret:
            return params
        
        params['timestamp'] = int(time.time() * 1000)
        query_string = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        params['signature'] = signature
        return params
    
    def _get_headers(self) -> Dict:
        """Get request headers."""
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['X-MBX-APIKEY'] = self.api_key
        return headers
    
    def fetch_klines(
        self,
        interval: str,
        limit: int = 500,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None
    ) -> List[Dict]:
        """
        Fetch klines from Binance.
        
        Args:
            interval: Kline interval ('15m', '1h', etc.)
            limit: Number of klines to fetch
            start_time: Start timestamp (ms)
            end_time: End timestamp (ms)
        
        Returns:
            List of kline dictionaries
        """
        url = f"{self.base_url}/api/v3/klines"
        
        params = {
            'symbol': self.symbol,
            'interval': interval,
            'limit': limit
        }
        
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            klines = response.json()
            
            result = []
            for k in klines:
                result.append({
                    'timestamp': datetime.fromtimestamp(k[0] / 1000),
                    'open': float(k[1]),
                    'high': float(k[2]),
                    'low': float(k[3]),
                    'close': float(k[4]),
                    'volume': float(k[5]),
                    'close_time': datetime.fromtimestamp(k[6] / 1000)
                })
            
            return result
            
        except requests.RequestException as e:
            logger.error(f"Error fetching klines: {e}")
            return []
    
    def warmup(self) -> bool:
        """
        Load historical data for strategy warmup.
        
        Fetches enough bars to initialize EMAs for both timeframes.
        
        Returns:
            True if warmup successful
        """
        logger.info("Starting data warmup...")
        
        # Fetch entry historical data
        logger.info(f"Fetching {LIVE_WARMUP_BARS} {TIMEFRAME_ENTRY} bars for warmup...")
        klines_entry = self.fetch_klines(TIMEFRAME_ENTRY, limit=LIVE_WARMUP_BARS)
        
        if len(klines_entry) < LIVE_WARMUP_BARS:
            logger.warning(f"Only got {len(klines_entry)} {TIMEFRAME_ENTRY} bars, expected {LIVE_WARMUP_BARS}")
        
        self._bars_entry = [BarData.from_dict(k) for k in klines_entry]
        
        if self._bars_entry:
            self._last_entry_timestamp = self._bars_entry[-1].timestamp
        
        logger.info(f"Loaded {len(self._bars_entry)} {TIMEFRAME_ENTRY} bars")
        
        # Fetch confirmation historical data
        logger.info(f"Fetching {LIVE_WARMUP_BARS} {TIMEFRAME_CONFIRMATION} bars for warmup...")
        klines_conf = self.fetch_klines(TIMEFRAME_CONFIRMATION, limit=LIVE_WARMUP_BARS)
        
        if len(klines_conf) < LIVE_WARMUP_BARS:
            logger.warning(f"Only got {len(klines_conf)} {TIMEFRAME_CONFIRMATION} bars, expected {LIVE_WARMUP_BARS}")
        
        self._bars_conf = [BarData.from_dict(k) for k in klines_conf]
        
        if self._bars_conf:
            self._last_conf_timestamp = self._bars_conf[-1].timestamp
        
        logger.info(f"Loaded {len(self._bars_conf)} {TIMEFRAME_CONFIRMATION} bars")
        
        logger.info("Warmup complete")
        return len(self._bars_entry) > 0 and len(self._bars_conf) > 0
    
    def poll_new_bars(self) -> Tuple[Optional[BarData], Optional[BarData]]:
        """
        Poll for new completed bars.
        
        Strict Detection Mechanism:
        1. Fetch last 2 klines (0=fully closed, 1=currently forming)
        2. Verify if kline[0] timestamp is newer than our last seen
        3. If yes, it's a new closed candle
        """
        new_entry_bar = None
        new_conf_bar = None
        
        # Poll entry timeframe
        klines_entry = self.fetch_klines(TIMEFRAME_ENTRY, limit=2)
        if len(klines_entry) >= 2:
            # Index -2 is the MOST RECENTLY CLOSED candle
            closed_kline = klines_entry[-2]
            ts = closed_kline['timestamp']
            
            if self._last_entry_timestamp is None or ts > self._last_entry_timestamp:
                new_entry_bar = BarData.from_dict(closed_kline)
                self._bars_entry.append(new_entry_bar)
                self._last_entry_timestamp = ts
                logger.info(f"DETECTED NEW {TIMEFRAME_ENTRY} BAR @ {ts} | Close: {new_entry_bar.close}")
                
                # Buffer management
                if len(self._bars_entry) > LIVE_WARMUP_BARS + 100:
                    self._bars_entry = self._bars_entry[-LIVE_WARMUP_BARS:]
        
        # Poll confirmation timeframe
        klines_conf = self.fetch_klines(TIMEFRAME_CONFIRMATION, limit=2)
        if len(klines_conf) >= 2:
            closed_kline = klines_conf[-2]
            ts = closed_kline['timestamp']
            
            if self._last_conf_timestamp is None or ts > self._last_conf_timestamp:
                new_conf_bar = BarData.from_dict(closed_kline)
                self._bars_conf.append(new_conf_bar)
                self._last_conf_timestamp = ts
                logger.info(f"DETECTED NEW {TIMEFRAME_CONFIRMATION} BAR @ {ts} | Close: {new_conf_bar.close}")

                # Buffer management
                if len(self._bars_conf) > LIVE_WARMUP_BARS + 100:
                    self._bars_conf = self._bars_conf[-LIVE_WARMUP_BARS:]

        return new_entry_bar, new_conf_bar
    
    def get_latest_entry_bar(self) -> Optional[BarData]:
        """Get the latest entry timeframe bar from buffer."""
        return self._bars_entry[-1] if self._bars_entry else None
    
    def get_latest_conf_bar(self) -> Optional[BarData]:
        """Get the latest confirmation timeframe bar from buffer."""
        return self._bars_conf[-1] if self._bars_conf else None
    
    def get_all_entry_bars(self) -> List[BarData]:
        """Get all entry timeframe bars in buffer."""
        return self._bars_entry.copy()
    
    def get_all_conf_bars(self) -> List[BarData]:
        """Get all confirmation timeframe bars in buffer."""
        return self._bars_conf.copy()
    
    def get_current_price(self) -> Optional[float]:
        """Get current price from latest bar."""
        bar = self.get_latest_entry_bar()
        return bar.close if bar else None
