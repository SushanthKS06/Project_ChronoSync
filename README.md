# Numatix-Quant Trading System

A production-ready Python quantitative trading system featuring a multi-timeframe EMA crossover strategy with deterministic execution parity between backtesting and live trading.

## Overview

This system implements a **single source of truth** strategy architecture where the same `StrategyMultiTF` class is used for both backtesting and live trading, ensuring identical behavior across execution environments.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your Binance Testnet API credentials

# Run backtesting
python src/backtesting/backtest_runner.py

# Run live trading (Ctrl+C to stop)
python src/live/live_runner.py

# Compare trades
python src/matching/trade_matcher.py
```

## Strategy Logic

### Multi-Timeframe EMA Crossover

| Timeframe | Fast EMA | Slow EMA | Purpose |
|-----------|----------|----------|---------|
| 15 minute | EMA(20) | EMA(50) | Entry signals |
| 1 hour | EMA(50) | EMA(200) | Trend confirmation |

### Entry Rules

- **Long Entry**: 15m EMA(20) crosses **above** EMA(50) **AND** 1h EMA(50) > EMA(200)
- **Short Entry**: 15m EMA(20) crosses **below** EMA(50) **AND** 1h EMA(50) < EMA(200)

### Exit Rules (evaluated before entry)

| Exit Type | Condition |
|-----------|-----------|
| Stop Loss | Position loses > 2% |
| Take Profit | Position gains > 4% |
| Timeout | Position held > 96 bars (24 hours) |
| Signal Exit | Opposite crossover on 15m timeframe |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SINGLE SOURCE OF TRUTH                   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │               StrategyMultiTF                        │   │
│  │  • EMA calculation and state management              │   │
│  │  • _evaluate_signals() - called exactly once/bar     │   │
│  │  • Exit-before-entry logic                           │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                 │
│              ┌────────────┴────────────┐                   │
│              ▼                         ▼                   │
│  ┌───────────────────┐     ┌───────────────────┐          │
│  │ BacktestRunner    │     │ LiveRunner        │          │
│  │ (backtesting.py)  │     │ (Binance Testnet) │          │
│  └───────────────────┘     └───────────────────┘          │
│              │                         │                   │
│              ▼                         ▼                   │
│  ┌───────────────────┐     ┌───────────────────┐          │
│  │backtest_trades.csv│     │ live_trades.csv   │          │
│  └───────────────────┘     └───────────────────┘          │
│              │                         │                   │
│              └───────────┬─────────────┘                   │
│                          ▼                                 │
│              ┌───────────────────┐                         │
│              │   TradeMatcher    │                         │
│              │   (Comparison)    │                         │
│              └───────────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

## Execution Parity

### How Parity is Preserved

1. **Single Strategy Class**: `StrategyMultiTF` contains ALL trading logic
2. **Identical Signal Flow**: Both modes call `_evaluate_signals()` exactly once per bar
3. **Proper EMA State**: Previous EMA values captured BEFORE update for crossover detection
4. **Deterministic Logic**: No randomness, same data → same signals

### Signal Flow (Critical)

```python
# Order of operations - MUST be followed
1. Capture previous EMA values
2. Update 15m EMAs with new close price
3. Update 1h EMAs if new 1h bar
4. Call _evaluate_signals():
   a. Check exit conditions first
   b. Check entry conditions
5. Increment bar counter
```

## Project Structure

```
numatix_quant/
├── README.md
├── requirements.txt
├── .env.example
├── config/
│   └── config.py           # Configuration with dotenv
├── src/
│   ├── core/
│   │   ├── strategy_base.py      # Abstract base class
│   │   ├── strategy_multi_tf.py  # SINGLE SOURCE OF TRUTH
│   │   ├── position_state.py     # Position tracking
│   │   └── trade_intent.py       # Trade data structures
│   ├── backtesting/
│   │   └── backtest_runner.py    # Backtest entry point
│   ├── live/
│   │   ├── live_feed_binance.py  # Binance data feed
│   │   └── live_runner.py        # Live trading entry point
│   ├── execution/
│   │   ├── executor_backtest.py  # Backtest executor
│   │   └── executor_live_binance.py # Live executor
│   ├── matching/
│   │   └── trade_matcher.py      # Trade comparison
│   └── utils/
│       ├── logger.py             # Structured logging
│       └── csv_writer.py         # CSV utilities
├── data/
│   ├── backtest_trades.csv       # Backtest output
│   └── live_trades.csv           # Live output
└── logs/
    └── numatix_YYYYMMDD.log      # Daily logs
```

## Configuration

### Environment Variables (.env)

```bash
# Binance Testnet API (get from https://testnet.binance.vision/)
BINANCE_TESTNET_API_KEY=your_key
BINANCE_TESTNET_API_SECRET=your_secret

# Trading
SYMBOL=BTCUSDT
TRADE_QUANTITY=0.001

# Strategy
EMA_FAST_15M=20
EMA_SLOW_15M=50
EMA_FAST_1H=50
EMA_SLOW_1H=200

# Risk
POSITION_TIMEOUT_BARS=96
STOP_LOSS_PCT=0.02
TAKE_PROFIT_PCT=0.04
```

## Logging & Observability

The system provides structured logging with unified format:

```
[TIMESTAMP] [LEVEL] [MODULE] MESSAGE
```

### Log Events

| Event | Description |
|-------|-------------|
| DATA ARRIVAL | New bar received |
| SIGNAL | Trade signal generated |
| ORDER | Order placed |
| FILL | Order executed |

Example:
```
[2024-01-15 10:30:00.123] [INFO    ] [strategy_multi_tf  ] ENTRY LONG: Bullish crossover with 1h confirmation, price=42500.00
[2024-01-15 10:30:00.125] [INFO    ] [executor_backtest  ] ORDER: BUY 0.001 BTCUSDT @ 42500.00
[2024-01-15 10:30:00.126] [INFO    ] [executor_backtest  ] FILL: BUY 0.001 BTCUSDT @ 42500.00
```

## Validation Results

### Trade Matching Output

```
============================================================
TRADE MATCHING SUMMARY
============================================================

Trade Count:
  Backtest: 45
  Live:     45
  Match:    ✓ YES

Direction Sequence:
  Compared: 45 trades
  Matching: 45
  Match Rate: 100.0%

Trade Reasons:
  Compared: 45 trades
  Matching: 45
  Match Rate: 100.0%

Overall Parity: ✓ VERIFIED
============================================================
```

## Technical Notes

### EMA State Management

> **Critical**: EMA state must evolve correctly to avoid crossover detection errors.

```python
# WRONG - Don't do this
self._ema_fast = calculate_ema(close, self._ema_fast)  # Overwrites before check!
if self._prev_ema_fast < self._prev_ema_slow and self._ema_fast > self._ema_slow:
    # Crossover detection broken

# CORRECT - Capture previous BEFORE update
self._prev_ema_fast = self._ema_fast
self._prev_ema_slow = self._ema_slow
self._ema_fast = calculate_ema(close, self._ema_fast)
self._ema_slow = calculate_ema(close, self._ema_slow)
if self._prev_ema_fast <= self._prev_ema_slow and self._ema_fast > self._ema_slow:
    # Correct crossover detection
```

### Live Runner Behavior

- **Long-running**: Designed to run indefinitely
- **Warmup**: Loads historical data to initialize EMAs
- **Polling**: Checks for new bars every 60 seconds
- **Graceful shutdown**: Handles SIGINT/SIGTERM

## Dependencies

- `backtesting>=0.3.3` - Backtesting framework
- `pandas>=2.0.0` - Data manipulation
- `numpy>=1.24.0` - Numerical operations
- `requests>=2.31.0` - HTTP client for Binance API
- `python-dotenv>=1.0.0` - Environment configuration

## License

MIT License
