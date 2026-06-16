from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse
from pathlib import Path

from bs4 import BeautifulSoup

from configs.logging import get_logger

logger = get_logger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
ALICDN_PATTERN = re.compile(r"https?://[^\"'\s]*alicdn[^\"'\s]*\.(?:jpg|jpeg|png|webp)")


def extract_image_urls(html: str, page_url: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    soup = BeautifulSoup(html, "html.parser")

    alicdn_urls = ALICDN_PATTERN.findall(html)
    for u in alicdn_urls:
        if re.search(r"\.\d+x\d+\.(?:jpg|jpeg|png|webp)", u):
            continue
        if "icon" in u.lower() or "logo" in u.lower():
            continue
        base = re.sub(r"_\d+x\d+\.(?:jpg|jpeg|png|webp)", ".jpg", u)
        if base not in seen:
            seen.add(base)
            urls.append(base)
    if urls:
        return urls

    img_tags = soup.find_all("img")
    for img in img_tags:
        src = img.get("src") or img.get("data-src") or img.get("data-lazyload") or img.get("data-original") or ""
        if not src:
            continue
        full_url = urljoin(page_url, src)
        if full_url in seen:
            continue
        seen.add(full_url)
        ext = Path(urlparse(full_url).path).suffix.lower()
        if ext in IMAGE_EXTENSIONS or any(kw in full_url.lower() for kw in ["product", "img", "photo", "image"]):
            urls.append(full_url)

    for tag in soup.find_all(["a", "link", "meta", "source"]):
        href = tag.get("href") or tag.get("content") or tag.get("srcset", "")
        if href:
            candidates = [u.strip().split(" ")[0] for u in href.split(",") if u.strip()]
            for c in candidates:
                full_url = urljoin(page_url, c)
                if full_url not in seen:
                    seen.add(full_url)
                    ext = Path(urlparse(full_url).path).suffix.lower()
                    if ext in IMAGE_EXTENSIONS:
                        urls.append(full_url)

    if not urls:
        for tag in soup.find_all(["div", "li", "figure", "section"]):
            for img in tag.find_all("img"):
                src = img.get("src") or img.get("data-src") or ""
                if src:
                    full_url = urljoin(page_url, src)
                    if full_url not in seen:
                        seen.add(full_url)
                        urls.append(full_url)

    return urls
