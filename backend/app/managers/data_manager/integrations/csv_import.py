"""
CSV Import Service
Parse and import historical OHLCV data from CSV files into database
"""
import csv
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.market_data_repository import MarketDataRepository
from app.logger import logger


class CSVImportService:
    """
    Service for importing market data from CSV files
    Expected format: Date, Time, Open, High, Low, Close, Volume
    """
    
    @staticmethod
    def parse_csv_file(
        file_path: str,
        symbol: str,
        date_format: str = "%Y-%m-%d",
        time_format: str = "%H:%M:%S",
        skip_header: bool = True
    ) -> List[Dict]:
        """
        Parse CSV file into list of bar dictionaries
        
        Args:
            file_path: Path to CSV file
            symbol: Stock symbol for this data
            date_format: Date format string (default: auto-detect, supports YYYY-MM-DD, MM/DD/YYYY, DD/MM/YYYY)
            time_format: Time format string (default: HH:MM:SS, also accepts HH:MM)
            skip_header: Skip first row as header
            
        Returns:
            List of dictionaries with bar data
            
        Expected CSV format (time can be HH:MM or HH:MM:SS):
            Date,Time,Open,High,Low,Close,Volume
            2024-01-15,09:30:00,180.50,181.20,180.10,180.90,1000000
            2024-01-15,09:31,180.90,181.00,180.70,180.85,950000
        """
        bars = []
        errors = []
        
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {file_path}")
        
        with open(file_path, 'r') as f:
            reader = csv.reader(f)
            
            if skip_header:
                next(reader, None)  # Skip header row
            
            for row_num, row in enumerate(reader, start=2 if skip_header else 1):
                try:
                    if len(row) < 7:
                        errors.append(f"Row {row_num}: Insufficient columns ({len(row)}/7)")
                        continue
                    
                    # Parse date and time
                    date_str = row[0].strip()
                    time_str = row[1].strip()
                    
                    # Handle flexible time formats (HH:MM:SS or HH:MM)
                    # If time_str doesn't have seconds, add :00
                    if time_str.count(':') == 1:  # HH:MM format
                        time_str = f"{time_str}:00"
                        actual_time_format = "%H:%M:%S"
                    else:  # HH:MM:SS format
                        actual_time_format = time_format
                    
                    # Auto-detect date format and parse
                    timestamp = None
                    date_formats_to_try = [
                        date_format,           # User-specified format
                        "%Y-%m-%d",           # YYYY-MM-DD
                        "%m/%d/%Y",           # MM/DD/YYYY
                        "%d/%m/%Y",           # DD/MM/YYYY
                        "%Y/%m/%d",           # YYYY/MM/DD
                    ]
                    
                    datetime_str = f"{date_str} {time_str}"
                    
                    for fmt in date_formats_to_try:
                        try:
                            timestamp = datetime.strptime(
                                datetime_str,
                                f"{fmt} {actual_time_format}"
                            )
                            break  # Success, stop trying
                        except ValueError:
                            continue  # Try next format
                    
                    if timestamp is None:
                        raise ValueError(f"Could not parse date '{date_str}' with any known format")
                    
                    # Parse OHLCV
                    bar = {
                        'symbol': symbol.upper(),
                        'timestamp': timestamp,
                        'interval': '1m',  # Assuming 1-minute bars
                        'open': float(row[2]),
                        'high': float(row[3]),
                        'low': float(row[4]),
                        'close': float(row[5]),
                        'volume': float(row[6])
                    }
                    
                    # Validate data
                    if not CSVImportService._validate_bar(bar):
                        errors.append(f"Row {row_num}: Invalid OHLCV data")
                        continue
                    
                    bars.append(bar)
                    
                except ValueError as e:
                    errors.append(f"Row {row_num}: Parse error - {str(e)}")
                    continue
                except Exception as e:
                    errors.append(f"Row {row_num}: Unexpected error - {str(e)}")
                    continue
        
        logger.info(f"Parsed CSV: {len(bars)} valid bars, {len(errors)} errors")
        
        if errors:
            logger.warning(f"CSV parse errors:\n" + "\n".join(errors[:10]))  # Log first 10 errors
        
        return bars
    
    @staticmethod
    def _validate_bar(bar: Dict) -> bool:
        """
        Validate bar data integrity
        
        Args:
            bar: Bar dictionary
            
        Returns:
            True if valid, False otherwise
        """
        try:
            # Check positive values
            if bar['open'] <= 0 or bar['high'] <= 0 or bar['low'] <= 0 or bar['close'] <= 0:
                return False
            
            # Check high >= low
            if bar['high'] < bar['low']:
                return False
            
            # Check high >= open, close
            if bar['high'] < bar['open'] or bar['high'] < bar['close']:
                return False
            
            # Check low <= open, close
            if bar['low'] > bar['open'] or bar['low'] > bar['close']:
                return False
            
            # Check volume is non-negative
            if bar['volume'] < 0:
                return False
            
            return True
            
        except (KeyError, TypeError):
            return False
    
    @staticmethod
    async def import_csv_to_database(
        session: AsyncSession,
        file_path: str,
        symbol: str,
        date_format: str = "%Y-%m-%d",
        time_format: str = "%H:%M:%S",
        skip_header: bool = True,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        batch_size: int = 1000
    ) -> Dict:
        """
        Import CSV file directly into database
        
        Args:
            session: Database session
            file_path: Path to CSV file
            symbol: Stock symbol
            date_format: Date format string
            time_format: Time format string
            skip_header: Skip header row
            start_date: Optional start date filter (inclusive)
            end_date: Optional end date filter (inclusive)
            batch_size: Number of bars to insert per batch (upsert on duplicate)
            
        Returns:
            Dictionary with import statistics
        """
        logger.info(f"Starting CSV import: {file_path} for {symbol}")
        
        # Parse CSV
        bars = CSVImportService.parse_csv_file(
            file_path,
            symbol,
            date_format,
            time_format,
            skip_header
        )
        
        if not bars:
            return {
                'success': False,
                'message': 'No valid bars found in CSV',
                'total_rows': 0,
                'imported': 0,
                'skipped': 0,
                'errors': []
            }
        
        # Filter by date range if specified
        total_before_filter = len(bars)
        if start_date or end_date:
            filtered_bars = []
            for bar in bars:
                bar_date = bar['timestamp']
                if start_date and bar_date < start_date:
                    continue
                if end_date and bar_date > end_date:
                    continue
                filtered_bars.append(bar)
            
            bars = filtered_bars
            filtered_count = total_before_filter - len(bars)
            logger.info(f"Date filter applied: {len(bars)}/{total_before_filter} bars kept (filtered {filtered_count})")
        
        # Filter to only include regular trading hours (9:30 AM - 4:00 PM ET)
        # This excludes pre-market and after-hours data
        from datetime import time as dt_time
        market_open = dt_time(9, 30, 0)
        market_close = dt_time(16, 0, 0)
        
        before_hours_filter = len(bars)
        bars = [
            bar for bar in bars
            if market_open <= bar['timestamp'].time() < market_close
        ]
        hours_filtered = before_hours_filter - len(bars)
        
        if hours_filtered > 0:
            logger.info(
                f"Trading hours filter: {len(bars)}/{before_hours_filter} bars kept "
                f"(filtered {hours_filtered} outside 9:30-16:00 ET)"
            )
        
        total_bars = len(bars)
        imported = 0
        
        # Import in batches (upsert - insert or update)
        for i in range(0, total_bars, batch_size):
            batch = bars[i:i + batch_size]
            
            try:
                batch_imported, _ = await MarketDataRepository.bulk_create_bars(
                    session,
                    batch
                )
                imported += batch_imported
                
                logger.info(
                    f"Batch {i//batch_size + 1}: "
                    f"Imported {batch_imported}/{len(batch)} bars"
                )
                
            except Exception as e:
                logger.error(f"Batch import failed: {e}")
                if not skip_duplicates:
                    raise
        
        # Get data quality metrics
        quality = await MarketDataRepository.check_data_quality(session, symbol)
        
        result = {
            'success': True,
            'message': f'Successfully imported {imported} bars for {symbol}',
            'total_rows': total_bars,
            'imported': imported,
            'symbol': symbol.upper(),
            'date_range': quality.get('date_range'),
            'quality_score': quality.get('quality_score'),
            'missing_bars': quality.get('missing_bars', 0)
        }
        
        logger.success(
            f"CSV import complete: {imported}/{total_bars} bars upserted "
            f"(quality: {quality.get('quality_score', 0):.1%})"
        )
        
        return result
    
    @staticmethod
    async def import_csv_from_bytes(
        session: AsyncSession,
        file_content: bytes,
        symbol: str,
        filename: str,
        date_format: str = "%Y-%m-%d",
        time_format: str = "%H:%M:%S",
        skip_header: bool = True
    ) -> Dict:
        """
        Import CSV from uploaded file bytes (for API uploads)
        
        Args:
            session: Database session
            file_content: File content as bytes
            symbol: Stock symbol
            filename: Original filename
            date_format: Date format string
            time_format: Time format string
            skip_header: Skip header row
            skip_duplicates: Skip duplicate bars
            
        Returns:
            Dictionary with import statistics
        """
        import tempfile
        
        # Write bytes to temporary file
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as tmp_file:
            tmp_file.write(file_content)
            tmp_path = tmp_file.name
        
        try:
            # Import from temp file
            result = await CSVImportService.import_csv_to_database(
                session=session,
                file_path=tmp_path,
                symbol=symbol,
                date_format=date_format,
                time_format=time_format,
                skip_header=skip_header
            )
            
            result['filename'] = filename
            return result
            
        finally:
            # Clean up temp file
            Path(tmp_path).unlink(missing_ok=True)


# Global instance
csv_import_service = CSVImportService()
