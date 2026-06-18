from __future__ import annotations

import json
import re
from typing import Any
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
                    try:
                        parsed = json.loads(val)
                        entries = []
                        for url_key, dims in parsed.items():
                            absolute = urljoin(page_url, url_key)
                            if absolute not in seen and _looks_like_product_image(absolute):
                                w, h = dims if isinstance(dims, (list, tuple)) and len(dims) == 2 else (0, 0)
                                entries.append((w * h, absolute))
                        entries.sort(key=lambda x: x[0], reverse=True)
                        for _, absolute in entries[:3]:
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

    if not urls:
        ali_urls = _ALI_CDN_PATTERN.findall(html)
        for u in ali_urls:
            if re.search(r"\.\d+x\d+\.(?:jpg|jpeg|png|webp)", u):
                continue
            if u not in seen:
                seen.add(u)
                urls.append(u)

    if len(urls) > 1:
        def _img_quality(url: str) -> int:
            lower = url.lower()
            score = 0
            if "sl" in lower:
                m = re.search(r"sl(\d+)", lower)
                if m:
                    score = int(m.group(1))
            if "ux" in lower:
                m = re.search(r"ux(\d+)", lower)
                if m:
                    score = max(score, int(m.group(1)))
            if "sy" in lower:
                m = re.search(r"sy(\d+)", lower)
                if m:
                    score = max(score, int(m.group(1)))
            if "sx" in lower:
                m = re.search(r"sx(\d+)", lower)
                if m:
                    score = max(score, int(m.group(1)))
            return score
        urls.sort(key=_img_quality, reverse=True)

    if not urls:
        json_ld_urls = _extract_json_ld_images(soup)
        for u in json_ld_urls:
            if u not in seen:
                seen.add(u)
                urls.append(u)

    if not urls:
        script_urls = _extract_script_data_images(html, page_url)
        for u in script_urls:
            if u not in seen:
                seen.add(u)
                urls.append(u)

    if not urls:
        cdn_urls = _extract_cdn_urls(html, page_url, seen)
        for u in cdn_urls:
            if u not in seen:
                seen.add(u)
                urls.append(u)

    if not urls:
        imgs_urls = _extract_data_imgs(soup, page_url, seen)
        for u in imgs_urls:
            if u not in seen:
                seen.add(u)
                urls.append(u)

    if not urls:
        extra_attrs = _extract_extra_attrs(soup, page_url, seen)
        for u in extra_attrs:
            if u not in seen:
                seen.add(u)
                urls.append(u)

    if not urls:
        bg_urls = _extract_background_images(soup, page_url, seen)
        for u in bg_urls:
            if u not in seen:
                seen.add(u)
                urls.append(u)

    if not urls:
        proto_urls = _extract_protocol_relative(html, page_url, seen)
        for u in proto_urls:
            if u not in seen:
                seen.add(u)
                urls.append(u)

    if len(urls) > 1:
        def _img_quality(url: str) -> int:
            lower = url.lower()
            score = 0
            if "sl" in lower:
                m = re.search(r"sl(\d+)", lower)
                if m:
                    score = int(m.group(1))
            if "ux" in lower:
                m = re.search(r"ux(\d+)", lower)
                if m:
                    score = max(score, int(m.group(1)))
            if "sy" in lower:
                m = re.search(r"sy(\d+)", lower)
                if m:
                    score = max(score, int(m.group(1)))
            if "sx" in lower:
                m = re.search(r"sx(\d+)", lower)
                if m:
                    score = max(score, int(m.group(1)))
            return score
        urls.sort(key=_img_quality, reverse=True)

    return urls


_IMAGE_EXT = re.compile(r"\.(jpe?g|png|webp|gif|avif|bmp)(\?.*)?$", re.I)
_ALI_CDN_PATTERN = re.compile(r"https?://[^\"'\s]*alicdn[^\"'\s]*\.(?:jpg|jpeg|png|webp)")
_CDN_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"https?://[^\"'\s]*alicdn[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "alicdn"),
    (re.compile(r"https?://[^\"'\s]*dhresource[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "dhresource"),
    (re.compile(r"https?://[^\"'\s]*(?:aimg|img|commimg)\.kwcdn[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "kwcdn"),
    (re.compile(r"https?://[^\"'\s]*made-in-china[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "made-in-china"),
    (re.compile(r"https?://[^\"'\s]*cbu0[0-9][^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "cbu"),
    (re.compile(r"https?://[^\"'\s]*(?:ae0[0-9]|ae01)[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "aliexpress"),
    (re.compile(r"https?://[^\"'\s]*image\.made-in-china[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "made-in-china-img"),
    (re.compile(r"https?://[^\"'\s]*(?:sc0[0-9]|sc0[0-9])\.alicdn[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "alicdn-sc"),
    (re.compile(r"https?://[^\"'\s]*m\.media-amazon[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "amazon"),
    (re.compile(r"https?://[^\"'\s]*img[0-9]?\.(?:jd|360buyimg)[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "jd"),
    (re.compile(r"https?://[^\"'\s]*taobao[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "taobao"),
    (re.compile(r"https?://[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)[^\"'\s]*(?:\?[^\"'\s]*)?", re.I), "generic"),
]


def _extract_json_ld_images(soup: BeautifulSoup) -> list[str]:
    results: list[str] = []
    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
            for container in [data] if isinstance(data, dict) else data:
                image_data = container.get("image") if isinstance(container, dict) else None
                if isinstance(image_data, str):
                    results.append(image_data)
                elif isinstance(image_data, list):
                    for item in image_data:
                        if isinstance(item, str):
                            results.append(item)
        except (json.JSONDecodeError, AttributeError):
            continue
    return results


def _extract_script_data_images(html: str, page_url: str) -> list[str]:
    results: list[str] = []
    patterns = [
        r'window\.productData\s*=\s*({.*?});',
        r'window\.initialState\s*=\s*({.*?});',
        r'window\.__NUXT__\s*=\s*({.*?});',
        r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
        r'dataLayer\.push\(({.*?})\);',
        r'var\s+galleryData\s*=\s*({.*?});',
        r'var\s+imgData\s*=\s*({.*?});',
    ]
    for pat in patterns:
        for m in re.finditer(pat, html, re.DOTALL):
            try:
                data = json.loads(m.group(1))
                _extract_urls_from_json(data, results, page_url)
                if results:
                    return results
            except (json.JSONDecodeError, Exception):
                continue
    return results


def _extract_urls_from_json(data: Any, results: list[str], page_url: str) -> None:
    if isinstance(data, str):
        abs_url = _urljoin_without_fragment(page_url, data)
        if _IMAGE_EXT.search(abs_url) and abs_url not in results:
            results.append(abs_url)
    elif isinstance(data, dict):
        for key in ("image", "images", "img", "src", "url", "file", "thumb", "thumbnail",
                    "original", "zoom", "big", "large", "gallery", "list", "pic", "pics",
                    "productImage", "product_image", "imageUrl", "imgUrl", "image_url"):
            val = data.get(key)
            if val:
                if isinstance(val, str):
                    abs_url = _urljoin_without_fragment(page_url, val)
                    if _IMAGE_EXT.search(abs_url) and abs_url not in results:
                        results.append(abs_url)
                elif isinstance(val, list):
                    for item in val:
                        _extract_urls_from_json(item, results, page_url)
                elif isinstance(val, dict):
                    _extract_urls_from_json(val, results, page_url)
        for key, val in data.items():
            if isinstance(val, (dict, list)):
                _extract_urls_from_json(val, results, page_url)
    elif isinstance(data, list):
        for item in data:
            _extract_urls_from_json(item, results, page_url)


def _urljoin_without_fragment(base: str, url: str) -> str:
    from urllib.parse import urljoin
    url = url.split("#")[0]
    return urljoin(base, url)


def _extract_cdn_urls(html: str, page_url: str, seen: set[str]) -> list[str]:
    results: list[str] = []
    for pattern, name in _CDN_PATTERNS:
        for m in pattern.finditer(html):
            url = m.group(0)
            if not _looks_like_product_image(url):
                continue
            if url not in seen and url not in results:
                results.append(url)
                if len(results) >= 10:
                    return results
    return results


def _extract_data_imgs(soup: BeautifulSoup, page_url: str, seen: set[str]) -> list[str]:
    results: list[str] = []
    for tag in soup.find_all(["img", "a", "div", "li", "span"], attrs={"data-imgs": True}):
        raw = tag.get("data-imgs", "")
        if not raw or not raw.strip().startswith("["):
            continue
        try:
            items = json.loads(raw)
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        for key in ("imgSrc", "src", "url", "image"):
                            val = item.get(key)
                            if val and isinstance(val, str):
                                absolute = _urljoin_without_fragment(page_url, val)
                                if absolute not in seen and _looks_like_product_image(absolute):
                                    seen.add(absolute)
                                    results.append(absolute)
                    elif isinstance(item, str):
                        absolute = _urljoin_without_fragment(page_url, item)
                        if absolute not in seen and _looks_like_product_image(absolute):
                            seen.add(absolute)
                            results.append(absolute)
                    if len(results) >= 10:
                        return results
        except (json.JSONDecodeError, Exception):
            pass
    return results


def _extract_extra_attrs(soup: BeautifulSoup, page_url: str, seen: set[str]) -> list[str]:
    results: list[str] = []
    extra_attrs = [
        "data-zoom-image", "data-large-image", "data-zoom", "data-img",
        "data-original", "data-src", "data-lazy", "data-echo",
        "data-ks-img", "data-img-url", "data-imgs", "data-image",
        "data-href", "data-url",
    ]
    for tag in soup.find_all(["img", "a", "div", "span", "figure", "li"]):
        for attr in extra_attrs:
            val = tag.get(attr, "")
            if val and isinstance(val, str):
                for candidate in val.split(","):
                    candidate = candidate.strip().split(" ")[0]
                    if candidate:
                        absolute = _urljoin_without_fragment(page_url, candidate)
                        if absolute not in seen and _looks_like_product_image(absolute):
                            seen.add(absolute)
                            results.append(absolute)
                            if len(results) >= 10:
                                return results
    return results


def _extract_background_images(soup: BeautifulSoup, page_url: str, seen: set[str]) -> list[str]:
    results: list[str] = []
    bg_re = re.compile(r"background(?:-image)?\s*:\s*url\(['\"]?(.*?)['\"]?\)", re.I)
    for el in soup.find_all(style=True):
        style = el.get("style", "")
        for m in bg_re.finditer(style):
            url = m.group(1).strip().strip("\"'")
            if url:
                absolute = _urljoin_without_fragment(page_url, url)
                if absolute not in seen and _looks_like_product_image(absolute):
                    seen.add(absolute)
                    results.append(absolute)
                    if len(results) >= 10:
                        return results
    return results


def _extract_protocol_relative(html: str, page_url: str, seen: set[str]) -> list[str]:
    results: list[str] = []
    from urllib.parse import urlparse
    scheme = urlparse(page_url).scheme or "https"
    proto_re = re.compile(r'src\s*=\s*["\']//([^"\']*\.(?:jpg|jpeg|png|webp)[^"\']*)["\']', re.I)
    for m in proto_re.finditer(html):
        url = f"{scheme}://{m.group(1)}"
        if url not in seen and _looks_like_product_image(url):
            seen.add(url)
            results.append(url)
            if len(results) >= 10:
                return results
    return results


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
