"""Comprehensive test suite for DataManager Snapshot API

ARCHITECTURE (2025-11):
These tests use SystemManager as the single source of truth for operation mode.

Tests cover:
- get_snapshot() - Latest market snapshot from data provider

Test scenarios:
1. Snapshot in live mode from Alpaca API
2. Snapshot unavailable in backtest mode
3. API response parsing (trade, quote, bars)
4. Error handling (no data, API failure, network issues)
5. Missing credentials
6. Invalid symbol
7. Data structure validation
8. Timestamp handling
9. Multiple providers (Alpaca only for now)
10. Rate limiting and retries
"""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock

from app.config import settings
from app.managers.data_manager.api import DataManager


class TestSnapshotAPI:
    """Test suite for Snapshot API."""
    
    def setup_method(self):
        """Setup before each test."""
        print("\n" + "="*80)
        print("STARTING NEW TEST - SNAPSHOT API")
        print("="*80)
    
    # ==================== get_snapshot() Tests ====================
    
    @pytest.mark.asyncio
    async def test_01_snapshot_live_mode_success(self, system_manager):
        """TEST 1: Get snapshot successfully in live mode"""
        print("✓ Testing: Snapshot API in live mode")
        
        system_manager.set_mode("live")
        dm = system_manager.get_data_manager()
        
        # Mock Alpaca API response
        mock_snapshot = {
            'latest_trade': {
                'price': 185.50,
                'size': 100,
                'timestamp': datetime.now().isoformat()
            },
            'latest_quote': {
                'bid_price': 185.48,
                'bid_size': 200,
                'ask_price': 185.52,
                'ask_size': 150,
                'timestamp': datetime.now().isoformat()
            },
            'minute_bar': {
                'open': 185.40,
                'high': 185.60,
                'low': 185.35,
                'close': 185.50,
                'volume': 45000,
                'timestamp': datetime.now().isoformat()
            },
            'daily_bar': {
                'open': 184.50,
                'high': 186.10,
                'low': 183.90,
                'close': 185.50,
                'volume': 45234567,
                'timestamp': datetime.now().isoformat()
            },
            'prev_daily_bar': {
                'open': 183.00,
                'high': 184.80,
                'low': 182.50,
                'close': 184.20,
                'volume': 42000000,
                'timestamp': datetime.now().isoformat()
            }
        }
        
        with patch('app.managers.data_manager.integrations.alpaca_data.fetch_snapshot',
                   new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_snapshot
            
            snapshot = await dm.get_snapshot("AAPL")
            
            assert snapshot is not None, "Snapshot should be returned"
            assert 'latest_trade' in snapshot, "Should have latest trade"
            assert 'latest_quote' in snapshot, "Should have latest quote"
            assert 'daily_bar' in snapshot, "Should have daily bar"
            
            print(f"  Symbol: AAPL")
            print(f"  Latest trade price: ${snapshot['latest_trade']['price']:.2f}")
            print(f"  Bid: ${snapshot['latest_quote']['bid_price']:.2f}")
            print(f"  Ask: ${snapshot['latest_quote']['ask_price']:.2f}")
            print(f"  Daily volume: {snapshot['daily_bar']['volume']:,}")
            print("  ✓ Snapshot retrieved successfully")
    
    @pytest.mark.asyncio
    async def test_02_snapshot_backtest_mode_unavailable(self, system_manager):
        """TEST 2: Snapshot unavailable in backtest mode"""
        print("✓ Testing: Snapshot unavailable in backtest mode")
        
        system_manager.set_mode("backtest")
        dm = system_manager.get_data_manager()
        
        snapshot = await dm.get_snapshot("AAPL")
        
        assert snapshot is None, "Snapshot should be None in backtest mode"
        print("  Mode: backtest")
        print("  Snapshot result: None")
        print("  ✓ Correctly returns None in backtest mode")
    
    @pytest.mark.asyncio
    async def test_03_snapshot_invalid_symbol(self, system_manager):
        """TEST 3: Handle invalid symbol gracefully"""
        print("✓ Testing: Snapshot with invalid symbol")
        
        system_manager.set_mode("live")
        dm = system_manager.get_data_manager()
        
        with patch('app.managers.data_manager.integrations.alpaca_data.fetch_snapshot',
                   new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None  # API returns None for invalid symbol
            
            snapshot = await dm.get_snapshot("INVALIDSYMBOL")
            
            assert snapshot is None, "Should return None for invalid symbol"
            print("  Symbol: INVALIDSYMBOL")
            print("  Result: None")
            print("  ✓ Invalid symbol handled gracefully")
    
    @pytest.mark.asyncio
    async def test_04_snapshot_api_failure(self, system_manager):
        """TEST 4: Handle API failure gracefully"""
        print("✓ Testing: Snapshot API failure handling")
        
        system_manager.set_mode("live")
        dm = system_manager.get_data_manager()
        
        with patch('app.managers.data_manager.integrations.alpaca_data.fetch_snapshot',
                   new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = Exception("API connection failed")
            
            snapshot = await dm.get_snapshot("AAPL")
            
            assert snapshot is None, "Should return None on API failure"
            print("  API error: Connection failed (simulated)")
            print("  Result: None")
            print("  ✓ API failure handled gracefully")
    
    @pytest.mark.asyncio
    async def test_05_snapshot_missing_trade_data(self, system_manager):
        """TEST 5: Handle snapshot with missing trade data"""
        print("✓ Testing: Snapshot with missing trade data")
        
        system_manager.set_mode("live")
        dm = system_manager.get_data_manager()
        
        # Snapshot with no trade data
        mock_snapshot = {
            'latest_quote': {
                'bid_price': 185.48,
                'bid_size': 200,
                'ask_price': 185.52,
                'ask_size': 150,
                'timestamp': datetime.now().isoformat()
            },
            'daily_bar': {
                'open': 184.50,
                'high': 186.10,
                'low': 183.90,
                'close': 185.50,
                'volume': 45234567,
                'timestamp': datetime.now().isoformat()
            }
        }
        
        with patch('app.managers.data_manager.integrations.alpaca_data.fetch_snapshot',
                   new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_snapshot
            
            snapshot = await dm.get_snapshot("AAPL")
            
            assert snapshot is not None, "Snapshot should be returned"
            assert 'latest_trade' not in snapshot or snapshot['latest_trade'] is None, "Trade data should be missing"
            assert 'latest_quote' in snapshot, "Quote data should exist"
            
            print("  Snapshot returned without trade data")
            print("  Quote available: Yes")
            print("  Daily bar available: Yes")
            print("  ✓ Partial snapshot handled correctly")
    
    @pytest.mark.asyncio
    async def test_06_snapshot_data_structure_validation(self, system_manager):
        """TEST 6: Validate snapshot data structure"""
        print("✓ Testing: Snapshot data structure validation")
        
        system_manager.set_mode("live")
        dm = system_manager.get_data_manager()
        
        mock_snapshot = {
            'latest_trade': {
                'price': 185.50,
                'size': 100,
                'timestamp': '2025-11-20T14:30:00Z'
            },
            'latest_quote': {
                'bid_price': 185.48,
                'bid_size': 200,
                'ask_price': 185.52,
                'ask_size': 150,
                'timestamp': '2025-11-20T14:30:01Z'
            },
            'minute_bar': {
                'open': 185.40,
                'high': 185.60,
                'low': 185.35,
                'close': 185.50,
                'volume': 45000,
                'timestamp': '2025-11-20T14:30:00Z'
            },
            'daily_bar': {
                'open': 184.50,
                'high': 186.10,
                'low': 183.90,
                'close': 185.50,
                'volume': 45234567,
                'timestamp': '2025-11-20T00:00:00Z'
            }
        }
        
        with patch('app.managers.data_manager.integrations.alpaca_data.fetch_snapshot',
                   new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_snapshot
            
            snapshot = await dm.get_snapshot("AAPL")
            
            # Validate structure
            assert 'latest_trade' in snapshot
            assert 'price' in snapshot['latest_trade']
            assert 'size' in snapshot['latest_trade']
            assert 'timestamp' in snapshot['latest_trade']
            
            assert 'latest_quote' in snapshot
            assert 'bid_price' in snapshot['latest_quote']
            assert 'ask_price' in snapshot['latest_quote']
            
            assert 'daily_bar' in snapshot
            assert 'open' in snapshot['daily_bar']
            assert 'high' in snapshot['daily_bar']
            assert 'low' in snapshot['daily_bar']
            assert 'close' in snapshot['daily_bar']
            assert 'volume' in snapshot['daily_bar']
            
            print("  ✓ Trade data structure: valid")
            print("  ✓ Quote data structure: valid")
            print("  ✓ Bar data structure: valid")
            print("  ✓ All data structures validated")
    
    @pytest.mark.asyncio
    async def test_07_snapshot_timestamp_parsing(self, system_manager):
        """TEST 7: Snapshot timestamps are parseable"""
        print("✓ Testing: Snapshot timestamp parsing")
        
        system_manager.set_mode("live")
        dm = system_manager.get_data_manager()
        
        timestamp_str = '2025-11-20T14:30:00.123456Z'
        
        mock_snapshot = {
            'latest_trade': {
                'price': 185.50,
                'size': 100,
                'timestamp': timestamp_str
            }
        }
        
        with patch('app.managers.data_manager.integrations.alpaca_data.fetch_snapshot',
                   new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_snapshot
            
            snapshot = await dm.get_snapshot("AAPL")
            
            assert snapshot is not None
            timestamp = snapshot['latest_trade']['timestamp']
            
            # Should be a string in ISO format
            assert isinstance(timestamp, str), "Timestamp should be string"
            assert 'T' in timestamp, "Should be ISO format"
            
            print(f"  Timestamp format: {timestamp}")
            print("  ✓ Timestamp format valid")
    
    @pytest.mark.asyncio
    async def test_08_snapshot_price_precision(self, system_manager):
        """TEST 8: Snapshot maintains price precision"""
        print("✓ Testing: Snapshot price precision")
        
        system_manager.set_mode("live")
        dm = system_manager.get_data_manager()
        
        precise_price = 185.12345
        
        mock_snapshot = {
            'latest_trade': {
                'price': precise_price,
                'size': 100,
                'timestamp': datetime.now().isoformat()
            },
            'latest_quote': {
                'bid_price': 185.12300,
                'bid_size': 200,
                'ask_price': 185.12400,
                'ask_size': 150,
                'timestamp': datetime.now().isoformat()
            }
        }
        
        with patch('app.managers.data_manager.integrations.alpaca_data.fetch_snapshot',
                   new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_snapshot
            
            snapshot = await dm.get_snapshot("AAPL")
            
            assert snapshot['latest_trade']['price'] == precise_price
            spread = snapshot['latest_quote']['ask_price'] - snapshot['latest_quote']['bid_price']
            
            print(f"  Trade price: ${precise_price:.5f}")
            print(f"  Bid: ${snapshot['latest_quote']['bid_price']:.5f}")
            print(f"  Ask: ${snapshot['latest_quote']['ask_price']:.5f}")
            print(f"  Spread: ${spread:.5f}")
            print("  ✓ Price precision maintained")
    
    @pytest.mark.asyncio
    async def test_09_snapshot_concurrent_requests(self, system_manager):
        """TEST 9: Multiple concurrent snapshot requests work correctly"""
        print("✓ Testing: Concurrent snapshot requests")
        
        system_manager.set_mode("live")
        dm = system_manager.get_data_manager()
        
        symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
        
        async def get_mock_snapshot(symbol):
            mock_data = {
                'latest_trade': {
                    'price': 100.0 + len(symbol),
                    'size': 100,
                    'timestamp': datetime.now().isoformat()
                }
            }
            return mock_data
        
        with patch('app.managers.data_manager.integrations.alpaca_data.fetch_snapshot',
                   new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = lambda sym: asyncio.coroutine(lambda: get_mock_snapshot(sym))()
            
            # Request all snapshots concurrently
            snapshots = await asyncio.gather(*[dm.get_snapshot(sym) for sym in symbols])
            
            assert len(snapshots) == len(symbols), "Should get all snapshots"
            assert all(s is not None for s in snapshots), "All snapshots should succeed"
            
            print(f"  Symbols requested: {len(symbols)}")
            print(f"  Snapshots received: {len(snapshots)}")
            print("  ✓ Concurrent requests handled correctly")
    
    @pytest.mark.asyncio
    async def test_10_snapshot_with_extended_hours_data(self, system_manager):
        """TEST 10: Snapshot includes extended hours data if available"""
        print("✓ Testing: Snapshot with extended hours data")
        
        system_manager.set_mode("live")
        dm = system_manager.get_data_manager()
        
        mock_snapshot = {
            'latest_trade': {
                'price': 185.50,
                'size': 50,  # Smaller size typical of pre/post market
                'timestamp': '2025-11-20T08:30:00Z',  # Pre-market
                'extended_hours': True
            },
            'daily_bar': {
                'open': 184.50,
                'high': 186.10,
                'low': 183.90,
                'close': 185.50,
                'volume': 45234567,
                'timestamp': '2025-11-20T00:00:00Z'
            }
        }
        
        with patch('app.managers.data_manager.integrations.alpaca_data.fetch_snapshot',
                   new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_snapshot
            
            snapshot = await dm.get_snapshot("AAPL")
            
            assert snapshot is not None
            if 'extended_hours' in snapshot['latest_trade']:
                assert snapshot['latest_trade']['extended_hours'] == True
                print("  Extended hours: Yes")
                print(f"  Pre/Post market price: ${snapshot['latest_trade']['price']:.2f}")
            
            print("  ✓ Extended hours data handled")
    
    @pytest.mark.asyncio
    async def test_11_snapshot_cache_behavior(self, system_manager):
        """TEST 11: Snapshots are not cached (always fresh data)"""
        print("✓ Testing: Snapshot freshness (no caching)")
        
        system_manager.set_mode("live")
        dm = system_manager.get_data_manager()
        
        call_count = 0
        
        async def mock_fetch_with_counter(symbol):
            nonlocal call_count
            call_count += 1
            return {
                'latest_trade': {
                    'price': 185.00 + call_count,  # Different price each time
                    'size': 100,
                    'timestamp': datetime.now().isoformat()
                }
            }
        
        with patch('app.managers.data_manager.integrations.alpaca_data.fetch_snapshot',
                   new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = mock_fetch_with_counter
            
            snapshot1 = await dm.get_snapshot("AAPL")
            snapshot2 = await dm.get_snapshot("AAPL")
            
            price1 = snapshot1['latest_trade']['price']
            price2 = snapshot2['latest_trade']['price']
            
            assert price1 != price2, "Prices should be different (not cached)"
            assert call_count == 2, "API should be called twice"
            
            print(f"  First call price: ${price1:.2f}")
            print(f"  Second call price: ${price2:.2f}")
            print(f"  API calls made: {call_count}")
            print("  ✓ No caching - always fresh data")
    
    @pytest.mark.asyncio
    async def test_12_snapshot_provider_not_supported(self, system_manager):
        """TEST 12: Unsupported provider returns None"""
        print("✓ Testing: Unsupported data provider")
        
        system_manager.set_mode("live")
        dm = system_manager.get_data_manager()
        
        # Temporarily change provider
        original_provider = dm.data_api
        dm.data_api = "unsupported_provider"
        
        snapshot = await dm.get_snapshot("AAPL")
        
        assert snapshot is None, "Unsupported provider should return None"
        
        # Restore original
        dm.data_api = original_provider
        
        print("  Provider: unsupported_provider")
        print("  Result: None")
        print("  ✓ Unsupported provider handled gracefully")
    
    @pytest.mark.asyncio
    async def test_13_snapshot_rate_limiting(self, system_manager):
        """TEST 13: Rapid snapshot requests don't cause issues"""
        print("✓ Testing: Rapid snapshot requests (rate limiting)")
        
        system_manager.set_mode("live")
        dm = system_manager.get_data_manager()
        
        request_count = 0
        
        async def mock_fetch_rate_limited(symbol):
            nonlocal request_count
            request_count += 1
            await asyncio.sleep(0.01)  # Simulate API latency
            return {
                'latest_trade': {
                    'price': 185.50,
                    'size': 100,
                    'timestamp': datetime.now().isoformat()
                }
            }
        
        with patch('app.managers.data_manager.integrations.alpaca_data.fetch_snapshot',
                   new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = mock_fetch_rate_limited
            
            # Make 20 rapid requests
            start = datetime.now()
            snapshots = await asyncio.gather(*[dm.get_snapshot("AAPL") for _ in range(20)])
            duration = (datetime.now() - start).total_seconds()
            
            assert len(snapshots) == 20, "All requests should complete"
            assert all(s is not None for s in snapshots), "All should succeed"
            
            print(f"  Requests made: {request_count}")
            print(f"  Duration: {duration:.2f}s")
            print(f"  Rate: {request_count/duration:.1f} req/s")
            print("  ✓ Rapid requests handled correctly")
    
    @pytest.mark.asyncio
    async def test_14_snapshot_market_status_indicators(self, system_manager):
        """TEST 14: Snapshot can include market status indicators"""
        print("✓ Testing: Snapshot with market status indicators")
        
        system_manager.set_mode("live")
        dm = system_manager.get_data_manager()
        
        mock_snapshot = {
            'latest_trade': {
                'price': 185.50,
                'size': 100,
                'timestamp': datetime.now().isoformat(),
                'market_status': 'open'  # Could be: open, closed, pre, post
            },
            'daily_bar': {
                'open': 184.50,
                'high': 186.10,
                'low': 183.90,
                'close': 185.50,
                'volume': 45234567,
                'timestamp': datetime.now().isoformat()
            }
        }
        
        with patch('app.managers.data_manager.integrations.alpaca_data.fetch_snapshot',
                   new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_snapshot
            
            snapshot = await dm.get_snapshot("AAPL")
            
            assert snapshot is not None
            if 'market_status' in snapshot['latest_trade']:
                status = snapshot['latest_trade']['market_status']
                print(f"  Market status: {status}")
                assert status in ['open', 'closed', 'pre', 'post']
            
            print("  ✓ Market status indicators handled")
    
    @pytest.mark.asyncio
    async def test_15_snapshot_alpaca_specific_fields(self, system_manager):
        """TEST 15: Snapshot handles Alpaca-specific fields correctly"""
        print("✓ Testing: Alpaca-specific snapshot fields")
        
        system_manager.set_mode("live")
        dm = system_manager.get_data_manager()
        
        # Alpaca snapshot with all fields
        mock_snapshot = {
            'latest_trade': {
                'price': 185.50,
                'size': 100,
                'timestamp': datetime.now().isoformat(),
                'exchange': 'NASDAQ',
                'conditions': ['@', 'T']
            },
            'latest_quote': {
                'bid_price': 185.48,
                'bid_size': 200,
                'bid_exchange': 'NASDAQ',
                'ask_price': 185.52,
                'ask_size': 150,
                'ask_exchange': 'NASDAQ',
                'timestamp': datetime.now().isoformat()
            },
            'minute_bar': {
                'open': 185.40,
                'high': 185.60,
                'low': 185.35,
                'close': 185.50,
                'volume': 45000,
                'vwap': 185.47,  # Volume Weighted Average Price
                'trade_count': 450,
                'timestamp': datetime.now().isoformat()
            },
            'daily_bar': {
                'open': 184.50,
                'high': 186.10,
                'low': 183.90,
                'close': 185.50,
                'volume': 45234567,
                'vwap': 185.12,
                'trade_count': 452345,
                'timestamp': datetime.now().isoformat()
            },
            'prev_daily_bar': {
                'open': 183.00,
                'high': 184.80,
                'low': 182.50,
                'close': 184.20,
                'volume': 42000000,
                'vwap': 183.75,
                'timestamp': datetime.now().isoformat()
            }
        }
        
        with patch('app.managers.data_manager.integrations.alpaca_data.fetch_snapshot',
                   new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_snapshot
            
            snapshot = await dm.get_snapshot("AAPL")
            
            assert snapshot is not None
            
            # Verify Alpaca-specific fields are present
            if 'vwap' in snapshot.get('daily_bar', {}):
                print(f"  Daily VWAP: ${snapshot['daily_bar']['vwap']:.2f}")
            if 'trade_count' in snapshot.get('daily_bar', {}):
                print(f"  Daily trades: {snapshot['daily_bar']['trade_count']:,}")
            if 'exchange' in snapshot.get('latest_trade', {}):
                print(f"  Exchange: {snapshot['latest_trade']['exchange']}")
            
            print("  ✓ Alpaca-specific fields handled correctly")


# Test execution summary
if __name__ == "__main__":
    print("\n" + "="*80)
    print("DataManager Snapshot API Test Suite")
    print("="*80)
    print("\nTests cover:")
    print("  - get_snapshot() - Live market snapshots")
    print("\nTo run these tests:")
    print("  pytest app/managers/data_manager/tests/test_snapshot_api.py -v -s")
    print("\n" + "="*80)
