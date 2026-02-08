import logging
from pathlib import Path

import asyncpg

logger = logging.getLogger(__name__)

def _find_migrations_dir() -> Path:
    """Find migrations dir — works both in dev (source tree) and Docker (/app)."""
    # Try relative to source tree first (dev mode)
    source_relative = Path(__file__).resolve().parent.parent.parent.parent / "migrations"
    if source_relative.is_dir():
        return source_relative
    # Fallback: /app/migrations (Docker)
    docker_path = Path("/app/migrations")
    if docker_path.is_dir():
        return docker_path
    # Last resort: current working directory
    return Path.cwd() / "migrations"


MIGRATIONS_DIR = _find_migrations_dir()


class Database:
    def __init__(self, database_url: str):
        self._url = database_url
        self._pool: asyncpg.Pool | None = None

    async def connect(self, min_size: int = 2, max_size: int = 10) -> None:
        self._pool = await asyncpg.create_pool(self._url, min_size=min_size, max_size=max_size)
        logger.info("Database pool connected")

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("Database pool disconnected")

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database not connected")
        return self._pool

    async def run_migrations(self) -> None:
        sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        async with self.pool.acquire() as conn:
            for sql_file in sql_files:
                sql = sql_file.read_text()
                await conn.execute(sql)
                logger.info("Applied migration: %s", sql_file.name)

    async def check_health(self) -> bool:
        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            logger.exception("Database health check failed")
            return False
