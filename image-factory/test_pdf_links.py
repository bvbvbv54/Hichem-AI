"""
Test Script: Run PDF product links through the system
=====================================================
This script reads the product URLs from the PDF and submits them
to the ImageFactory pipeline for processing without generating actual images.

Usage:
    python test_pdf_links.py [--dry-run] [--batch-size 10]

Steps:
1. Read URLs from the PDF
2. Register each URL as a ProductLink in the database
3. Submit to the pipeline (acquisition only, no AI generation)
4. Track status and report results
"""

import asyncio
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Add the image-factory directory to the path
sys.path.insert(0, str(Path(__file__).parent / "image-factory"))

from configs.settings import settings
from configs.logging import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)


def extract_urls_from_pdf(pdf_path: str) -> list[dict]:
    """Extract product URLs from the PDF file."""
    try:
        import pdfplumber
    except ImportError:
        logger.error("pdfplumber not installed. Run: pip install pdfplumber")
        return []

    urls = []
    seen = set()
    notes_map = {}

    try:
        with pdfplumber.open(pdf_path) as pdf:
            raw_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    raw_text += text + "\n"

            lines = raw_text.split("\n")
            current_note = ""
            for line in lines:
                line = line.strip()
                if not line:
                    current_note = ""
                    continue

                stripped = line.lower()
                if any(stripped.startswith(w) for w in ["yes", "check", "desk fan", "quest 3"]):
                    current_note = line.split("https")[0].strip() if "https" in line else line
                    url_part = line.split("https")[-1] if "https" in line else ""
                    if url_part:
                        line = "https" + url_part
                    else:
                        continue

                if line.startswith("http"):
                    clean_url = line.split("?")[0] if "1688.com" in line else line
                    if clean_url not in seen:
                        seen.add(clean_url)
                        category = "1688" if "1688.com" in clean_url else "Amazon" if "amazon.com" in clean_url else "TikTok" if "tiktok.com" in clean_url else "Other"
                        urls.append({
                            "url": clean_url,
                            "category": category,
                            "notes": current_note,
                            "priority": 1 if current_note else 0,
                        })
                        current_note = ""

        logger.info(f"Extracted {len(urls)} unique URLs from PDF")
        return urls

    except Exception as e:
        logger.error(f"Failed to extract URLs from PDF: {e}")
        return []


async def register_product_links(urls: list[dict], dry_run: bool = False) -> list[dict]:
    """Register URLs as ProductLink entries in the database."""
    from database.session import async_session
    from database.models.product_link import ProductLink
    from sqlalchemy import select

    registered = []
    async with async_session() as session:
        for entry in urls:
            url = entry["url"]
            url_hash = hashlib.sha256(url.encode()).hexdigest()

            existing = await session.execute(
                select(ProductLink).where(ProductLink.url_hash == url_hash)
            )
            if existing.scalar_one_or_none():
                logger.info(f"Already registered (skipping): {url[:80]}...")
                registered.append({"url": url, "status": "already_exists"})
                continue

            if dry_run:
                registered.append({"url": url, "status": "would_register"})
                continue

            link = ProductLink(
                url=url,
                url_hash=url_hash,
                project_id="pdf_test_batch",
                batch_id=f"pdf_test_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                status="pending",
                category=entry.get("category", ""),
                notes=entry.get("notes", ""),
                priority=entry.get("priority", 0),
            )
            session.add(link)
            registered.append({"url": url, "status": "registered"})
            logger.info(f"Registered: {url[:80]}...")

        if not dry_run:
            await session.commit()

    return registered


async def run_pipeline_test(pdf_path: str, dry_run: bool = False, batch_size: int = 10):
    """Run the full test pipeline on PDF URLs."""
    logger.info("=" * 60)
    logger.info("PDF Links Pipeline Test")
    logger.info(f"PDF: {pdf_path}")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    logger.info(f"Batch size: {batch_size}")
    logger.info("=" * 60)

    urls = extract_urls_from_pdf(pdf_path)
    if not urls:
        logger.error("No URLs extracted. Aborting.")
        return

    logger.info(f"\nExtracted {len(urls)} URLs:")
    for i, entry in enumerate(urls):
        note = f" [{entry['notes']}]" if entry.get("notes") else ""
        logger.info(f"  {i+1}. [{entry['category']}] {entry['url'][:80]}...{note}")

    logger.info(f"\nRegistering product links in database...")
    registered = await register_product_links(urls, dry_run)

    registered_count = sum(1 for r in registered if r["status"] == "registered")
    skipped_count = sum(1 for r in registered if r["status"] == "already_exists")
    logger.info(f"Registered: {registered_count} new, {skipped_count} already exist")

    if dry_run:
        logger.info("\n=== DRY RUN COMPLETE ===")
        logger.info("No database changes were made.")
        logger.info("Run without --dry-run to actually register and process.")
        return

    logger.info("\n=== REGISTRATION COMPLETE ===")
    logger.info(f"Total URLs: {len(urls)}")
    logger.info(f"Newly registered: {registered_count}")
    logger.info(f"Already existed: {skipped_count}")

    # Group by category
    categories = {}
    for entry in urls:
        cat = entry.get("category", "Other")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(entry)

    logger.info("\n=== URLs BY CATEGORY ===")
    for cat, items in categories.items():
        logger.info(f"  {cat}: {len(items)} URLs")
        for item in items[:3]:
            logger.info(f"    - {item['url'][:80]}...")
        if len(items) > 3:
            logger.info(f"    ... and {len(items)-3} more")

    logger.info("\n=== PDF LINKS TEST COMPLETE ===")
    logger.info("URLs are now registered in the database as ProductLink entries.")
    logger.info("Access them via the Content tab in the dashboard at /content")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Test PDF product links through ImageFactory pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Dry run - no database changes")
    parser.add_argument("--batch-size", type=int, default=10, help="Number of URLs to process at once")
    args = parser.parse_args()

    pdf_path = str(Path(__file__).parent / "products to look at  - Sheet1.pdf")

    if not Path(pdf_path).exists():
        logger.error(f"PDF file not found: {pdf_path}")
        sys.exit(1)

    asyncio.run(run_pipeline_test(pdf_path, dry_run=args.dry_run, batch_size=args.batch_size))


if __name__ == "__main__":
    main()
