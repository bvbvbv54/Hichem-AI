from __future__ import annotations

import csv
import io
import json
import tempfile
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_csv_reader():
    from services.extractor.excel_reader import ExcelReader

    csv_content = "URL,Name,Price\nhttps://example.com,Test Product,19.99\n"
    reader = ExcelReader()
    result = await reader.read_bytes(csv_content.encode(), "test.csv")

    assert result.total_rows == 1
    assert result.valid_rows == 1
    assert len(result.products) == 1
    assert result.products[0].product_url == "https://example.com"
    assert result.products[0].product_name == "Test Product"


@pytest.mark.asyncio
async def test_excel_parse_result():
    from services.extractor.excel_reader import ExcelReader

    reader = ExcelReader()
    rows = [
        {"URL": "https://example.com/a", "Name": "Alpha"},
        {"link": "https://example.com/b", "Title": "Beta"},
    ]
    result = reader.parse_rows(rows)
    assert result.valid_rows == 2
    assert result.products[0].product_url == "https://example.com/a"
    assert result.products[1].product_url == "https://example.com/b"


@pytest.mark.asyncio
async def test_generic_parser():
    from services.extractor.parsers.generic import GenericParser

    parser = GenericParser()
    assert parser.can_handle("https://example.com/product") is True
    assert parser.can_handle("not-a-url") is False


@pytest.mark.asyncio
async def test_alibaba_parser():
    from services.extractor.parsers.alibaba import AlibabaParser

    parser = AlibabaParser()
    assert parser.can_handle("https://www.alibaba.com/product/123") is True
    assert parser.can_handle("https://example.com") is False


@pytest.mark.asyncio
async def test_aliexpress_parser():
    from services.extractor.parsers.aliexpress import AliExpressParser

    parser = AliExpressParser()
    assert parser.can_handle("https://www.aliexpress.com/item/123") is True
    assert parser.can_handle("https://example.com") is False


@pytest.mark.asyncio
async def test_product_extractor_finds_parser():
    from services.extractor.product_extractor import ProductExtractor

    extractor = ProductExtractor()
    parser = extractor._find_parser("https://www.alibaba.com/product/123")
    assert parser is not None
    assert parser.__class__.__name__ == "AlibabaParser"

    parser = extractor._find_parser("https://www.example.com/product")
    assert parser is not None
    assert parser.__class__.__name__ == "GenericParser"
