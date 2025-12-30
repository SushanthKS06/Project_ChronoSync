"""
Configuration module for Numatix-Quant Trading System.
Loads settings from environment variables using python-dotenv.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Binance Testnet API Configuration
BINANCE_TESTNET_API_KEY = os.getenv('BINANCE_TESTNET_API_KEY', '')
BINANCE_TESTNET_API_SECRET = os.getenv('BINANCE_TESTNET_API_SECRET', '')
BINANCE_TESTNET_BASE_URL = 'https://testnet.binance.vision'
BINANCE_TESTNET_FUTURES_URL = 'https://testnet.binancefuture.com'

# Public API for market data (mainnet - no auth required for klines)
BINANCE_PUBLIC_API_URL = 'https://api.binance.com'

# Use mainnet for public data, testnet for trading execution
BINANCE_API_BASE_URL = BINANCE_PUBLIC_API_URL  # For klines/market data
BINANCE_TRADING_URL = BINANCE_TESTNET_BASE_URL  # For order execution

# Trading Configuration
SYMBOL = os.getenv('SYMBOL', 'BTCUSDT')
TRADE_QUANTITY = float(os.getenv('TRADE_QUANTITY', '0.001'))

# Timeframe Configuration
TIMEFRAME_ENTRY = os.getenv('TIMEFRAME_ENTRY', '5m')
TIMEFRAME_CONFIRMATION = os.getenv('TIMEFRAME_CONFIRMATION', '15m')

# Strategy Parameters - Entry timeframe (e.g., 5m)
EMA_FAST_ENTRY = int(os.getenv('EMA_FAST_ENTRY', '8'))
EMA_SLOW_ENTRY = int(os.getenv('EMA_SLOW_ENTRY', '21'))

# Strategy Parameters - Confirmation timeframe (e.g., 15m)
EMA_FAST_CONFIRMATION = int(os.getenv('EMA_FAST_CONFIRMATION', '50'))
EMA_SLOW_CONFIRMATION = int(os.getenv('EMA_SLOW_CONFIRMATION', '200'))

# Position Management
POSITION_TIMEOUT_BARS = int(os.getenv('POSITION_TIMEOUT_BARS', '96'))
STOP_LOSS_PCT = float(os.getenv('STOP_LOSS_PCT', '0.02'))  # 2%
TAKE_PROFIT_PCT = float(os.getenv('TAKE_PROFIT_PCT', '0.04'))  # 4%

# Data paths
DATA_DIR = Path(__file__).parent.parent / 'data'
BACKTEST_TRADES_PATH = DATA_DIR / 'backtest_trades.csv'
LIVE_TRADES_PATH = DATA_DIR / 'live_trades.csv'

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Backtesting Configuration
# Use 3 months of data for reasonable testing time (~8500 15m bars)
BACKTEST_START_DATE = '2024-09-01'
BACKTEST_END_DATE = '2024-12-01'
BACKTEST_INITIAL_CASH = 1000000.0  # $1M to handle BTC prices with 0.001 BTC positions
BACKTEST_COMMISSION = 0.001  # 0.1%

# Live Trading Configuration
LIVE_POLL_INTERVAL_SECONDS = 60  # Poll every minute
LIVE_WARMUP_BARS = int(os.getenv('LIVE_WARMUP_BARS', '250'))  # Bars for each timeframe
