"""
Migration: translate all existing ProductLinks that don't have display_title.

Usage: python scripts/migrate_translations.py
"""
import asyncio, sys
sys.path.insert(0, '.')
from database import async_session
from database.models.product_link import ProductLink
from services.translation_service import detect_language, needs_translation, translate_text

BATCH_SIZE = 10

async def migrate():
    async with async_session() as s:
        stmt = (ProductLink.__table__.select()
                .where(ProductLink.display_title == "")
                .where(ProductLink.product_name != "")
                .limit(BATCH_SIZE))
        rows = (await s.execute(stmt)).fetchall()
        total = len(rows)
        print(f"Found {total} products needing translation")

        for row in rows:
            link_id = row.id
            name = row.product_name or ""
            if not name:
                continue
            source_lang = detect_language(name)
            if needs_translation(name):
                display = await translate_text(name)
            else:
                display = name
            await s.execute(
                ProductLink.__table__.update()
                .where(ProductLink.id == link_id)
                .values(display_title=display, source_title=name, source_language=source_lang)
            )
            print(f"  {link_id[:8]}: '{name[:40]}' -> '{display[:40]}' ({source_lang})")

        await s.commit()
        print(f"Migrated {total} products")

asyncio.run(migrate())
