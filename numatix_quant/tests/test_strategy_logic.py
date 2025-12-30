import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, timedelta
from src.core.strategy_multi_tf import StrategyMultiTF
from src.core.strategy_base import BarData
from src.core.trade_intent import TradeSide, TradeReason

@pytest.fixture
def strategy():
    s = StrategyMultiTF(symbol="BTCUSDT", quantity=1.0)
    s.reset()
    # Mock warmup complete
    s._warmup_complete_entry = True
    s._warmup_complete_conf = True
    return s

def create_bar(timestamp, close):
    return BarData(
        timestamp=timestamp,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=100
    )

def test_long_entry_signal(strategy):
    """Test long entry on bullish crossover + bullish trend."""
    now = datetime.now()
    
    # Set bullish trend
    strategy._ema_fast_conf = 100
    strategy._ema_slow_conf = 90
    
    # Initial state: fast < slow
    strategy._prev_ema_fast_entry = 50
    strategy._prev_ema_slow_entry = 60
    
    # New bar: fast > slow
    strategy._ema_fast_entry = 65
    strategy._ema_slow_entry = 60
    
    bar = create_bar(now, 65)
    conf_bar = create_bar(now, 100)
    
    intent = strategy._evaluate_signals(bar, conf_bar)
    
    assert intent is not None
    assert intent.side == TradeSide.BUY
    assert intent.reason == TradeReason.ENTRY_LONG
    assert strategy.position.is_long()

def test_short_entry_signal(strategy):
    """Test short entry on bearish crossover + bearish trend."""
    now = datetime.now()
    
    # Set bearish trend
    strategy._ema_fast_conf = 80
    strategy._ema_slow_conf = 90
    
    # Initial state: fast > slow
    strategy._prev_ema_fast_entry = 60
    strategy._prev_ema_slow_entry = 50
    
    # New bar: fast < slow
    strategy._ema_fast_entry = 45
    strategy._ema_slow_entry = 50
    
    bar = create_bar(now, 45)
    conf_bar = create_bar(now, 80)
    
    intent = strategy._evaluate_signals(bar, conf_bar)
    
    assert intent is not None
    assert intent.side == TradeSide.SELL
    assert intent.reason == TradeReason.ENTRY_SHORT
    assert strategy.position.is_short()

def test_stop_loss_exit(strategy):
    """Test exit on stop loss."""
    now = datetime.now()
    
    # Open long at 100
    strategy.position.open_long(100.0, now, 0, 1.0)
    strategy.bar_index = 1
    
    # Set EMAs flat to avoid signal exit
    strategy._ema_fast_entry = 100
    strategy._ema_slow_entry = 90
    strategy._prev_ema_fast_entry = 100
    strategy._prev_ema_slow_entry = 90
    
    # Price drops to 98 (Stop loss 2% from config default)
    bar = create_bar(now + timedelta(minutes=5), 97.0) 
    
    intent = strategy._evaluate_signals(bar, None)
    
    assert intent is not None
    assert intent.reason == TradeReason.EXIT_STOP_LOSS
    assert strategy.position.is_flat()

def test_take_profit_exit(strategy):
    """Test exit on take profit."""
    now = datetime.now()
    
    # Open long at 100
    strategy.position.open_long(100.0, now, 0, 1.0)
    strategy.bar_index = 1
    
    # Set EMAs flat
    strategy._ema_fast_entry = 100
    strategy._ema_slow_entry = 90
    strategy._prev_ema_fast_entry = 100
    strategy._prev_ema_slow_entry = 90
    
    # Price rises to 106 (Take profit 5% from config default)
    bar = create_bar(now + timedelta(minutes=5), 106.0) 
    
    intent = strategy._evaluate_signals(bar, None)
    
    assert intent is not None
    assert intent.reason == TradeReason.EXIT_TAKE_PROFIT
    assert strategy.position.is_flat()

def test_signal_exit_long(strategy):
    """Test exit on bearish crossover (signal exit for long)."""
    now = datetime.now()
    
    # Open long
    strategy.position.open_long(100.0, now, 0, 1.0)
    strategy.bar_index = 1
    
    # Bearish crossover
    strategy._prev_ema_fast_entry = 110
    strategy._prev_ema_slow_entry = 100
    strategy._ema_fast_entry = 95
    strategy._ema_slow_entry = 100
    
    bar = create_bar(now + timedelta(minutes=5), 99.0)
    
    intent = strategy._evaluate_signals(bar, None)
    
    assert intent is not None
    assert intent.reason == TradeReason.EXIT_SIGNAL
    assert intent.side == TradeSide.SELL
    assert strategy.position.is_flat()

def test_execution_parity_mock(strategy):
    """
    Test that the same sequence of bars produces the same signals.
    This validates the core 'on_bar' logic which is used in both live/backtest.
    """
    now = datetime.now()
    
    # Sequence of prices leading to a long entry
    prices = [100, 101, 102, 103, 104, 105]
    
    # Setup bullish trend
    strategy._ema_fast_conf = 120
    strategy._ema_slow_conf = 110
    
    intents = []
    for i, p in enumerate(prices):
        bar = create_bar(now + timedelta(minutes=5*i), p)
        # Force a crossover at index 4
        if i == 4:
            strategy._prev_ema_fast_entry = 100
            strategy._prev_ema_slow_entry = 102
            strategy._ema_fast_entry = 103
            strategy._ema_slow_entry = 102
        else:
            # maintain no crossover
            strategy._prev_ema_fast_entry = 100
            strategy._prev_ema_slow_entry = 110
            strategy._ema_fast_entry = 101
            strategy._ema_slow_entry = 110
            
        intent = strategy.on_bar(bar, create_bar(now, 120))
        if intent:
            intents.append(intent)
            
    assert len(intents) == 1
    assert intents[0].reason == TradeReason.ENTRY_LONG

def test_no_exit_on_same_bar(strategy):
    """
    Test that exit is blocked on the same bar as entry.
    
    CRITICAL: This test validates same-bar exit protection, which ensures:
    - Position must be held for at least 1 bar before exit
    - No zero-PnL trades with identical entry/exit timestamps
    - Live/backtest parity is maintained
    """
    now = datetime.now()
    
    # Setup for a long entry (bullish crossover + bullish trend)
    strategy._ema_fast_conf = 100
    strategy._ema_slow_conf = 90
    strategy._prev_ema_fast_entry = 50
    strategy._prev_ema_slow_entry = 60
    strategy._ema_fast_entry = 65
    strategy._ema_slow_entry = 60
    
    bar = create_bar(now, 65)
    conf_bar = create_bar(now, 100)
    
    # Should enter long
    intent = strategy._evaluate_signals(bar, conf_bar)
    assert intent is not None
    assert intent.reason == TradeReason.ENTRY_LONG
    assert strategy.position.is_long()
    
    # Position is now open at current bar_index (0)
    # Try to exit on the SAME bar (bar_index not incremented yet)
    # Setup conditions that would normally trigger exit (bearish crossover)
    strategy._prev_ema_fast_entry = 110
    strategy._prev_ema_slow_entry = 100  
    strategy._ema_fast_entry = 95
    strategy._ema_slow_entry = 100
    
    bar2 = create_bar(now, 97.0)  # Price that might also trigger stop loss
    
    # Exit should be BLOCKED because bars_held is 0
    intent2 = strategy._evaluate_signals(bar2, None)
    assert intent2 is None, "Exit should be blocked on same bar as entry"
    assert strategy.position.is_long(), "Position should still be open"
    
    # Now increment bar_index (simulate new bar closing)
    strategy.bar_index += 1
    
    # Exit should now be allowed (bars_held = 1)
    intent3 = strategy._evaluate_signals(bar2, None)
    assert intent3 is not None, "Exit should be allowed after 1 bar"
    assert intent3.reason == TradeReason.EXIT_SIGNAL
    assert strategy.position.is_flat(), "Position should be closed"
