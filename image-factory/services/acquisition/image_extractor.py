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
        urls.sort(key=_img_quality, reverse=True)

    return urls


_IMAGE_EXT = re.compile(r"\.(jpe?g|png|webp|gif|avif|bmp)(\?.*)?$", re.I)
_ALI_CDN_PATTERN = re.compile(r"https?://[^\"'\s]*alicdn[^\"'\s]*\.(?:jpg|jpeg|png|webp)")
_CDN_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"https?://[^\"'\s]*alicdn[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "alicdn"),
    (re.compile(r"https?://[^\"'\s]*dhresource[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "dhresource"),
    (re.compile(r"https?://[^\"'\s]*(?:aimg|img|commimg)\.kwcdn[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "kwcdn"),
    (re.compile(r"https?://[^\"'\s]*kwcdn[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "kwcdn2"),
    (re.compile(r"https?://[^\"'\s]*(?:made-in-china|image\.made|micstatic)[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "made-in-china"),
    (re.compile(r"https?://[^\"'\s]*cbu0[0-9][^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "cbu"),
    (re.compile(r"https?://[^\"'\s]*(?:ae0[0-9]|ae01)[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "aliexpress"),
    (re.compile(r"https?://[^\"'\s]*image\.made-in-china[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "made-in-china-img"),
    (re.compile(r"https?://[^\"'\s]*(?:sc0[0-9]|sc0[0-9])\.alicdn[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "alicdn-sc"),
    (re.compile(r"https?://[^\"'\s]*m\.media-amazon[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "amazon"),
    (re.compile(r"https?://[^\"'\s]*img[0-9]?\.(?:jd|360buyimg)[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "jd"),
    (re.compile(r"https?://[^\"'\s]*taobao[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "taobao"),
    (re.compile(r"https?://[^\"'\s]*ae-pic-a1[^\"'\s]*\.(?:jpg|jpeg|png|webp|avif|gif)(?:\?[^\"'\s]*)?", re.I), "ae-pic"),
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
        r'window\.runParams\s*=\s*({.*?});',
        r'window\.g_config\s*=\s*({.*?});',
        r'window\._dsc_g_config\s*=\s*({.*?});',
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


_AMAZON_IMG_ID = re.compile(r"/images/I/([A-Za-z0-9._-]+)")


def _add_amazon_image(url: str, seen_ids: set[str], urls: list[str]) -> None:
    abs_url = url.split("?")[0].split("#")[0]
    id_m = _AMAZON_IMG_ID.search(abs_url)
    if id_m:
        img_id = id_m.group(1).split(".")[0]
        if img_id not in seen_ids:
            seen_ids.add(img_id)
            full = f"https://m.media-amazon.com/images/I/{img_id}.jpg"
            urls.append(full)
    elif abs_url not in urls:
        urls.append(abs_url)


def _extract_amazon_color_images_from_script(html: str) -> list[str]:
    seen_ids: set[str] = set()
    urls: list[str] = []

    pattern = re.compile(r'"hiRes"\s*:\s*"((?:https?:)?//m\.media-amazon\.com/images/I/[^"]+)"', re.I)
    for m in pattern.finditer(html):
        url = m.group(1)
        if not url.startswith("http"):
            url = "https:" + url
        id_m = _AMAZON_IMG_ID.search(url)
        if id_m:
            img_id = id_m.group(1).split(".")[0]
            if img_id not in seen_ids:
                seen_ids.add(img_id)
                urls.append(url)

    if urls:
        return urls

    return _extract_amazon_images_fallback(html)


def _extract_amazon_images_fallback(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    seen_ids: set[str] = set()
    urls: list[str] = []

    for img in soup.find_all("img", attrs={"data-a-dynamic-image": True}):
        val = img.get("data-a-dynamic-image", "")
        if val.startswith("{"):
            try:
                parsed = json.loads(val)
                for url_key in parsed:
                    _add_amazon_image(url_key, seen_ids, urls)
            except json.JSONDecodeError:
                pass

    landing = soup.select_one("#landingImage")
    if landing:
        for attr in ("src", "data-old-hires", "data-a-dynamic-image"):
            val = landing.get(attr, "")
            if val and isinstance(val, str) and val.startswith("http"):
                _add_amazon_image(val, seen_ids, urls)

    for thumb in soup.select("#altImages img, #imageBlockThumbnails img, [data-a-image-name^='thumb'] img"):
        src = thumb.get("src", "")
        if src:
            _add_amazon_image(src, seen_ids, urls)

    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src and "media-amazon" in src:
            _add_amazon_image(src, seen_ids, urls)

    return urls[:10]


def extract_amazon_images(html: str) -> list[str]:
    return _extract_amazon_color_images_from_script(html)


_1688_GALLERY_SELECTORS = [
    ".detail-gallery img",
    ".product-gallery img",
    ".tb-thumb img",
    "#detail-pic img",
    ".tb-gallery img",
    ".detail-pic-wrap img",
    "[data-widget-type='PicGallery'] img",
    ".module-od-picture-gallery img",
    ".od-gallery-preview img",
    "ul.od-gallery-list img",
    "[class*='preview-img'] img",
]

_1688_REJECT_PATTERNS = [
    re.compile(r"/tfs/", re.I),
    re.compile(r"/tps/", re.I),
    re.compile(r"-tps-\d+", re.I),
    re.compile(r"gw\.alicdn\.com", re.I),
    re.compile(r"//img\.alicdn\.com/tfs/"),
    re.compile(r"//img\.alicdn\.com/tps/"),
    re.compile(r"//img\.alicdn\.com/imgextra/.*?-tps-"),
    re.compile(r"\.slim\.(?:jpg|png|webp)"),
    re.compile(r"captcha", re.I),
    re.compile(r"/cms/upload/"),
]


def _extract_json_var(html: str, var_name: str) -> dict | None:
    patterns = [
        rf"window\.{re.escape(var_name)}\s*=\s*",
        rf"var\s+{re.escape(var_name)}\s*=\s*",
        rf"const\s+{re.escape(var_name)}\s*=\s*",
        rf"let\s+{re.escape(var_name)}\s*=\s*",
    ]
    for pat in patterns:
        for m in re.finditer(pat, html):
            start = m.end()
            if start >= len(html):
                continue
            while start < len(html) and html[start] in " \t\n\r":
                start += 1
            if start >= len(html) or html[start] != "{":
                continue
            depth = 0
            in_string = False
            escape = False
            json_end = start
            for i in range(start, len(html)):
                ch = html[i]
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if not in_string:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            json_end = i + 1
                            break
            if depth == 0:
                json_str = html[start:json_end]
                try:
                    return json.loads(json_str)
                except (json.JSONDecodeError, Exception):
                    continue
    return None


def _deep_get(obj: dict | list, path: str, default=None):
    parts = path.split(".")
    current = obj
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            current = current[idx] if idx < len(current) else None
        else:
            return default
        if current is None:
            return default
    return current


def _is_1688_product_image(url: str) -> bool:
    if not _looks_like_product_image(url):
        return False
    lower = url.lower()
    for pat in _1688_REJECT_PATTERNS:
        if pat.search(lower):
            return False
    return True


def _extract_1688_gallery(html: str, page_url: str) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []

    # Method 1: Embedded JSON (window.offerView.imageList)
    offer_view = _extract_json_var(html, "offerView")
    if offer_view:
        image_list = _deep_get(offer_view, "imageList", [])
        if isinstance(image_list, list):
            for item in image_list:
                if isinstance(item, str):
                    abs_url = urljoin(page_url, item)
                    if _is_1688_product_image(abs_url) and abs_url not in seen:
                        seen.add(abs_url)
                        urls.append(abs_url)
                elif isinstance(item, dict):
                    for key in ("url", "src", "original", "fullSizeImageUrl"):
                        val = item.get(key, "")
                        if val:
                            abs_url = urljoin(page_url, val)
                            if _is_1688_product_image(abs_url) and abs_url not in seen:
                                seen.add(abs_url)
                                urls.append(abs_url)

    if urls:
        return urls

    # Method 1b: Inline JSON arrays (offerImgList, mainImage) found in IIFE or script data
    for key in ("offerImgList", "mainImage"):
        m = re.search(rf'"{key}"\s*:\s*(\[.+?\])', html, re.DOTALL)
        if m:
            try:
                items = json.loads(m.group(1))
                for item in items if isinstance(items, list) else [items]:
                    if isinstance(item, str):
                        abs_url = urljoin(page_url, item)
                        if _is_1688_product_image(abs_url) and abs_url not in seen:
                            seen.add(abs_url)
                            urls.append(abs_url)
            except (json.JSONDecodeError, Exception):
                pass

    if urls:
        return urls

    # Method 2: DOM gallery container selectors
    soup = BeautifulSoup(html, "lxml") if not urls else None
    if soup:
        for selector in _1688_GALLERY_SELECTORS:
            for el in soup.select(selector):
                src = el.get("src") or el.get("data-src") or el.get("data-lazyload") or ""
                if src:
                    abs_url = urljoin(page_url, src)
                    if _is_1688_product_image(abs_url) and abs_url not in seen:
                        seen.add(abs_url)
                        urls.append(abs_url)
                data_imgs = el.get("data-imgs", "")
                if data_imgs and data_imgs.strip().startswith("["):
                    try:
                        items = json.loads(data_imgs)
                        for item in items if isinstance(items, list) else [items]:
                            if isinstance(item, dict):
                                for key in ("imgSrc", "src", "url", "image"):
                                    val = item.get(key, "")
                                    if val:
                                        abs_url = urljoin(page_url, val)
                                        if _is_1688_product_image(abs_url) and abs_url not in seen:
                                            seen.add(abs_url)
                                            urls.append(abs_url)
                    except (json.JSONDecodeError, Exception):
                        pass

        if urls:
            return urls

        # Method 3: Any img.alicdn.com URL that looks like a product image (scoped but no known gallery container found)
        for img in soup.find_all("img"):
            for attr in ("src", "data-src", "data-lazyload", "data-original"):
                val = img.get(attr, "")
                if val and "alicdn" in val.lower():
                    abs_url = urljoin(page_url, val)
                    if _is_1688_product_image(abs_url) and abs_url not in seen:
                        seen.add(abs_url)
                        urls.append(abs_url)

    if urls:
        return urls

    # Method 4: Raw-HTML regex fallback for alicdn URLs (catches images embedded in JS/JSON/IIFE)
    for m in re.finditer(r'https?://[^"\'\\s>]*alicdn[^"\'\\s>]*\.(?:jpg|jpeg|png|webp)', html, re.I):
        abs_url = m.group(0)
        if _is_1688_product_image(abs_url) and abs_url not in seen:
            seen.add(abs_url)
            urls.append(abs_url)

    return urls


_ALIBABA_GALLERY_SELECTORS = [
    ".product-gallery img",
    ".image-gallery img",
    ".detail-gallery img",
    ".gallery-container img",
    ".image-viewer img",
    ".magnifier img",
    "[data-component-type='product-gallery'] img",
    ".gallery-wrap img",
    ".detail-content .gallery img",
    ".detail-gallery-magnifier img",
]

_ALIBABA_JSON_VARS = ["pageData", "product", "detailData"]


def _looks_like_alibaba_image(url: str) -> bool:
    if not _looks_like_product_image(url):
        return False
    lower = url.lower()
    for pat in _1688_REJECT_PATTERNS:
        if pat.search(lower):
            return False
    return True


def _extract_alibaba_gallery(html: str, page_url: str) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []

    # Method 1: Embedded JSON (pageData.images, product.images)
    for var_name in _ALIBABA_JSON_VARS:
        data = _extract_json_var(html, var_name)
        if data:
            for path in ("images", "imageList", "gallery", "imageUrl"):
                imgs = _deep_get(data, path, [])
                if isinstance(imgs, list):
                    for item in imgs:
                        if isinstance(item, str):
                            abs_url = urljoin(page_url, item)
                            if _looks_like_alibaba_image(abs_url) and abs_url not in seen:
                                seen.add(abs_url)
                                urls.append(abs_url)
                        elif isinstance(item, dict):
                            for key in ("url", "src", "original", "fullSizeImageUrl", "imageUrl", "imgUrl"):
                                val = item.get(key, "")
                                if val:
                                    abs_url = urljoin(page_url, val)
                                    if _looks_like_alibaba_image(abs_url) and abs_url not in seen:
                                        seen.add(abs_url)
                                        urls.append(abs_url)

    if urls:
        return urls

    # Method 1b: JSON-LD structured data (Product.image)
    soup = BeautifulSoup(html, "lxml")
    json_ld_urls = _extract_json_ld_images(soup)
    for u in json_ld_urls:
        abs_url = urljoin(page_url, u)
        if _looks_like_alibaba_image(abs_url) and abs_url not in seen:
            seen.add(abs_url)
            urls.append(abs_url)

    if urls:
        return urls

    # Method 2: DOM gallery container selectors
    for selector in _ALIBABA_GALLERY_SELECTORS:
        for el in soup.select(selector):
            src = el.get("src") or el.get("data-src") or el.get("data-lazyload") or el.get("data-original") or ""
            if src:
                abs_url = urljoin(page_url, src)
                if _looks_like_alibaba_image(abs_url) and abs_url not in seen:
                    seen.add(abs_url)
                    urls.append(abs_url)
            data_imgs = el.get("data-imgs", "")
            if data_imgs and data_imgs.strip().startswith("["):
                try:
                    items = json.loads(data_imgs)
                    for item in items if isinstance(items, list) else [items]:
                        if isinstance(item, dict):
                            for key in ("imgSrc", "src", "url", "image"):
                                val = item.get(key, "")
                                if val:
                                    abs_url = urljoin(page_url, val)
                                    if _looks_like_alibaba_image(abs_url) and abs_url not in seen:
                                        seen.add(abs_url)
                                        urls.append(abs_url)
                except (json.JSONDecodeError, Exception):
                    pass

    if urls:
        return urls

    # Method 3: Any img inside a gallery-like container (broader match)
    gallery_containers = [
        ".product-gallery", ".image-gallery", ".detail-gallery",
        ".gallery-container", ".image-viewer", ".magnifier",
        "[data-component-type='product-gallery']",
    ]
    for container_sel in gallery_containers:
        for container in soup.select(container_sel):
            for img in container.find_all("img"):
                src = img.get("src") or img.get("data-src") or ""
                if src:
                    abs_url = urljoin(page_url, src)
                    if _looks_like_alibaba_image(abs_url) and abs_url not in seen:
                        seen.add(abs_url)
                        urls.append(abs_url)

    if urls:
        return urls

    # Method 4: Raw-HTML regex fallback for alicdn / sc04.alicdn.com URLs
    for m in re.finditer(r'https?://[^"\'\\s>]*(?:sc0[0-9]\.alicdn|alicdn)[^"\'\\s>]*\.(?:jpg|jpeg|png|webp)', html, re.I):
        abs_url = m.group(0)
        if _looks_like_alibaba_image(abs_url) and abs_url not in seen:
            seen.add(abs_url)
            urls.append(abs_url)

    return urls


def validate_product_page(url: str, html: str) -> tuple[bool, str]:
    from urllib.parse import urlparse
    soup = BeautifulSoup(html, "lxml")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    h1_tag = soup.find("h1")
    h1 = h1_tag.get_text(strip=True) if h1_tag else ""

    # Check for captcha
    title_lower = title.lower()
    if any(kw in title_lower for kw in ["captcha", "just a moment", "please wait", "attention required",
                                         "verify", "access denied", "blocked", "security check"]):
        return False, f"Blocked by captcha/security page: {title}"

    # Check for empty/meaningless H1
    if not h1 or len(h1) < 5:
        return False, f"No meaningful product title found (H1='{h1[:50]}')"

    # Extract numeric product ID from URL (e.g. "60607930952" from "..._60607930952.html")
    import re as _re
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]
    product_id = None
    for part in path_parts:
        id_match = _re.search(r"_(\d{5,})", part)
        if id_match:
            product_id = id_match.group(1)
            break
    if product_id and product_id not in html:
        return False, f"Product ID '{product_id}' not found in page content"

    return True, ""


def _upgrade_dhgate_url(url: str) -> str:
    """Upgrade a DHgate thumbnail URL to full resolution by swapping size token to 0x0."""
    # Handle protocol-relative URLs
    if url.startswith("//"):
        url = "https:" + url
    # Swap /m/SIZExSIZE/ to /m/0x0/ for full resolution
    upgraded = re.sub(r"/m/\d+x\d+/", "/m/0x0/", url)
    return upgraded


def _extract_dhgate_gallery(html: str, page_url: str) -> list[str]:
    """Extract product images from DHgate, scoped to gallery container only.

    DHgate uses Next.js with CSS-module class names (randomized per build), so
    we rely on stable attributes:
      - `ul[spm-c="imagelist"]` — the thumbnail gallery strip
      - `id="masterImg"` — the main large display image

    All gallery thumbnails share the same product-description alt text.  URL size
    tokens (`/m/100x100/`) are upgraded to `/m/0x0/` for full resolution.

    Color swatches (`img[preview="false"]`, `alt` starting with `#`) and
    recommended/related-product images (different URL paths or alt text) are
    excluded by attribute checks, not size.
    """
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    gallery_urls: set[str] = set()

    def is_color_swatch(img) -> bool:
        alt = (img.get("alt") or "")
        return img.get("preview") == "false" or alt.startswith("#")

    def is_contaminated(img) -> bool:
        """Check if image is NOT a product gallery image."""
        alt = (img.get("alt") or "").strip()
        src = (img.get("src") or "").strip()
        # Empty alt or data: placeholders
        if not alt or not src or src.startswith("data:"):
            return True
        # Color swatches
        if is_color_swatch(img):
            return True
        # Recommended products have very different alt text (other products)
        # Gallery images all share a long descriptive product alt
        return False

    def extract_src(img) -> str:
        src = img.get("src") or img.get("data-src") or ""
        if src.startswith("//"):
            src = "https:" + src
        return src

    def get_product_alt_text() -> str:
        """Find the common alt text from gallery thumbnails."""
        ul = soup.select_one('ul[spm-c="imagelist"]')
        if ul:
            for li in ul.find_all("li"):
                img = li.find("img")
                if img and img.get("alt"):
                    alt = img.get("alt", "").strip()
                    if alt and not alt.startswith("#"):
                        return alt
        # Fallback: look for the page title
        title = soup.find("title")
        if title:
            return title.get_text(strip=True)
        return ""

    # Strategy 1: primary — ul[spm-c="imagelist"] (stable Next.js attribute)
    ul = soup.select_one('ul[spm-c="imagelist"]')
    if ul:
        for li in ul.find_all("li"):
            img = li.find("img")
            if img and not is_contaminated(img):
                src = extract_src(img)
                if src and "dhresource" in src:
                    upgraded = _upgrade_dhgate_url(src)
                    if upgraded not in seen:
                        seen.add(upgraded)
                        gallery_urls.add(upgraded)

    # Strategy 2: masterImg (if not already found via gallery)
    if not gallery_urls:
        master = soup.select_one("#masterImg")
        if master:
            src = extract_src(master)
            if src and "dhresource" in src and src not in seen:
                upgraded = _upgrade_dhgate_url(src)
                seen.add(upgraded)
                gallery_urls.add(upgraded)

    # Strategy 3: alt-text-based fallback (for pages with different DOM structure)
    if not gallery_urls:
        product_alt = get_product_alt_text()
        if product_alt:
            for img in soup.find_all("img"):
                if is_contaminated(img):
                    continue
                src = extract_src(img)
                if not src or "dhresource" not in src:
                    continue
                alt = (img.get("alt") or "").strip()
                # Gallery thumbnails share a long common prefix of the product alt
                if alt and (alt == product_alt or product_alt.startswith(alt[:30]) or alt.startswith(product_alt[:30])):
                    if src not in seen:
                        upgraded = _upgrade_dhgate_url(src)
                        seen.add(upgraded)
                        gallery_urls.add(upgraded)

    # Strategy 4: embedded JSON (__NEXT_DATA__, etc.)
    if not gallery_urls:
        for script in soup.find_all("script"):
            script_text = script.string or ""
            if script.get("id") == "__NEXT_DATA__":
                try:
                    data = json.loads(script_text)
                    for val in _walk_json_for_images(data):
                        if val not in seen and _looks_like_product_image(val):
                            seen.add(val)
                            upgraded = _upgrade_dhgate_url(val)
                            gallery_urls.add(upgraded)
                except json.JSONDecodeError:
                    pass
            if "__INITIAL_STATE__" in script_text or "window.__INITIAL_STATE__" in script_text:
                match = re.search(r"window\.__INITIAL_STATE__\s*=\s*({.*?});", script_text, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        for val in _walk_json_for_images(data):
                            if val not in seen and _looks_like_product_image(val):
                                seen.add(val)
                                upgraded = _upgrade_dhgate_url(val)
                                gallery_urls.add(upgraded)
                    except json.JSONDecodeError:
                        pass

    # Strategy 5: CDN regex fallback (last resort)
    if not gallery_urls:
        for pat, _label in _CDN_PATTERNS:
            if "dhresource" in _label:
                for m in pat.finditer(html):
                    url = m.group(0)
                    if url not in seen and _looks_like_product_image(url):
                        seen.add(url)
                        upgraded = _upgrade_dhgate_url(url)
                        gallery_urls.add(upgraded)

    if gallery_urls:
        urls = list(gallery_urls)
        urls.sort(key=_img_quality, reverse=True)
        return urls
    return []


def _walk_json_for_images(data: Any) -> list[str]:
    """Recursively walk a parsed JSON tree to find image URLs on dhresource CDN."""
    results: list[str] = []
    if isinstance(data, dict):
        for v in data.values():
            results.extend(_walk_json_for_images(v))
    elif isinstance(data, list):
        for item in data:
            results.extend(_walk_json_for_images(item))
    elif isinstance(data, str) and "dhresource" in data and _IMAGE_EXT.search(data):
        results.append(data)
    return results


def _extract_mic_gallery(html: str, page_url: str) -> list[str]:
    """Extract product images from made-in-china.com product pages.

    Multi-strategy: JSON-LD (authoritative full-res), then gallery container,
    then broader data-original scan.  Deduplicates by unique image ID,
    keeping the best-resolution variant per image.
    """
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    urls: list[str] = []

    # Strategy 1: JSON-LD (most authoritative, full resolution)
    for u in _extract_json_ld_images(soup):
        if u not in seen:
            seen.add(u)
            urls.append(u)

    # Strategy 2: Gallery container (stable JS-hook class)
    gallery = soup.select_one("div.J-pic-list-wrap")
    if gallery:
        for img in gallery.find_all("img"):
            for attr in ("data-original", "src"):
                val = img.get(attr, "")
                if val:
                    absolute = urljoin(page_url, val)
                    if _is_mic_image(absolute) and absolute not in seen:
                        seen.add(absolute)
                        urls.append(absolute)

    # Strategy 3: Broader data-original scan for different-angle images
    for img in soup.find_all("img"):
        dor = img.get("data-original", "")
        if dor:
            absolute = urljoin(page_url, dor)
            if _is_mic_image(absolute) and absolute not in seen:
                seen.add(absolute)
                urls.append(absolute)

    if not urls:
        # Fall back to generic extractor for unusual page structures
        generic = extract_image_urls(html, page_url)
        for u in generic:
            if _is_mic_image(u) and u not in seen:
                seen.add(u)
                urls.append(u)

    if not urls:
        return []

    urls = _dedup_mic_urls(urls)
    return urls[:5]


_MIC_CDN_ID = re.compile(r"image\.made-in-china\.com/([a-zA-Z0-9]+)/")


def _is_mic_image(url: str) -> bool:
    """Strictly validate a made-in-china.com image URL is a genuine product image."""
    if not _looks_like_product_image(url):
        return False
    lower = url.lower()
    if "image.made-in-china.com" not in lower:
        return False
    if "/43f34j00" in lower:    # recommended products from other sellers
        return False
    if "/206f0j00" in lower:    # company logo / banner
        return False
    if "/318f0j00" in lower or "/229f0j00" in lower or "/313f0j00" in lower:
        return False
    if "-mp4." in lower:        # video thumbnail
        return False
    return True


def _mic_image_id(url: str) -> str | None:
    """Extract the unique image ID from a MIC CDN URL (last 12 chars of first path segment)."""
    m = _MIC_CDN_ID.search(url)
    if m:
        seg = m.group(1)
        return seg[-12:] if len(seg) >= 12 else seg
    return None


def _mic_url_priority(url: str) -> int:
    """Lower = better resolution variant for dedup."""
    m = _MIC_CDN_ID.search(url)
    if not m:
        return 99
    seg = m.group(1)
    if seg.startswith("2f0j00") or seg.startswith("202f0"):
        return 0
    if seg.startswith("371f3") or seg.startswith("374f3") or seg.startswith("373f3"):
        return 1
    if seg.startswith("203f0"):
        return 2
    if seg.startswith("3f2j00"):
        return 3
    return 10


def _dedup_mic_urls(urls: list[str]) -> list[str]:
    """Deduplicate by image ID keeping the best-resolution variant per image."""
    by_id: dict[str, str] = {}
    for u in urls:
        img_id = _mic_image_id(u)
        if not img_id:
            continue
        if img_id not in by_id or _mic_url_priority(u) < _mic_url_priority(by_id[img_id]):
            by_id[img_id] = u

    seen_ids: set[str] = set()
    result: list[str] = []
    for u in urls:
        img_id = _mic_image_id(u)
        if img_id and img_id in by_id and img_id not in seen_ids:
            result.append(by_id[img_id])
            seen_ids.add(img_id)
        elif img_id is None and u not in seen_ids:
            result.append(u)
            seen_ids.add(u)

    result.sort(key=_img_quality, reverse=True)
    return result


_ALIEXPRESS_GALLERY_SELECTORS = [
    ".detail-gallery img",
    ".product-gallery img",
    ".image-gallery img",
    ".gallery-item img",
    ".image-view img",
    "[class*='gallery'] img",
    "#root img",
    "#detail-img",
    ".product-main-image",
    ".product-img-wrap img",
    "[data-role='gallery'] img",
]

_ALIEXPRESS_JSON_VARS = ["_dsc_g_config", "g_config", "runParams", "data"]


def _walk_json_for_ae_images(data: Any, page_url: str, seen: set[str]) -> list[str]:
    """Recursively walk parsed JSON to find AliExpress image URLs."""
    results: list[str] = []
    if isinstance(data, dict):
        for key, val in data.items():
            if isinstance(val, str) and ("alicdn" in val.lower() or "ae" in val.lower()[:4]):
                abs_url = urljoin(page_url, val)
                if _is_aliexpress_image(abs_url) and abs_url not in seen:
                    seen.add(abs_url)
                    results.append(abs_url)
            elif isinstance(val, (dict, list)):
                results.extend(_walk_json_for_ae_images(val, page_url, seen))
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, str) and ("alicdn" in item.lower() or "ae01" in item.lower()):
                abs_url = urljoin(page_url, item)
                if _is_aliexpress_image(abs_url) and abs_url not in seen:
                    seen.add(abs_url)
                    results.append(abs_url)
            elif isinstance(item, (dict, list)):
                results.extend(_walk_json_for_ae_images(item, page_url, seen))
    return results


def _is_aliexpress_image(url: str) -> bool:
    if not _looks_like_product_image(url):
        return False
    lower = url.lower()
    # Reject icons, banners, captcha
    for pat in _1688_REJECT_PATTERNS:
        if pat.search(lower):
            return False
    return True


def _extract_aliexpress_gallery(html: str, page_url: str) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []

    # Strategy 1: JSON-LD (most authoritative)
    soup = BeautifulSoup(html, "lxml")
    for u in _extract_json_ld_images(soup):
        abs_url = urljoin(page_url, u)
        if _is_aliexpress_image(abs_url) and abs_url not in seen:
            seen.add(abs_url)
            urls.append(abs_url)

    if urls:
        return urls

    # Strategy 2: Embedded JSON variables (AE-specific)
    for var_name in _ALIEXPRESS_JSON_VARS:
        data = _extract_json_var(html, var_name)
        if data:
            for path in ("images", "imageList", "gallery", "imageUrl", "image",
                         "productDetail.images", "productDetail.image",
                         "module.productDetail.images", "module.productDetail.image",
                         "productDetail.skuBase.productSKUPropertyList",
                         "module.productDetail.skuBase.productSKUPropertyList"):
                vals = _deep_get(data, path, [])
                if isinstance(vals, str):
                    vals = [vals]
                for item in vals if isinstance(vals, list) else [vals]:
                    if isinstance(item, str):
                        abs_url = urljoin(page_url, item)
                        if _is_aliexpress_image(abs_url) and abs_url not in seen:
                            seen.add(abs_url)
                            urls.append(abs_url)
                    elif isinstance(item, dict):
                        for key in ("url", "src", "imageUrl", "imgUrl",
                                    "original", "fullSizeImageUrl",
                                    "skuPropertyImagePath", "imagePath"):
                            val = item.get(key, "")
                            if val:
                                abs_url = urljoin(page_url, val)
                                if _is_aliexpress_image(abs_url) and abs_url not in seen:
                                    seen.add(abs_url)
                                    urls.append(abs_url)
                        # Nested: skuPropertyValues within skuBase
                        for sub in item.get("skuPropertyValues", []):
                            path_val = sub.get("skuPropertyImagePath", "")
                            if path_val:
                                abs_url = urljoin(page_url, path_val)
                                if _is_aliexpress_image(abs_url) and abs_url not in seen:
                                    seen.add(abs_url)
                                    urls.append(abs_url)

    if urls:
        return urls

    # Strategy 2b: Next.js __NEXT_DATA__ script (modern AliExpress)
    next_data = soup.find("script", id="__NEXT_DATA__", type="application/json")
    if next_data and next_data.string:
        try:
            nd = json.loads(next_data.string)
            nd_urls = _walk_json_for_ae_images(nd, page_url, seen)
            urls.extend(nd_urls)
        except (json.JSONDecodeError, Exception):
            pass

    if urls:
        return urls

    # Strategy 3: DOM gallery selectors
    for selector in _ALIEXPRESS_GALLERY_SELECTORS:
        for el in soup.select(selector):
            for attr in ("src", "data-src", "data-lazyload", "data-original"):
                val = el.get(attr, "")
                if val:
                    abs_url = urljoin(page_url, val)
                    if _is_aliexpress_image(abs_url) and abs_url not in seen:
                        seen.add(abs_url)
                        urls.append(abs_url)
            data_imgs = el.get("data-imgs", "")
            if data_imgs and data_imgs.strip().startswith("["):
                try:
                    items = json.loads(data_imgs)
                    for item in items if isinstance(items, list) else [items]:
                        if isinstance(item, dict):
                            for key in ("imgSrc", "src", "url", "image"):
                                val = item.get(key, "")
                                if val:
                                    abs_url = urljoin(page_url, val)
                                    if _is_aliexpress_image(abs_url) and abs_url not in seen:
                                        seen.add(abs_url)
                                        urls.append(abs_url)
                except (json.JSONDecodeError, Exception):
                    pass

    if urls:
        return urls

    # Strategy 4: CDN regex — AliExpress uses ae0[0-9].alicdn / ae-pic-a1.aliexpress-media.com
    ae_cdn_re = re.compile(
        r"https?://[^\"'\s>]*(?:ae0\d|ae-pic-a1|ae[0-9]{2})[^\"'\s>]*(?:alicdn|aliexpress-media)[^\"'\s>]*\.(?:jpg|jpeg|png|webp)",
        re.I,
    )
    for m in ae_cdn_re.finditer(html):
        u = m.group(0)
        if _is_aliexpress_image(u) and u not in seen:
            seen.add(u)
            urls.append(u)

    if urls:
        return urls

    # Strategy 5: Any alicdn URL on AliExpress pages
    for m in re.finditer(r"https?://[^\"'\s>]*alicdn[^\"'\s>]*\.(?:jpg|jpeg|png|webp)", html, re.I):
        u = m.group(0)
        if _is_aliexpress_image(u) and u not in seen:
            seen.add(u)
            urls.append(u)

    return urls


def is_plausible_product_page(html: str, page_url: str) -> tuple[bool, str]:
    soup = BeautifulSoup(html, "lxml")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    h1_tag = soup.find("h1")
    h1 = h1_tag.get_text(strip=True) if h1_tag else ""

    # Not-found or error pages
    title_lower = title.lower()
    not_found_kw = ["404", "not found", "page not found", "error 404",
                    "this page could not be found", "product not found",
                    "sorry", "we couldn't find", "page unavailable",
                    "page does not exist", "product does not exist",
                    "no longer available", "page is no longer available"]
    for kw in not_found_kw:
        if kw in title_lower:
            return False, f"Page appears to be an error/not-found page — title contains '{kw}'"

    # Meaningful product title
    if not h1 or len(h1) < 5:
        return False, f"No meaningful product title found (H1='{h1[:50]}')"

    # Body has actual content
    body = soup.find("body")
    if body:
        text = body.get_text(strip=True)
        if len(text) < 200:
            return False, f"Page body too short ({len(text)} chars) — not a product page"

    return True, ""


# Per-domain image extractor dispatch table.
# Add new site-specific extractors here.
DOMAIN_IMAGE_EXTRACTORS: dict[str, callable] = {
    "1688.com": _extract_1688_gallery,
    "detail.1688.com": _extract_1688_gallery,
    "alibaba.com": _extract_alibaba_gallery,
    "aliexpress.com": _extract_aliexpress_gallery,
    "amazon.com": lambda html, page_url: _extract_amazon_color_images_from_script(html),
    "amazon.co.uk": lambda html, page_url: _extract_amazon_color_images_from_script(html),
    "amazon.de": lambda html, page_url: _extract_amazon_color_images_from_script(html),
    "amazon.fr": lambda html, page_url: _extract_amazon_color_images_from_script(html),
    "amazon.it": lambda html, page_url: _extract_amazon_color_images_from_script(html),
    "amazon.es": lambda html, page_url: _extract_amazon_color_images_from_script(html),
    "amazon.ca": lambda html, page_url: _extract_amazon_color_images_from_script(html),
    "amazon.in": lambda html, page_url: _extract_amazon_color_images_from_script(html),
    "amazon.com.au": lambda html, page_url: _extract_amazon_color_images_from_script(html),
    "amazon.com.br": lambda html, page_url: _extract_amazon_color_images_from_script(html),
    "amazon.com.mx": lambda html, page_url: _extract_amazon_color_images_from_script(html),
    "amazon.nl": lambda html, page_url: _extract_amazon_color_images_from_script(html),
    "amazon.pl": lambda html, page_url: _extract_amazon_color_images_from_script(html),
    "amazon.se": lambda html, page_url: _extract_amazon_color_images_from_script(html),
    "amazon.sg": lambda html, page_url: _extract_amazon_color_images_from_script(html),
    "amazon.ae": lambda html, page_url: _extract_amazon_color_images_from_script(html),
    "amazon.sa": lambda html, page_url: _extract_amazon_color_images_from_script(html),
    "dhgate.com": _extract_dhgate_gallery,
    "m.dhgate.com": _extract_dhgate_gallery,
    "www.dhgate.com": _extract_dhgate_gallery,
    "made-in-china.com": _extract_mic_gallery,
    "www.made-in-china.com": _extract_mic_gallery,
}


def extract_images_for_domain(html: str, page_url: str, domain: str) -> list[str]:
    for d, extractor in DOMAIN_IMAGE_EXTRACTORS.items():
        if d in domain:
            return extractor(html, page_url)
    return extract_image_urls(html, page_url)


def _looks_like_image(url: str) -> bool:
    return bool(_IMAGE_EXT.search(url))


def _looks_like_product_image(url: str) -> bool:
    if not _IMAGE_EXT.search(url):
        return False
    lower = url.lower()
    banned = ("icon", "logo", "avatar", "banner", "spacer", "pixel", "captcha",
              "sprite", "button", "btn_", "thumb_", "favicon", "loading",
              "placeholder", "transparent", "noimg", "no-img", "spacer.gif",
              "blank.gif", "clear.gif", "pixel.gif")
    if any(b in lower for b in banned):
        return False
    return True
