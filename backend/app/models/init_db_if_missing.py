"""One-shot database initialization helper.

This script is safe to run multiple times. It will:

- Inspect settings.DATABASE_URL (expected to be sqlite+aiosqlite:///...)
- Resolve the underlying SQLite file path
- If the file already exists and has tables, it does nothing
- If the file does not exist (or is empty), it creates all tables

Usage (from project root):

    source .venv/bin/activate
    python -m app.models.init_db_if_missing

"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Sequence

from sqlalchemy import inspect

from app.config import settings
from app.models.database import Base, engine
import app.models  # noqa: F401  # ensure all models are imported & registered with Base
from app.logger import logger


def _sqlite_path_from_url(url: str) -> Path | None:
    """Extract the SQLite file path from a DATABASE_URL, if applicable."""
    prefix = "sqlite+aiosqlite:///"
    if not url.startswith(prefix):
        return None
    return Path(url.replace(prefix, ""))


async def _init_db_if_needed() -> None:
    db_path = _sqlite_path_from_url(settings.DATABASE_URL)

    if db_path is None:
        logger.info(
            "DATABASE_URL is not sqlite+aiosqlite (got %s); init_db_if_missing will just create_all on current engine",
            settings.DATABASE_URL,
        )
    else:
        # Ensure parent directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)

    async with engine.begin() as conn:
        # Inspect existing tables
        def get_tables(sync_conn) -> Sequence[str]:
            insp = inspect(sync_conn)
            return insp.get_table_names()

        existing_tables = await conn.run_sync(get_tables)

        if existing_tables:
            logger.info("Database already initialized with tables: %s", ", ".join(existing_tables))
            return

        # No tables yet: create all
        logger.info("No tables found; creating all tables via Base.metadata.create_all()")
        await conn.run_sync(Base.metadata.create_all)

        # Log the resulting tables
        def show_tables(sync_conn):
            insp = inspect(sync_conn)
            tables = insp.get_table_names()
            logger.info("Database initialized with tables: %s", ", ".join(tables))

        await conn.run_sync(show_tables)


def main() -> None:
    asyncio.run(_init_db_if_needed())


if __name__ == "__main__":
    main()
