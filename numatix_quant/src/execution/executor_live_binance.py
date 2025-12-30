"""
Live Binance Testnet Executor.
Handles order execution on Binance Testnet.
"""

import sys
import os
import time
import hmac
import hashlib
from datetime import datetime
from typing import Optional, Dict
from urllib.parse import urlencode

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.trade_intent import TradeIntent, TradeSide, TradeResult
from src.utils.logger import get_logger, log_order, log_fill
from config.config import (
    BINANCE_TRADING_URL, BINANCE_TESTNET_API_KEY, BINANCE_TESTNET_API_SECRET,
    SYMBOL
)

logger = get_logger(__name__)


class BinanceLiveExecutor:
    """
    Executes trades on Binance Testnet via REST API.
    
    Handles:
    - Order placement (market orders)
    - Order tracking
    - Fill confirmation
    """
    
    def __init__(self):
        """Initialize executor."""
        self.base_url = BINANCE_TRADING_URL
        self.api_key = BINANCE_TESTNET_API_KEY
        self.api_secret = BINANCE_TESTNET_API_SECRET
        
        # Track pending and completed orders
        self._pending_orders: Dict[str, TradeIntent] = {}
        self._completed_orders: Dict[str, TradeResult] = {}
        
        logger.info("BinanceLiveExecutor initialized")
        
        if not self.api_key or not self.api_secret:
            logger.warning("API credentials not configured - orders will be simulated")
    
    def _sign_request(self, params: Dict) -> Dict:
        """Sign request with HMAC-SHA256."""
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
        return {
            'Content-Type': 'application/json',
            'X-MBX-APIKEY': self.api_key
        }
    
    def execute(self, intent: TradeIntent, current_price: float) -> Optional[TradeResult]:
        """
        Execute a trade based on intent.
        
        Args:
            intent: TradeIntent describing the trade
            current_price: Current market price for fill estimation
        
        Returns:
            TradeResult if successful, None otherwise
        """
        log_order(logger, intent.side.value, intent.symbol, intent.quantity, current_price)
        
        # Check if credentials are configured
        if not self.api_key or not self.api_secret:
            # Simulate execution for testing
            return self._simulate_execution(intent, current_price)
        
        # Execute real order
        return self._execute_real_order(intent, current_price)
    
    def _simulate_execution(self, intent: TradeIntent, current_price: float) -> TradeResult:
        """
        Simulate order execution when API credentials not available.
        
        Args:
            intent: TradeIntent
            current_price: Simulated fill price
        
        Returns:
            TradeResult with simulated fill
        """
        logger.info(f"SIMULATED: {intent.side.value} {intent.quantity} {intent.symbol} @ {current_price:.2f}")
        
        fill_price = current_price
        
        result = TradeResult(
            timestamp=intent.timestamp,
            symbol=intent.symbol,
            side=intent.side.value,
            entry_price=fill_price,
            exit_price=None,
            quantity=intent.quantity,
            reason=intent.reason.value
        )
        
        log_fill(logger, intent.side.value, intent.symbol, intent.quantity, fill_price)
        
        return result
    
    def _execute_real_order(self, intent: TradeIntent, current_price: float) -> Optional[TradeResult]:
        """
        Execute real order on Binance Testnet.
        
        Args:
            intent: TradeIntent
            current_price: Current price for reference
        
        Returns:
            TradeResult if successful
        """
        url = f"{self.base_url}/api/v3/order"
        
        params = {
            'symbol': intent.symbol,
            'side': intent.side.value,
            'type': 'MARKET',
            'quantity': intent.quantity
        }
        
        params = self._sign_request(params)
        
        try:
            response = requests.post(
                url,
                params=params,
                headers=self._get_headers(),
                timeout=30
            )
            response.raise_for_status()
            order_response = response.json()
            
            # Extract fill information
            fill_price = float(order_response.get('cummulativeQuoteQty', 0)) / float(order_response.get('executedQty', 1))
            filled_qty = float(order_response.get('executedQty', intent.quantity))
            
            result = TradeResult(
                timestamp=intent.timestamp,
                symbol=intent.symbol,
                side=intent.side.value,
                entry_price=fill_price,
                exit_price=None,
                quantity=filled_qty,
                reason=intent.reason.value
            )
            
            log_fill(logger, intent.side.value, intent.symbol, filled_qty, fill_price)
            
            logger.info(f"Order executed: {order_response.get('orderId')} "
                       f"status={order_response.get('status')}")
            
            return result
            
        except requests.RequestException as e:
            logger.error(f"Order execution failed: {e}")
            
            # Fall back to simulation on error
            logger.warning("Falling back to simulated execution")
            return self._simulate_execution(intent, current_price)
    
    def get_account_info(self) -> Optional[Dict]:
        """Get account information from Binance."""
        if not self.api_key or not self.api_secret:
            return None
        
        url = f"{self.base_url}/api/v3/account"
        params = self._sign_request({})
        
        try:
            response = requests.get(
                url,
                params=params,
                headers=self._get_headers(),
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get account info: {e}")
            return None
    
    def get_open_orders(self, symbol: str = SYMBOL) -> list:
        """Get open orders for a symbol."""
        if not self.api_key or not self.api_secret:
            return []
        
        url = f"{self.base_url}/api/v3/openOrders"
        params = self._sign_request({'symbol': symbol})
        
        try:
            response = requests.get(
                url,
                params=params,
                headers=self._get_headers(),
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get open orders: {e}")
            return []
