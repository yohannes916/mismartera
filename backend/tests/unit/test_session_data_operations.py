"""Unit Tests for SessionData Operations

Tests basic SessionData operations like registration, retrieval, clearing.
"""
import pytest
from datetime import datetime
from app.managers.data_manager.session_data import SessionData, SymbolSessionData


class TestSymbolRegistration:
    """Test symbol registration in SessionData."""
    
    def test_register_single_symbol(self):
        """Test registering a single symbol."""
        session_data = SessionData()
        
        symbol = SymbolSessionData(
            symbol="AAPL",
            base_interval="1m",
            added_at=datetime.now()
        )
        
        session_data.register_symbol_data(symbol)
        
        assert "AAPL" in session_data._symbols
        assert session_data.get_symbol_data("AAPL") is not None
        assert session_data.get_symbol_data("AAPL").symbol == "AAPL"
    
    def test_register_multiple_symbols(self):
        """Test registering multiple symbols."""
        session_data = SessionData()
        
        for ticker in ["AAPL", "MSFT", "GOOGL"]:
            symbol = SymbolSessionData(
                symbol=ticker,
                base_interval="1m",
                added_at=datetime.now()
            )
            session_data.register_symbol_data(symbol)
        
        assert len(session_data._symbols) == 3
        assert "AAPL" in session_data._symbols
        assert "MSFT" in session_data._symbols
        assert "GOOGL" in session_data._symbols


class TestSymbolRetrieval:
    """Test symbol data retrieval."""
    
    def test_get_existing_symbol(self):
        """Test retrieving existing symbol."""
        session_data = SessionData()
        
        symbol = SymbolSessionData(
            symbol="AAPL",
            base_interval="1m",
            added_at=datetime.now()
        )
        session_data.register_symbol_data(symbol)
        
        retrieved = session_data.get_symbol_data("AAPL")
        
        assert retrieved is not None
        assert retrieved.symbol == "AAPL"
    
    def test_get_nonexistent_symbol(self):
        """Test retrieving non-existent symbol returns None."""
        session_data = SessionData()
        
        retrieved = session_data.get_symbol_data("DOESNOTEXIST")
        
        assert retrieved is None
    
    def test_get_symbol_case_insensitive(self):
        """Test symbol retrieval is case-insensitive."""
        session_data = SessionData()
        
        symbol = SymbolSessionData(
            symbol="AAPL",
            base_interval="1m",
            added_at=datetime.now()
        )
        session_data.register_symbol_data(symbol)
        
        # Try different cases
        assert session_data.get_symbol_data("AAPL") is not None
        assert session_data.get_symbol_data("aapl") is not None
        assert session_data.get_symbol_data("Aapl") is not None


class TestSessionClearing:
    """Test session clearing operations."""
    
    def test_clear_session(self):
        """Test clearing session data."""
        session_data = SessionData()
        
        # Add some symbols
        for ticker in ["AAPL", "MSFT", "GOOGL"]:
            symbol = SymbolSessionData(
                symbol=ticker,
                base_interval="1m",
                added_at=datetime.now()
            )
            session_data.register_symbol_data(symbol)
        
        assert len(session_data._symbols) == 3
        
        # Clear
        session_data.clear()
        
        assert len(session_data._symbols) == 0


class TestSymbolCount:
    """Test symbol counting."""
    
    def test_count_symbols(self):
        """Test counting symbols in session."""
        session_data = SessionData()
        
        assert len(session_data._symbols) == 0
        
        # Add symbols
        for i in range(5):
            symbol = SymbolSessionData(
                symbol=f"SYM{i}",
                base_interval="1m",
                added_at=datetime.now()
            )
            session_data.register_symbol_data(symbol)
        
        assert len(session_data._symbols) == 5


class TestSymbolReplacement:
    """Test replacing existing symbol."""
    
    def test_replace_symbol_data(self):
        """Test that registering same symbol replaces it."""
        session_data = SessionData()
        
        # Register first version
        symbol1 = SymbolSessionData(
            symbol="AAPL",
            base_interval="1m",
            added_by="scanner",
            added_at=datetime.now()
        )
        session_data.register_symbol_data(symbol1)
        
        assert session_data.get_symbol_data("AAPL").added_by == "scanner"
        
        # Register second version (same symbol)
        symbol2 = SymbolSessionData(
            symbol="AAPL",
            base_interval="1m",
            added_by="strategy",
            added_at=datetime.now()
        )
        session_data.register_symbol_data(symbol2)
        
        # Should have replaced
        assert session_data.get_symbol_data("AAPL").added_by == "strategy"
        assert len(session_data._symbols) == 1  # Still only one


class TestSessionIterationn:
    """Test iterating over session symbols."""
    
    def test_iterate_symbols(self):
        """Test iterating over all symbols."""
        session_data = SessionData()
        
        tickers = ["AAPL", "MSFT", "GOOGL"]
        for ticker in tickers:
            symbol = SymbolSessionData(
                symbol=ticker,
                base_interval="1m",
                added_at=datetime.now()
            )
            session_data.register_symbol_data(symbol)
        
        # Iterate
        symbols_found = [symbol for symbol in session_data._symbols.keys()]
        
        assert len(symbols_found) == 3
        for ticker in tickers:
            assert ticker in symbols_found
