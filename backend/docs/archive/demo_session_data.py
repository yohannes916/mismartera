#!/usr/bin/env python3
"""
Quick demonstration of Phase 1: session_data implementation

This script shows how the new session_data singleton works and demonstrates
the fast access methods optimized for AnalysisEngine.
"""
import asyncio
from datetime import datetime, timedelta
from app.managers.system_manager import get_system_manager, reset_system_manager
from app.managers.data_manager.session_data import get_session_data, reset_session_data
from app.models.trading import BarData


async def demo_basic_operations():
    """Demonstrate basic session_data operations."""
    print("=" * 70)
    print("PHASE 1 DEMONSTRATION: session_data Singleton")
    print("=" * 70)
    print()
    
    # Reset for clean demo
    reset_system_manager()
    reset_session_data()
    
    # Access via SystemManager (recommended way)
    print("1️⃣  Accessing session_data via SystemManager...")
    system_mgr = get_system_manager()
    session_data = system_mgr.session_data
    print(f"   ✅ SystemManager.session_data: {type(session_data).__name__}")
    print()
    
    # Create test data
    print("2️⃣  Creating test data (100 bars for AAPL)...")
    bars = []
    base_time = datetime(2025, 1, 1, 9, 30)
    for i in range(100):
        bar = BarData(
            symbol="AAPL",
            timestamp=base_time + timedelta(minutes=i),
            open=150.0 + i * 0.1,
            high=151.0 + i * 0.1,
            low=149.0 + i * 0.1,
            close=150.5 + i * 0.1,
            volume=1000 + i * 10
        )
        bars.append(bar)
    
    await session_data.add_bars_batch("AAPL", bars)
    print(f"   ✅ Added {len(bars)} bars")
    print()
    
    # Demonstrate O(1) latest bar access
    print("3️⃣  Getting latest bar (O(1) operation)...")
    latest = await session_data.get_latest_bar("AAPL")
    print(f"   ✅ Latest bar: ${latest.close:.2f} at {latest.timestamp.strftime('%H:%M')}")
    print(f"   ✅ Volume: {latest.volume:,}")
    print()
    
    # Demonstrate last-N bars
    print("4️⃣  Getting last 20 bars (for SMA calculation)...")
    last_20 = await session_data.get_last_n_bars("AAPL", 20)
    print(f"   ✅ Retrieved {len(last_20)} bars")
    
    # Calculate SMA-20
    sma_20 = sum(b.close for b in last_20) / len(last_20)
    print(f"   ✅ SMA-20: ${sma_20:.2f}")
    print(f"   ✅ Current vs SMA: {'Above' if latest.close > sma_20 else 'Below'}")
    print()
    
    # Demonstrate time-based query
    print("5️⃣  Getting bars from last 30 minutes...")
    thirty_min_ago = latest.timestamp - timedelta(minutes=30)
    recent = await session_data.get_bars_since("AAPL", thirty_min_ago)
    print(f"   ✅ Retrieved {len(recent)} bars")
    
    # Calculate recent volume
    recent_volume = sum(b.volume for b in recent)
    print(f"   ✅ Volume (last 30 min): {recent_volume:,}")
    print()
    
    # Demonstrate bar count
    print("6️⃣  Getting bar count (O(1) operation)...")
    count = await session_data.get_bar_count("AAPL")
    print(f"   ✅ Total bars: {count}")
    print()
    
    # Demonstrate session metrics
    print("7️⃣  Getting session metrics...")
    metrics = await session_data.get_session_metrics("AAPL")
    print(f"   ✅ Session volume: {metrics['session_volume']:,}")
    print(f"   ✅ Session high: ${metrics['session_high']:.2f}")
    print(f"   ✅ Session low: ${metrics['session_low']:.2f}")
    print(f"   ✅ Bar quality: {metrics['bar_quality']:.1f}%")
    print()


async def demo_multi_symbol():
    """Demonstrate multi-symbol operations."""
    print("8️⃣  Multi-Symbol Operations...")
    
    session_data = get_session_data()
    
    # Add bars for multiple symbols
    symbols = ["GOOGL", "MSFT", "TSLA"]
    base_time = datetime(2025, 1, 1, 10, 30)
    
    for symbol in symbols:
        bars = []
        for i in range(50):
            bar = BarData(
                symbol=symbol,
                timestamp=base_time + timedelta(minutes=i),
                open=200.0 + i,
                high=201.0 + i,
                low=199.0 + i,
                close=200.5 + i,
                volume=2000 + i * 20
            )
            bars.append(bar)
        await session_data.add_bars_batch(symbol, bars)
    
    print(f"   ✅ Added 50 bars each for {', '.join(symbols)}")
    
    # Batch get latest bars
    all_symbols = ["AAPL", "GOOGL", "MSFT", "TSLA"]
    latest_bars = await session_data.get_latest_bars_multi(all_symbols)
    
    print(f"   ✅ Retrieved latest bars for {len(latest_bars)} symbols:")
    for symbol, bar in latest_bars.items():
        if bar:
            print(f"      {symbol}: ${bar.close:.2f}")
    
    print()
    print(f"   ✅ Active symbols: {session_data.get_active_symbols()}")
    print()


async def demo_analysis_engine_pattern():
    """Demonstrate how AnalysisEngine would use session_data."""
    print("9️⃣  AnalysisEngine Usage Pattern...")
    print()
    
    session_data = get_session_data()
    
    # Simulate AnalysisEngine analyzing a symbol
    symbol = "AAPL"
    
    print(f"   Analyzing {symbol}...")
    print()
    
    # Step 1: Check if enough data exists
    bar_count = await session_data.get_bar_count(symbol)
    print(f"   1. Check data availability: {bar_count} bars")
    
    if bar_count < 50:
        print(f"      ⚠️  Need at least 50 bars for analysis")
        return
    
    # Step 2: Get latest bar
    latest = await session_data.get_latest_bar(symbol)
    print(f"   2. Get current price: ${latest.close:.2f}")
    
    # Step 3: Get bars for technical indicators
    bars_50 = await session_data.get_last_n_bars(symbol, 50)
    bars_20 = bars_50[-20:]  # More efficient than separate call
    
    # Step 4: Calculate indicators
    sma_20 = sum(b.close for b in bars_20) / 20
    sma_50 = sum(b.close for b in bars_50) / 50
    
    print(f"   3. Calculate SMA-20: ${sma_20:.2f}")
    print(f"   4. Calculate SMA-50: ${sma_50:.2f}")
    
    # Step 5: Determine trend
    if latest.close > sma_20 > sma_50:
        trend = "Strong Bullish"
        emoji = "🚀"
    elif latest.close > sma_20:
        trend = "Bullish"
        emoji = "📈"
    elif latest.close < sma_20 < sma_50:
        trend = "Strong Bearish"
        emoji = "📉"
    else:
        trend = "Bearish"
        emoji = "⚠️"
    
    print(f"   5. Determine trend: {emoji} {trend}")
    
    # Step 6: Volume analysis
    recent = await session_data.get_bars_since(symbol, latest.timestamp - timedelta(minutes=10))
    avg_volume = sum(b.volume for b in recent) / len(recent) if recent else 0
    volume_spike = latest.volume > avg_volume * 1.5
    
    print(f"   6. Volume analysis: {'🔥 Spike detected!' if volume_spike else '✅ Normal'}")
    
    # Step 7: Get session context
    metrics = await session_data.get_session_metrics(symbol)
    near_high = abs(latest.close - metrics['session_high']) / metrics['session_high'] < 0.01
    near_low = abs(latest.close - metrics['session_low']) / metrics['session_low'] < 0.01
    
    print(f"   7. Session context:")
    print(f"      • Near session high: {'✅ Yes' if near_high else 'No'}")
    print(f"      • Near session low: {'✅ Yes' if near_low else 'No'}")
    
    print()
    print(f"   {emoji} ANALYSIS RESULT: {trend} trend")
    print(f"      Price: ${latest.close:.2f}")
    print(f"      SMA-20: ${sma_20:.2f} | SMA-50: ${sma_50:.2f}")
    print(f"      Volume: {latest.volume:,} ({'spike' if volume_spike else 'normal'})")
    print()


async def main():
    """Run all demonstrations."""
    try:
        await demo_basic_operations()
        await demo_multi_symbol()
        await demo_analysis_engine_pattern()
        
        print("=" * 70)
        print("✅ DEMONSTRATION COMPLETE")
        print("=" * 70)
        print()
        print("Key Takeaways:")
        print("  • session_data accessible via SystemManager")
        print("  • O(1) latest bar access (microseconds)")
        print("  • Efficient last-N bars for indicators")
        print("  • Multi-symbol batch operations")
        print("  • Thread-safe async operations")
        print("  • Ready for AnalysisEngine integration")
        print()
        print("Next: Review PHASE1_COMPLETE.md for full details")
        print()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("\n")
    asyncio.run(main())
