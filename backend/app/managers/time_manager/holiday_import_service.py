"""
Holiday Import Service
Handles importing holidays from JSON or CSV files with exchange awareness
"""
import json
import csv
from pathlib import Path
from datetime import date, time as dt_time, datetime
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session

from app.logger import logger
from app.managers.time_manager.exchange_groups import (
    is_valid_group,
    get_group_metadata
)
from app.managers.time_manager.repositories import TradingCalendarRepository


class HolidayImportService:
    """Service for importing holiday data with exchange awareness"""
    
    @staticmethod
    def import_from_file(
        session: Session,
        file_path: str,
        exchange_override: Optional[str] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Import holidays from JSON or CSV file
        
        Args:
            session: Database session
            file_path: Path to holiday file (.json or .csv)
            exchange_override: Override exchange/group from file
            dry_run: If True, validate only (don't import)
            
        Returns:
            Dict with import results:
                - success: bool
                - holidays_count: int (unique holidays)
                - exchanges: List[str] (affected exchanges)
                - inserted: int (total DB entries)
                - error: str (if failed)
        """
        path = Path(file_path)
        
        if not path.exists():
            return {
                "success": False,
                "error": f"File not found: {file_path}"
            }
        
        logger.info(f"Importing holidays from: {file_path}")
        
        if path.suffix == '.json':
            return HolidayImportService._import_json(
                session, path, exchange_override, dry_run
            )
        elif path.suffix == '.csv':
            return HolidayImportService._import_csv(
                session, path, exchange_override, dry_run
            )
        else:
            return {
                "success": False,
                "error": f"Unsupported file format: {path.suffix} (use .json or .csv)"
            }
    
    @staticmethod
    def _import_json(
        session: Session,
        path: Path,
        exchange_override: Optional[str],
        dry_run: bool
    ) -> Dict[str, Any]:
        """Import from JSON format"""
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            
            # Extract metadata
            exchange_group = exchange_override or data.get('exchange_group')
            if not exchange_group:
                # Try to get from exchanges list
                exchanges_list = data.get('exchanges', [])
                if exchanges_list:
                    exchange_group = exchanges_list[0]
                else:
                    exchange_group = 'NYSE'  # Fallback
            
            country = data.get('country', 'Unknown')
            timezone = data.get('timezone', 'UTC')
            description = data.get('description', '')
            
            # Store at exchange group level (no expansion)
            # e.g., US_EQUITY stored once, not NYSE+NASDAQ+AMEX+ARCA separately
            
            # Parse holidays
            holidays_data = []
            
            # Support both flat list and multi-year structure
            if 'holidays' in data:
                # Flat list format
                for h in data['holidays']:
                    parsed_holiday = HolidayImportService._parse_json_holiday(h)
                    if parsed_holiday:
                        holidays_data.append(parsed_holiday)
                        
            elif 'years' in data:
                # Multi-year format
                for year, year_holidays in data['years'].items():
                    for h in year_holidays:
                        parsed_holiday = HolidayImportService._parse_json_holiday(h)
                        if parsed_holiday:
                            holidays_data.append(parsed_holiday)
            else:
                return {
                    "success": False,
                    "error": "JSON file must contain 'holidays' or 'years' field"
                }
            
            if not holidays_data:
                return {
                    "success": False,
                    "error": "No valid holidays found in file"
                }
            
            # Dry run - just validate
            if dry_run:
                return {
                    "success": True,
                    "dry_run": True,
                    "holidays_count": len(holidays_data),
                    "exchanges": [exchange_group],
                    "would_insert": len(holidays_data),
                    "country": country,
                    "timezone": timezone,
                    "description": description
                }
            
            # Import once for the exchange group
            count = TradingCalendarRepository.bulk_create_holidays(
                session, holidays_data, exchange_group=exchange_group
            )
            logger.info(f"Imported {count} holidays for {exchange_group}")
            total_imported = count
            
            return {
                "success": True,
                "inserted": total_imported,
                "exchanges": [exchange_group],
                "holidays_count": len(holidays_data),
                "country": country,
                "timezone": timezone,
                "description": description
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return {"success": False, "error": f"Invalid JSON: {e}"}
        except Exception as e:
            logger.error(f"JSON import error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def _parse_json_holiday(h: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a single holiday from JSON format
        
        Args:
            h: Holiday dict from JSON
            
        Returns:
            Parsed holiday dict or None if invalid
        """
        try:
            # Parse date
            holiday_date = date.fromisoformat(h['date'])
            
            # Parse type (full_close or early_close)
            holiday_type = h.get('type', 'full_close')
            is_closed = holiday_type == 'full_close'
            
            # Parse early close time if present
            early_close = None
            if not is_closed and h.get('early_close_time'):
                try:
                    early_close = dt_time.fromisoformat(h['early_close_time'])
                except:
                    logger.warning(f"Invalid early_close_time: {h.get('early_close_time')}")
            
            return {
                'date': holiday_date,
                'holiday_name': h.get('name', h.get('holiday_name', '')),
                'is_closed': is_closed,
                'early_close_time': early_close,
                'notes': h.get('notes')
            }
        except Exception as e:
            logger.warning(f"Failed to parse holiday {h}: {e}")
            return None
    
    @staticmethod
    def _import_csv(
        session: Session,
        path: Path,
        exchange_override: Optional[str],
        dry_run: bool
    ) -> Dict[str, Any]:
        """Import from CSV format (backward compatible)"""
        try:
            with open(path, 'r') as f:
                reader = csv.DictReader(f)
                holidays_data = []
                
                for row in reader:
                    # Skip empty rows
                    if not row.get('Date'):
                        continue
                    
                    # Parse date - handle multiple formats
                    try:
                        date_str = row['Date'].strip().strip('"')
                        
                        # Try ISO format first (2024-01-01)
                        try:
                            holiday_date = date.fromisoformat(date_str)
                        except:
                            # Try full text format (Wednesday, January 1, 2025)
                            # Remove day name if present
                            if ',' in date_str:
                                parts = date_str.split(',')
                                if len(parts) >= 3:  # "Wednesday, January 1, 2025"
                                    date_str = ','.join(parts[1:]).strip()  # "January 1, 2025"
                                
                            # Parse with multiple formats
                            for fmt in ['%B %d, %Y', '%b %d, %Y', '%m/%d/%Y', '%Y-%m-%d']:
                                try:
                                    holiday_date = datetime.strptime(date_str, fmt).date()
                                    break
                                except:
                                    continue
                            else:
                                raise ValueError(f"Could not parse date: {row['Date']}")
                    except Exception as e:
                        logger.warning(f"Invalid date in CSV: {row.get('Date')} - {e}")
                        continue
                    
                    # Parse early close time
                    early_close = None
                    if row.get('Early Close Time'):
                        try:
                            early_close = dt_time.fromisoformat(row['Early Close Time'])
                        except:
                            pass
                    
                    # Get exchange from row or use override
                    exchange_group = exchange_override
                    if not exchange_group and 'Exchange Group' in row and row['Exchange Group']:
                        exchange_group = row['Exchange Group']
                    if not exchange_group:
                        exchange_group = 'NYSE'  # Default fallback
                    
                    holidays_data.append({
                        'date': holiday_date,
                        'holiday_name': row.get('Holiday Name', ''),
                        'is_closed': early_close is None,
                        'early_close_time': early_close,
                        'notes': row.get('Notes'),
                        'exchange_group': exchange_group
                    })
            
            if not holidays_data:
                return {
                    "success": False,
                    "error": "No valid holidays found in CSV"
                }
            
            # Group by exchange_group (no expansion)
            by_exchange_group = {}
            for h in holidays_data:
                exch_group = h.pop('exchange_group')
                if exch_group not in by_exchange_group:
                    by_exchange_group[exch_group] = []
                # Avoid duplicates
                if h not in by_exchange_group[exch_group]:
                    by_exchange_group[exch_group].append(h)
            
            # Calculate totals
            total_holidays = len(set(h['date'] for group_holidays in by_exchange_group.values() for h in group_holidays))
            total_entries = sum(len(group_holidays) for group_holidays in by_exchange_group.values())
            
            # Dry run - just validate
            if dry_run:
                return {
                    "success": True,
                    "dry_run": True,
                    "holidays_count": total_holidays,
                    "exchanges": list(by_exchange_group.keys()),
                    "would_insert": total_entries
                }
            
            # Import for each exchange group (no expansion)
            total_imported = 0
            for exch_group, group_holidays in by_exchange_group.items():
                count = TradingCalendarRepository.bulk_create_holidays(
                    session, group_holidays, exchange_group=exch_group
                )
                total_imported += count
                logger.info(f"Imported {count} holidays for {exch_group}")
            
            return {
                "success": True,
                "inserted": total_imported,
                "exchanges": list(by_exchange_group.keys()),
                "holidays_count": total_holidays
            }
            
        except Exception as e:
            logger.error(f"CSV import error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
