"""Reset system data: drop DB tables, clear Redis, reinitialize.

Usage: python scripts/reset_system.py [--yes]
"""
from __future__ import annotations

import asyncio
import os
import sys

# Ensure the project root is on sys.path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from configs.settings import settings
from configs.logging import get_logger

logger = get_logger(__name__)


async def reset():
    print("=" * 60)
    print("  IMAGE FACTORY - SYSTEM RESET")
    print("=" * 60)
    print()

    if "--yes" not in sys.argv:
        confirm = input("This will DELETE ALL DATA. Are you sure? (yes/no): ")
        if confirm.lower() != "yes":
            print("Aborted.")
            return

    # 1. Drop all database tables
    print("[1/3] Dropping database tables...")
    from database.session import get_engine, Base
    from sqlalchemy import text

    engine = get_engine()
    async with engine.begin() as conn:
        # Import all models so they are registered
        from database.models.job import Job  # noqa
        from database.models.asset import Asset  # noqa
        from database.models.user import User, ApiKey, Project  # noqa
        from database.models.product_link import ProductLink  # noqa
        from database.models.notification import Notification  # noqa
        from database.models.setting import Setting  # noqa

        await conn.run_sync(Base.metadata.drop_all)
        print("   Tables dropped successfully.")

    # 2. Clear Redis
    print("[2/3] Clearing Redis...")
    try:
        import redis.asyncio as aioredis
        r = await aioredis.from_url(settings.redis_url, socket_connect_timeout=5)
        await r.flushall()
        await r.aclose()
        print("   Redis cleared successfully.")
    except Exception as e:
        print(f"   Warning: Could not clear Redis ({e}). Skipping.")

    # 3. Reinitialize database
    print("[3/3] Reinitializing database...")
    from database.session import init_db
    await init_db()
    print("   Database reinitialized successfully.")

    print()
    print("=" * 60)
    print("  RESET COMPLETE. System is ready for fresh start.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(reset())
