from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from configs.logging import get_logger

logger = get_logger(__name__)

URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)

COLUMN_MAP: dict[str, str] = {
    "url": "product_url",
    "link": "product_url",
    "product url": "product_url",
    "product link": "product_url",
    "product_url": "product_url",
    "name": "product_name",
    "title": "product_name",
    "product name": "product_name",
    "product title": "product_name",
    "product_name": "product_name",
    "sku": "product_name",
    "priority": "priority",
    "order": "priority",
    "category": "category",
    "type": "category",
    "notes": "notes",
    "note": "notes",
    "comment": "notes",
    "description": "product_description",
    "product description": "product_description",
    "desc": "product_description",
    "product image": "product_image",
    "product images": "product_images",
    "image": "product_image",
    "images": "product_images",
    "supplier": "supplier_name",
    "supplier name": "supplier_name",
    "price": "price",
    "supplier price": "price",
}


@dataclass
class ExtractedProduct:
    product_url: str
    product_name: str = ""
    priority: int = 0
    category: str = ""
    notes: str = ""
    product_description: str = ""
    product_image: str = ""
    supplier_name: str = ""
    price: str = ""
    row_number: int = 0


@dataclass
class ExcelParseResult:
    total_rows: int = 0
    valid_rows: int = 0
    skipped_rows: int = 0
    duplicate_rows: int = 0
    products: list[ExtractedProduct] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ExcelReader:

    def __init__(self) -> None:
        self._openpyxl = None

    @property
    def _has_openpyxl(self) -> bool:
        if self._openpyxl is not None:
            return self._openpyxl
        try:
            import openpyxl  # noqa
            self._openpyxl = True
        except ImportError:
            self._openpyxl = False
        return self._openpyxl

    def _find_url_column(self, raw_rows: list[dict[str, Any]]) -> str | None:
        """Find the column that contains URLs by scanning header names first,
        then falling back to data content."""
        if not raw_rows:
            return None
        headers = list(raw_rows[0].keys())
        # First pass: match known URL column name patterns
        for h in headers:
            norm = h.strip().lower()
            if norm in ("url", "link", "product url", "product link", "product_url", "product_link", "website", "site", "href"):
                return h
        # Second pass: check if any column contains mostly URL-like values
        url_pattern = re.compile(r"^https?://", re.IGNORECASE)
        for h in headers:
            url_count = 0
            for row in raw_rows[:20]:
                val = str(row.get(h, "")).strip()
                if url_pattern.match(val):
                    url_count += 1
            if url_count >= 3 or (url_count > 0 and url_count == len(raw_rows[:20])):
                return h
        # Third pass: return the first column that has ANY URL
        for h in headers:
            for row in raw_rows[:10]:
                val = str(row.get(h, "")).strip()
                if url_pattern.match(val):
                    return h
        return None

    def _find_name_column(self, raw_rows: list[dict[str, Any]], url_col: str | None) -> str | None:
        """Find the column that contains product names by checking headers."""
        if not raw_rows:
            return None
        headers = list(raw_rows[0].keys())
        name_keywords = {"name", "title", "product name", "product title", "product_name",
                         "product", "item", "description", "desc", "sku"}
        for h in headers:
            norm = h.strip().lower()
            if norm in name_keywords:
                return h
        # If URL column is found, use the column immediately to its left as name
        if url_col:
            col_idx = headers.index(url_col)
            if col_idx > 0:
                return headers[col_idx - 1]
        return None

    def _normalize_headers(self, raw_headers: list[str]) -> list[str]:
        return [COLUMN_MAP.get(h.strip().lower(), h.strip().lower()) for h in raw_headers]

    def _build_product(self, row: dict[str, Any], row_number: int) -> ExtractedProduct:
        url = (row.get("product_url") or "").strip()
        name = (row.get("product_name") or "").strip()
        raw_priority = row.get("priority")
        priority = 0
        if raw_priority is not None:
            try:
                priority = int(raw_priority)
            except (ValueError, TypeError):
                pass
        return ExtractedProduct(
            product_url=url,
            product_name=name,
            priority=priority,
            category=(row.get("category") or "").strip(),
            notes=(row.get("notes") or "").strip(),
            product_description=(row.get("product_description") or "").strip(),
            product_image=(row.get("product_image") or "").strip(),
            supplier_name=(row.get("supplier_name") or "").strip(),
            price=(row.get("price") or "").strip(),
            row_number=row_number,
        )

    def _is_valid_url(self, url: str) -> bool:
        return bool(URL_RE.match(url))

    def parse_rows(self, raw_rows: list[dict[str, Any]]) -> ExcelParseResult:
        result = ExcelParseResult()
        seen_urls: set[str] = set()

        url_col = self._find_url_column(raw_rows)
        name_col = self._find_name_column(raw_rows, url_col) if url_col else None
        if url_col:
            result.warnings.append(f"Auto-detected URL column: '{url_col}'")
            if name_col:
                result.warnings.append(f"Auto-detected name column: '{name_col}'")

        for idx, raw in enumerate(raw_rows):
            row_num = idx + 2
            result.total_rows += 1
            row = {}
            for k, v in raw.items():
                norm_k = COLUMN_MAP.get(k.strip().lower(), k.strip().lower())
                row[norm_k] = v

            # If URL column was auto-detected (not from normal headers), inject it
            if url_col and not row.get("product_url"):
                raw_url = str(raw.get(url_col, "")).strip()
                if raw_url:
                    row["product_url"] = raw_url
            if name_col and not row.get("product_name"):
                raw_name = str(raw.get(name_col, "")).strip()
                if raw_name:
                    row["product_name"] = raw_name

            url = (row.get("product_url") or "").strip()

            if not url:
                result.skipped_rows += 1
                result.warnings.append(f"Row {row_num}: URL is empty (skipped)")
                continue

            if not self._is_valid_url(url):
                result.skipped_rows += 1
                result.warnings.append(f"Row {row_num}: URL '{url}' is not valid (skipped)")
                continue

            if url in seen_urls:
                result.duplicate_rows += 1
                result.warnings.append(f"Row {row_num}: duplicate URL '{url}' (skipped)")
                continue

            seen_urls.add(url)
            product = self._build_product(row, row_num)
            result.products.append(product)
            result.valid_rows += 1

        return result

    async def read_bytes(self, data: bytes, filename: str) -> ExcelParseResult:
        ext = Path(filename).suffix.lower()
        if ext == ".csv":
            return self._parse_csv_bytes(data)
        elif ext in (".xlsx", ".xls"):
            result = self._parse_xlsx_bytes(data, filename)
            return result
        else:
            raise ValueError(f"Unsupported file format: {ext}")

    def _parse_csv_bytes(self, data: bytes) -> ExcelParseResult:
        content = data.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        raw_rows: list[dict[str, Any]] = []
        for row in reader:
            raw_rows.append({k.strip(): v.strip() if v else "" for k, v in row.items()})
        return self.parse_rows(raw_rows)

    def _parse_xlsx_bytes(self, data: bytes, filename: str) -> ExcelParseResult:
        if not self._has_openpyxl:
            raise RuntimeError("openpyxl is required for .xlsx files. Install with: pip install openpyxl")
        import openpyxl
        import tempfile
        tmp = Path(tempfile.gettempdir()) / filename
        tmp.write_bytes(data)
        try:
            wb = openpyxl.load_workbook(str(tmp), read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            wb.close()
            if not rows:
                return ExcelParseResult()

            first_row = rows[0]
            if first_row and any(cell is not None for cell in first_row):
                headers = [str(h).strip() if h else f"column_{i}" for i, h in enumerate(first_row)]
            else:
                max_cols = max((len(r) for r in rows), default=0)
                headers = [f"column_{i}" for i in range(max_cols)]

            raw_rows: list[dict[str, Any]] = []
            start_idx = 0 if not first_row or not any(cell is not None for cell in first_row) else 1
            for row in rows[start_idx:]:
                if not any(cell is not None for cell in row):
                    continue
                product: dict[str, Any] = {}
                for i, value in enumerate(row):
                    if i < len(headers):
                        product[headers[i]] = value if value is not None else ""
                raw_rows.append(product)
            return self.parse_rows(raw_rows)
        finally:
            tmp.unlink(missing_ok=True)
