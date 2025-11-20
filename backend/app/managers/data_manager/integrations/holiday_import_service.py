"""Holiday Schedule Import Service (DataManager integration)

Parses and imports market holidays from CSV files into the trading calendar
via repositories.
"""
import csv
from datetime import datetime, time
from typing import List, Dict
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.trading_calendar_repository import TradingCalendarRepository
from app.logger import logger


class HolidayImportService:
    """Service for importing holiday schedules from CSV"""

    @staticmethod
    def parse_holiday_csv(file_path: str) -> List[Dict]:
        """Parse holiday CSV file.

        Expected CSV format (header names):
            Date,Holiday Name,Notes,Early Close Time
        """
        holidays: List[Dict] = []
        errors: List[str] = []

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Holiday file not found: {file_path}")

        with open(file_path, "r") as f:
            reader = csv.DictReader(f)

            for row_num, row in enumerate(reader, start=2):
                try:
                    date_str = row.get("Date", "").strip().strip('"')
                    holiday_name = row.get("Holiday Name", "").strip().strip('"')
                    notes = row.get("Notes", "").strip()
                    early_close_str = row.get("Early Close Time", "").strip()

                    if not date_str or not holiday_name:
                        errors.append(f"Row {row_num}: Missing date or holiday name")
                        continue

                    parsed_date = None
                    date_formats = [
                        "%A, %B %d, %Y",  # Wednesday, January 1, 2025
                        "%B %d, %Y",      # January 1, 2025
                        "%Y-%m-%d",       # 2025-01-01
                        "%m/%d/%Y",       # 01/01/2025
                    ]

                    for fmt in date_formats:
                        try:
                            parsed_date = datetime.strptime(date_str, fmt).date()
                            break
                        except ValueError:
                            continue

                    if not parsed_date:
                        errors.append(f"Row {row_num}: Could not parse date '{date_str}'")
                        continue

                    early_close_time = None
                    if early_close_str:
                        try:
                            if ":" in early_close_str:
                                early_close_time = time.fromisoformat(early_close_str)
                            else:
                                early_close_time = time(int(early_close_str), 0)
                        except Exception as e:  # noqa: BLE001
                            logger.warning(
                                "Could not parse early close time '%s': %s",
                                early_close_str,
                                e,
                            )

                    is_closed = early_close_time is None

                    holiday = {
                        "date": parsed_date,
                        "holiday_name": holiday_name,
                        "notes": notes if notes else None,
                        "is_closed": is_closed,
                        "early_close_time": early_close_time,
                    }

                    holidays.append(holiday)

                except Exception as e:  # noqa: BLE001
                    errors.append(f"Row {row_num}: Unexpected error - {str(e)}")
                    continue

        logger.info(
            "Parsed holiday CSV: %s valid holidays, %s errors", len(holidays), len(errors)
        )

        if errors:
            logger.warning(
                "Holiday parse errors (showing up to 10):\n%s",
                "\n".join(errors[:10]),
            )

        return holidays

    @staticmethod
    async def import_holidays_to_database(
        session: AsyncSession,
        file_path: str,
    ) -> Dict:
        """Import holiday CSV file directly into database.

        Args:
            session: Database session
            file_path: Path to CSV file

        Returns:
            Dictionary with import statistics
        """
        logger.info("Starting holiday import: %s", file_path)

        holidays = HolidayImportService.parse_holiday_csv(file_path)

        if not holidays:
            return {
                "success": False,
                "message": "No valid holidays found in CSV",
                "total_rows": 0,
                "imported": 0,
            }

        imported = await TradingCalendarRepository.bulk_create_holidays(
            session,
            holidays,
        )

        result = {
            "success": True,
            "message": f"Successfully imported {imported} holidays",
            "total_rows": len(holidays),
            "imported": imported,
            "year": holidays[0]["date"].year if holidays else None,
        }

        logger.success("Holiday import complete: %s holidays imported", imported)

        return result


holiday_import_service = HolidayImportService()
