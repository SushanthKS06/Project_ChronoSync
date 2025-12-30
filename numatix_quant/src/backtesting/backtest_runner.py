"""
Backtest Runner - Main entry point for backtesting.
Fetches historical data and runs backtesting.py with our strategy wrapper.

CRITICAL: Deterministic execution guaranteed via seed setting.
"""

import sys
import os
import random
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import requests

# Set seeds FIRST for deterministic behavior
RANDOM_SEED = 42
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backtesting import Backtest

from src.execution.executor_backtest import BacktestStrategyWrapper
from src.utils.logger import get_logger
from src.utils.csv_writer import CSVWriter
from config.config import (
    SYMBOL, BACKTEST_TRADES_PATH, BACKTEST_INITIAL_CASH,
    BACKTEST_COMMISSION, BINANCE_API_BASE_URL,
    BACKTEST_START_DATE, BACKTEST_END_DATE,
    TIMEFRAME_ENTRY, TIMEFRAME_CONFIRMATION
)

logger = get_logger(__name__)


def fetch_binance_klines(
    symbol: str,
    interval: str,
    start_time: datetime,
    end_time: datetime,
    limit: int = 1000
) -> pd.DataFrame:
    """
    Fetch historical klines from Binance API.
    
    Args:
        symbol: Trading pair (e.g., 'BTCUSDT')
        interval: Kline interval (e.g., '15m', '1h')
        start_time: Start datetime
        end_time: End datetime
        limit: Max klines per request
    
    Returns:
        DataFrame with OHLCV data
    """
    url = f"{BINANCE_API_BASE_URL}/api/v3/klines"
    
    all_klines = []
    current_start = int(start_time.timestamp() * 1000)
    end_ms = int(end_time.timestamp() * 1000)
    
    while current_start < end_ms:
        params = {
            'symbol': symbol,
            'interval': interval,
            'startTime': current_start,
            'endTime': end_ms,
            'limit': limit
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            klines = response.json()
            
            if not klines:
                break
            
            all_klines.extend(klines)
            
            # Move start to after the last kline
            current_start = klines[-1][0] + 1
            
            # Progress indicator
            logger.info(f"Fetched {len(all_klines)} {interval} bars...")
            print(f"  Downloading {interval} data: {len(all_klines)} bars fetched...", end='\r')
            
        except requests.RequestException as e:
            logger.error(f"Error fetching klines: {e}")
            break
    
    print()  # New line after progress
    
    if not all_klines:
        return pd.DataFrame()
    
    # Convert to DataFrame
    df = pd.DataFrame(all_klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
        'taker_buy_quote', 'ignore'
    ])
    
    # Process columns
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.set_index('timestamp')
    
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    
    # Rename for backtesting.py compatibility
    df = df.rename(columns={
        'open': 'Open',
        'high': 'High',
        'low': 'Low',
        'close': 'Close',
        'volume': 'Volume'
    })
    
    return df[['Open', 'High', 'Low', 'Close', 'Volume']]


def run_backtest():
    """
    Run the backtest with StrategyMultiTF.
    
    This function:
    1. Fetches historical data for both timeframes
    2. Runs backtesting.py with our strategy wrapper
    3. Saves trades to CSV
    4. Prints results summary
    """
    logger.info("=" * 60)
    logger.info("STARTING BACKTEST")
    logger.info("=" * 60)
    
    # Parse dates
    start_date = datetime.strptime(BACKTEST_START_DATE, '%Y-%m-%d')
    end_date = datetime.strptime(BACKTEST_END_DATE, '%Y-%m-%d')
    
    logger.info(f"Symbol: {SYMBOL}")
    logger.info(f"Period: {start_date.date()} to {end_date.date()}")
    
    # Fetch entry timeframe data
    logger.info(f"Fetching {TIMEFRAME_ENTRY} historical data...")
    data_entry = fetch_binance_klines(SYMBOL, TIMEFRAME_ENTRY, start_date, end_date)
    
    if data_entry.empty:
        logger.error(f"Failed to fetch {TIMEFRAME_ENTRY} data")
        return
    
    logger.info(f"Loaded {len(data_entry)} {TIMEFRAME_ENTRY} bars")
    
    # Fetch confirmation timeframe data
    logger.info(f"Fetching {TIMEFRAME_CONFIRMATION} historical data...")
    data_conf = fetch_binance_klines(SYMBOL, TIMEFRAME_CONFIRMATION, start_date, end_date)
    
    if data_conf.empty:
        logger.error(f"Failed to fetch {TIMEFRAME_CONFIRMATION} data")
        return
    
    logger.info(f"Loaded {len(data_conf)} {TIMEFRAME_CONFIRMATION} bars")
    
    # Set confirmation data for strategy
    BacktestStrategyWrapper.set_conf_data(data_conf)
    
    # Create and run backtest
    logger.info("Running backtest...")
    bt = Backtest(
        data_entry,
        BacktestStrategyWrapper,
        cash=BACKTEST_INITIAL_CASH,
        commission=BACKTEST_COMMISSION,
        exclusive_orders=True,
        trade_on_close=True  # Execute on bar close for determinism
    )
    
    stats = bt.run()
    
    # Print results
    logger.info("=" * 60)
    logger.info("BACKTEST RESULTS")
    logger.info("=" * 60)
    
    print("\n" + "=" * 60)
    print("BACKTEST RESULTS SUMMARY")
    print("=" * 60)
    print(f"Start Date:           {start_date.date()}")
    print(f"End Date:             {end_date.date()}")
    print(f"Duration:             {(end_date - start_date).days} days")
    print(f"Starting Equity:      ${BACKTEST_INITIAL_CASH:,.2f}")
    print(f"Ending Equity:        ${stats['Equity Final [$]']:,.2f}")
    print(f"Return:               {stats['Return [%]']:.2f}%")
    print(f"Max Drawdown:         {stats['Max. Drawdown [%]']:.2f}%")
    print(f"Total Trades:         {stats['# Trades']}")
    print(f"Win Rate:             {stats['Win Rate [%]']:.2f}%")
    print(f"Profit Factor:        {stats.get('Profit Factor', 'N/A')}")
    print("=" * 60)
    
    # Save trades to CSV
    trades = BacktestStrategyWrapper.get_trade_log()
    
    if trades:
        csv_writer = CSVWriter(BACKTEST_TRADES_PATH)
        csv_writer.clear()
        csv_writer.write_trades(trades)
        logger.info(f"Saved {len(trades)} trades to {BACKTEST_TRADES_PATH}")
        print(f"\nTrades saved to: {BACKTEST_TRADES_PATH}")
    else:
        logger.warning("No trades generated during backtest")
        print("\nNo trades were generated during the backtest.")
    
    logger.info("Backtest complete")
    
    return stats


if __name__ == '__main__':
    run_backtest()
