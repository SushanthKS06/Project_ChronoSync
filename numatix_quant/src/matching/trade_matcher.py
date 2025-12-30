"""
Trade Matcher.
Compares backtest trades with live trades to verify execution parity.
"""

import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.utils.logger import get_logger
from src.utils.csv_writer import CSVWriter
from config.config import BACKTEST_TRADES_PATH, LIVE_TRADES_PATH

logger = get_logger(__name__)


class TradeMatcher:
    """
    Compares backtest and live trades to verify execution parity.
    
    Comparison Criteria:
    - Trade count
    - Direction consistency (BUY/SELL sequence)
    - Approximate timestamps (timing drift acceptable)
    - Trade reasons
    
    Logic mismatches are flagged; timing drift is acceptable.
    """
    
    def __init__(
        self,
        backtest_path: str = str(BACKTEST_TRADES_PATH),
        live_path: str = str(LIVE_TRADES_PATH)
    ):
        """
        Initialize trade matcher.
        
        Args:
            backtest_path: Path to backtest trades CSV
            live_path: Path to live trades CSV
        """
        self.backtest_path = backtest_path
        self.live_path = live_path
        
        self.backtest_trades: List[Dict] = []
        self.live_trades: List[Dict] = []
        
        self.mismatches: List[Dict] = []
        self.matches: List[Dict] = []
    
    def load_trades(self) -> Tuple[int, int]:
        """
        Load trades from both CSV files.
        
        Returns:
            Tuple of (backtest_count, live_count)
        """
        # Load backtest trades
        backtest_writer = CSVWriter(self.backtest_path)
        self.backtest_trades = backtest_writer.read_trades()
        
        # Load live trades
        live_writer = CSVWriter(self.live_path)
        self.live_trades = live_writer.read_trades()
        
        logger.info(f"Loaded {len(self.backtest_trades)} backtest trades")
        logger.info(f"Loaded {len(self.live_trades)} live trades")
        
        return len(self.backtest_trades), len(self.live_trades)
    
    def compare_trade_count(self) -> Dict:
        """
        Compare trade counts.
        
        Returns:
            Dictionary with comparison results
        """
        bt_count = len(self.backtest_trades)
        live_count = len(self.live_trades)
        
        result = {
            'backtest_count': bt_count,
            'live_count': live_count,
            'difference': abs(bt_count - live_count),
            'match': bt_count == live_count
        }
        
        if result['match']:
            logger.info(f"✓ Trade count matches: {bt_count}")
        else:
            logger.warning(f"✗ Trade count mismatch: backtest={bt_count}, live={live_count}")
        
        return result
    
    def compare_direction_sequence(self) -> Dict:
        """
        Compare the sequence of trade directions.
        
        Returns:
            Dictionary with sequence comparison results
        """
        bt_directions = [t.get('side', '') for t in self.backtest_trades]
        live_directions = [t.get('side', '') for t in self.live_trades]
        
        # Compare up to the shorter length
        min_len = min(len(bt_directions), len(live_directions))
        
        matches = 0
        mismatches = []
        
        for i in range(min_len):
            if bt_directions[i] == live_directions[i]:
                matches += 1
            else:
                mismatches.append({
                    'index': i,
                    'backtest': bt_directions[i],
                    'live': live_directions[i]
                })
        
        match_rate = (matches / min_len * 100) if min_len > 0 else 0
        
        result = {
            'compared_trades': min_len,
            'matching_directions': matches,
            'mismatched_directions': len(mismatches),
            'match_rate': match_rate,
            'mismatches': mismatches[:10]  # First 10 mismatches
        }
        
        if match_rate == 100:
            logger.info(f"✓ Direction sequence matches: {matches}/{min_len}")
        else:
            logger.warning(f"✗ Direction mismatch: {matches}/{min_len} ({match_rate:.1f}% match)")
            for m in mismatches[:5]:
                logger.warning(f"  Trade {m['index']}: backtest={m['backtest']}, live={m['live']}")
        
        return result
    
    def compare_trade_reasons(self) -> Dict:
        """
        Compare trade reasons between backtest and live.
        
        Returns:
            Dictionary with reason comparison results
        """
        bt_reasons = [t.get('reason', '') for t in self.backtest_trades]
        live_reasons = [t.get('reason', '') for t in self.live_trades]
        
        min_len = min(len(bt_reasons), len(live_reasons))
        
        matches = 0
        mismatches = []
        
        for i in range(min_len):
            if bt_reasons[i] == live_reasons[i]:
                matches += 1
            else:
                mismatches.append({
                    'index': i,
                    'backtest': bt_reasons[i],
                    'live': live_reasons[i]
                })
        
        match_rate = (matches / min_len * 100) if min_len > 0 else 0
        
        result = {
            'compared_trades': min_len,
            'matching_reasons': matches,
            'mismatched_reasons': len(mismatches),
            'match_rate': match_rate,
            'mismatches': mismatches[:10]
        }
        
        if match_rate == 100:
            logger.info(f"✓ Trade reasons match: {matches}/{min_len}")
        else:
            logger.warning(f"✗ Reason mismatch: {matches}/{min_len} ({match_rate:.1f}% match)")
            for m in mismatches[:5]:
                logger.warning(f"  Trade {m['index']}: backtest={m['backtest']}, live={m['live']}")
        
        return result
    
    def analyze_timing_drift(self) -> Dict:
        """
        Analyze timing differences between backtest and live trades.
        
        Note: Timing drift is expected and acceptable.
        
        Returns:
            Dictionary with timing analysis
        """
        if not self.backtest_trades or not self.live_trades:
            return {'status': 'insufficient_data'}
        
        try:
            bt_times = []
            live_times = []
            
            for t in self.backtest_trades:
                ts = t.get('timestamp', '')
                if ts:
                    bt_times.append(pd.to_datetime(ts))
            
            for t in self.live_trades:
                ts = t.get('timestamp', '')
                if ts:
                    live_times.append(pd.to_datetime(ts))
            
            if not bt_times or not live_times:
                return {'status': 'no_timestamps'}
            
            # Calculate time range
            bt_start = min(bt_times)
            bt_end = max(bt_times)
            live_start = min(live_times)
            live_end = max(live_times)
            
            result = {
                'backtest_range': f"{bt_start} to {bt_end}",
                'live_range': f"{live_start} to {live_end}",
                'status': 'analyzed'
            }
            
            logger.info(f"Timing analysis:")
            logger.info(f"  Backtest: {bt_start} to {bt_end}")
            logger.info(f"  Live:     {live_start} to {live_end}")
            logger.info(f"  (Timing drift is expected and acceptable)")
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing timing: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def run_comparison(self) -> Dict:
        """
        Run full comparison and generate summary.
        
        Returns:
            Dictionary with complete comparison results
        """
        logger.info("=" * 60)
        logger.info("TRADE MATCHING ANALYSIS")
        logger.info("=" * 60)
        
        # Load trades
        bt_count, live_count = self.load_trades()
        
        if bt_count == 0 and live_count == 0:
            logger.warning("No trades found in either file")
            return {
                'status': 'no_trades',
                'backtest_count': 0,
                'live_count': 0
            }
        
        if bt_count == 0:
            logger.warning("No backtest trades found")
        if live_count == 0:
            logger.warning("No live trades found - this is expected if live trading hasn't run yet")
        
        # Run comparisons
        count_result = self.compare_trade_count()
        direction_result = self.compare_direction_sequence()
        reason_result = self.compare_trade_reasons()
        timing_result = self.analyze_timing_drift()
        
        # Generate summary
        overall_match = (
            count_result['match'] and
            direction_result.get('match_rate', 0) == 100 and
            reason_result.get('match_rate', 0) == 100
        )
        
        summary = {
            'status': 'complete',
            'overall_match': overall_match,
            'trade_count': count_result,
            'direction_sequence': direction_result,
            'trade_reasons': reason_result,
            'timing': timing_result
        }
        
        # Print summary
        self._print_summary(summary)
        
        return summary
    
    def _print_summary(self, summary: Dict) -> None:
        """Print formatted summary to CLI."""
        print("\n" + "=" * 60)
        print("TRADE MATCHING SUMMARY")
        print("=" * 60)
        
        count = summary['trade_count']
        print(f"\nTrade Count:")
        print(f"  Backtest: {count['backtest_count']}")
        print(f"  Live:     {count['live_count']}")
        print(f"  Match:    {'✓ YES' if count['match'] else '✗ NO'}")
        
        direction = summary['direction_sequence']
        print(f"\nDirection Sequence:")
        print(f"  Compared: {direction.get('compared_trades', 0)} trades")
        print(f"  Matching: {direction.get('matching_directions', 0)}")
        print(f"  Match Rate: {direction.get('match_rate', 0):.1f}%")
        
        reason = summary['trade_reasons']
        print(f"\nTrade Reasons:")
        print(f"  Compared: {reason.get('compared_trades', 0)} trades")
        print(f"  Matching: {reason.get('matching_reasons', 0)}")
        print(f"  Match Rate: {reason.get('match_rate', 0):.1f}%")
        
        print(f"\nTiming:")
        timing = summary['timing']
        if timing.get('status') == 'analyzed':
            print(f"  Backtest: {timing.get('backtest_range', 'N/A')}")
            print(f"  Live:     {timing.get('live_range', 'N/A')}")
            print(f"  Note: Timing drift is expected and acceptable")
        else:
            print(f"  Status: {timing.get('status', 'unknown')}")
        
        print(f"\nOverall Parity: {'✓ VERIFIED' if summary['overall_match'] else '! ATTENTION NEEDED'}")
        
        if not summary['overall_match']:
            print("\nNote: Some mismatches detected. This may be due to:")
            print("  - Insufficient live trading data")
            print("  - Market conditions during different time periods")
            print("  - Expected timing differences between backtest and live")
        
        print("=" * 60)


def run_matcher():
    """Entry point for trade matching."""
    matcher = TradeMatcher()
    matcher.run_comparison()


if __name__ == '__main__':
    run_matcher()
