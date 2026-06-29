"""Recovery: dispatch Celery tasks for all pending ProductLinks in a project."""
import asyncio, sys
sys.path.insert(0, '.')
from database import async_session
from database.models.product_link import ProductLink
from sqlalchemy import select

PROJECT_ID = "36a9d83b-3845-4633-938e-c366935bc3a2"

async def recover():
    async with async_session() as s:
        stmt = select(ProductLink).where(
            ProductLink.project_id == PROJECT_ID,
            ProductLink.status == "pending",
        )
        rows = (await s.execute(stmt)).scalars().all()
        print(f"Found {len(rows)} pending products in project {PROJECT_ID}")

        from workers.celery_app import celery_app
        sent = 0
        for p in rows:
            try:
                celery_app.send_task(
                    "tasks.product.process_single_product",
                    args=[p.job_id, p.url, PROJECT_ID],
                )
                sent += 1
            except Exception as e:
                print(f"  FAILED id={p.id}: {e}")
        print(f"Dispatched {sent}/{len(rows)} Celery tasks")

asyncio.run(recover())
