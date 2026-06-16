from __future__ import annotations

import hashlib
import re
import uuid
from io import BytesIO
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from PIL import Image

from configs.settings import settings
from configs.logging import get_logger

logger = get_logger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
ALI_CDN_PATTERN = re.compile(r"https?://[^\"'\s]*alicdn[^\"'\s]*\.(?:jpg|jpeg|png|webp)")
MAX_IMAGES_PER_PRODUCT = 5
MIN_IMAGE_DIMENSION = 200
MIN_IMAGE_SIZE_BYTES = 10240
SKIP_KEYWORDS = ["icon", "logo", "avatar", "favicon", "spacer", "banner", "thumb", "badge", "sprite", "bg_", "loading"]

SITE_HANDLERS: dict[str, str] = {
    "1688.com": "1688",
}


class ProductScraper:
    def __init__(self):
        self.timeout = settings.extractor_timeout
        self.user_agent = settings.extractor_user_agent

    async def _fetch_page(self, client: httpx.AsyncClient, url: str, domain: str) -> Optional[str]:
        page_url = url
        handler = self._detect_handler(domain)

        if handler == "1688":
            logger.info("scrape_using_1688_handler", url=url)
            try:
                await client.get("https://www.1688.com/", headers={"User-Agent": self.user_agent})
            except Exception as e:
                logger.warning("scrape_1688_prefetch_failed", url=url, error=str(e))
            offer_id = self._extract_offer_id(url)
            if offer_id:
                page_url = f"https://m.1688.com/offer/{offer_id}.html"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                    "Referer": "https://www.1688.com/",
                }
                try:
                    resp = await client.get(page_url, headers=headers)
                    if resp.status_code == 200 and len(resp.text) > 5000:
                        return resp.text
                    logger.warning("scrape_1688_mobile_failed", status=resp.status_code, length=len(resp.text))
                except Exception as e:
                    logger.warning("scrape_1688_mobile_error", url=page_url, error=str(e))

        try:
            resp = await client.get(url, headers={"User-Agent": self.user_agent})
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.warning("scrape_fetch_failed", url=url, error=str(e))
            return None

    def _detect_handler(self, domain: str) -> Optional[str]:
        for site_domain, handler in SITE_HANDLERS.items():
            if site_domain in domain:
                return handler
        return None

    def _extract_offer_id(self, url: str) -> Optional[str]:
        m = re.search(r"/(\d+)\.html", url)
        return m.group(1) if m else None

    async def extract_product_name(self, url: str) -> str:
        """Fetch page and extract product name from <title> or meta tags."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                html = await self._fetch_page(client, url, urlparse(url).netloc.replace("www.", ""))
                if not html:
                    return ""
                soup = BeautifulSoup(html, "html.parser")
                title = soup.find("title")
                if title and title.get_text(strip=True):
                    name = title.get_text(strip=True)
                    name = re.sub(r"\s*[-–|]\s*.*", "", name).strip()
                    if len(name) > 3:
                        return name[:200]
                og_title = soup.find("meta", property="og:title")
                if og_title and og_title.get("content"):
                    return og_title["content"].strip()[:200]
                h1 = soup.find("h1")
                if h1 and h1.get_text(strip=True):
                    return h1.get_text(strip=True)[:200]
                return ""
        except Exception as e:
            logger.debug("extract_product_name_failed", url=url, error=str(e))
            return ""

    async def scrape_product_images(self, url: str, output_dir: str) -> list[dict]:
        downloaded = []
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        content_hashes: set[str] = set()

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                html = await self._fetch_page(client, url, domain)
                if not html:
                    return downloaded

                image_urls = self._extract_image_urls(html, url, domain)
                out_path = Path(output_dir)
                out_path.mkdir(parents=True, exist_ok=True)

                for img_url in image_urls:
                    if len(downloaded) >= MAX_IMAGES_PER_PRODUCT:
                        break

                    if any(kw in img_url.lower() for kw in SKIP_KEYWORDS):
                        continue

                    try:
                        img_resp = await client.get(img_url, headers={"User-Agent": self.user_agent})
                        if img_resp.status_code != 200:
                            continue
                        if len(img_resp.content) < MIN_IMAGE_SIZE_BYTES:
                            logger.debug("scrape_skipped_small_file", url=img_url, size=len(img_resp.content))
                            continue

                        content_hash = hashlib.sha256(img_resp.content[:65536]).hexdigest()
                        if content_hash in content_hashes:
                            logger.debug("scrape_skipped_duplicate_content", url=img_url)
                            continue
                        content_hashes.add(content_hash)

                        try:
                            pil_img = Image.open(BytesIO(img_resp.content))
                            w, h = pil_img.size
                            pil_img.close()
                            if w < MIN_IMAGE_DIMENSION or h < MIN_IMAGE_DIMENSION:
                                logger.debug("scrape_skipped_small_dimensions", url=img_url, dims=f"{w}x{h}")
                                continue
                        except Exception:
                            logger.debug("scrape_skipped_unreadable", url=img_url)
                            continue

                        ext = self._get_extension(img_url, img_resp)
                        filename = f"{uuid.uuid4().hex}{ext}"
                        filepath = out_path / filename
                        with open(filepath, "wb") as f:
                            f.write(img_resp.content)
                        downloaded.append({
                            "filename": filename,
                            "file_path": str(filepath),
                            "original_url": img_url,
                            "file_size": len(img_resp.content),
                            "mime_type": img_resp.headers.get("content-type", "image/jpeg"),
                            "width": w,
                            "height": h,
                        })
                    except Exception as e:
                        logger.debug("scrape_download_failed", url=img_url, error=str(e))
                        continue
        except Exception as e:
            logger.warning("scrape_network_error", url=url, error=str(e))

        logger.info("scrape_complete", url=url, images=len(downloaded))
        return downloaded

    def _extract_image_urls(self, html: str, page_url: str, domain: str) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        soup = BeautifulSoup(html, "html.parser")

        handler = self._detect_handler(domain)
        if handler == "1688":
            all_ali = ALI_CDN_PATTERN.findall(html)
            full_size = []
            for u in all_ali:
                if re.search(r"\.\d+x\d+\.(?:jpg|jpeg|png|webp)", u):
                    continue
                if any(kw in u.lower() for kw in SKIP_KEYWORDS):
                    continue
                base = re.sub(r"_\d+x\d+\.(?:jpg|jpeg|png|webp)", ".jpg", u)
                if base not in seen:
                    seen.add(base)
                    full_size.append(base)
            if full_size:
                return full_size

        img_tags = soup.find_all("img")
        product_candidates = []
        for img in img_tags:
            src = img.get("src") or img.get("data-src") or img.get("data-lazyload") or ""
            if not src:
                continue
            full_url = urljoin(page_url, src)
            if full_url in seen:
                continue
            seen.add(full_url)
            ext = Path(urlparse(full_url).path).suffix.lower()
            if ext not in IMAGE_EXTENSIONS:
                continue
            if any(kw in full_url.lower() for kw in SKIP_KEYWORDS):
                continue

            parent_classes = ""
            parent = img.parent
            for _ in range(3):
                if parent and parent.get("class"):
                    parent_classes += " ".join(parent.get("class")) + " "
                parent = parent.parent if parent else None

            is_product = any(kw in full_url.lower() for kw in ["product", "img", "photo", "image", "main", "zoom", "big"])
            is_product = is_product or any(kw in parent_classes.lower() for kw in ["product", "gallery", "main", "preview", "zoom", "detail", "pic"])
            is_product = is_product or (img.get("alt") and len(img.get("alt")) > 10)

            candidate = (full_url, is_product)
            product_candidates.append(candidate)

        product_candidates.sort(key=lambda x: (not x[1], 0))
        for full_url, _ in product_candidates:
            urls.append(full_url)

        if not urls:
            for tag in soup.find_all(["div", "li", "figure"]):
                for img in tag.find_all("img"):
                    src = img.get("src") or img.get("data-src") or ""
                    if src:
                        full_url = urljoin(page_url, src)
                        if full_url not in seen:
                            seen.add(full_url)
                            urls.append(full_url)

        return urls

    def _get_extension(self, url: str, response: httpx.Response) -> str:
        ext = Path(urlparse(url).path).suffix.lower()
        if ext in IMAGE_EXTENSIONS:
            return ext
        ct = response.headers.get("content-type", "")
        return { "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif", "image/avif": ".avif" }.get(ct, ".jpg")
