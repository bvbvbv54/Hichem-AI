from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup


def extract_page_title(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    title_tag = soup.find("title")
    if title_tag and title_tag.get_text(strip=True):
        return title_tag.get_text(strip=True)
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content", "").strip():
        return og_title["content"].strip()
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    return ""


def extract_page_description(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content", "").strip():
        return meta_desc["content"].strip()
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content", "").strip():
        return og_desc["content"].strip()
    for selector in [
        {"class_": "product-description"},
        {"class_": "productDescription"},
        {"id": "productDescription"},
        {"class_": "description"},
        {"itemprop": "description"},
    ]:
        el = soup.find(**selector)
        if el:
            text = el.get_text(" ", strip=True)
            if text:
                return text
    article = soup.find("article")
    if article:
        text = article.get_text(" ", strip=True)[:2000]
        if text:
            return text
    body = soup.find("body")
    if body:
        text = body.get_text(" ", strip=True)[:500]
        if text:
            return text
    return ""


def extract_image_urls(html: str, page_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    urls: list[str] = []

    for img in soup.find_all("img"):
        for attr in ("src", "data-src", "data-lazyload", "data-original", "data-srcset", "data-a-dynamic-image"):
            val = img.get(attr, "")
            if val:
                if attr == "data-a-dynamic-image" and val.startswith("{"):
                    import json
                    try:
                        for url_key in json.loads(val):
                            absolute = urljoin(page_url, url_key)
                            if absolute not in seen and _looks_like_product_image(absolute):
                                seen.add(absolute)
                                urls.append(absolute)
                    except json.JSONDecodeError:
                        pass
                else:
                    candidates = [v.strip().split(" ")[0] for v in val.split(",") if v.strip()]
                    for c in candidates:
                        absolute = urljoin(page_url, c)
                        if absolute not in seen and _looks_like_product_image(absolute):
                            seen.add(absolute)
                            urls.append(absolute)

    for tag in soup.find_all(["a", "link", "meta", "source"]):
        for attr in ("href", "content", "srcset"):
            val = tag.get(attr, "")
            if val and isinstance(val, str):
                candidates = [v.strip().split(" ")[0] for v in val.split(",") if v.strip()]
                for c in candidates:
                    absolute = urljoin(page_url, c)
                    if absolute not in seen and _looks_like_image(absolute):
                        seen.add(absolute)
                        urls.append(absolute)

    if not urls:
        for container in soup.find_all(["div", "li", "figure", "section"]):
            for img in container.find_all("img"):
                src = img.get("src") or img.get("data-src") or ""
                if src:
                    absolute = urljoin(page_url, src)
                    if absolute not in seen and _looks_like_product_image(absolute):
                        seen.add(absolute)
                        urls.append(absolute)

    return urls


_IMAGE_EXT = re.compile(r"\.(jpe?g|png|webp|gif|avif|bmp)(\?.*)?$", re.I)


def _looks_like_image(url: str) -> bool:
    return bool(_IMAGE_EXT.search(url))


def _looks_like_product_image(url: str) -> bool:
    if not _IMAGE_EXT.search(url):
        return False
    lower = url.lower()
    banned = ("icon", "logo", "avatar", "banner", "spacer", "pixel", "captcha",
              "sprite", "button", "btn_", "thumb_", "favicon", "loading")
    if any(b in lower for b in banned):
        return False
    return True
