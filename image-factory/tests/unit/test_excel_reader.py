from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_csv_reader(sample_csv):
    from services.extractor.excel_reader import ExcelReader
    reader = ExcelReader()
    result = await reader.read_bytes(sample_csv, "test.csv")
    assert result.total_rows == 2
    assert result.valid_rows == 2
    assert result.skipped_rows == 0
    assert result.duplicate_rows == 0
    assert len(result.warnings) == 0
    assert len(result.products) == 2
    assert result.products[0].product_url == "https://example.com/a"
    assert result.products[0].product_name == "Alpha"
    assert result.products[0].priority == 1


@pytest.mark.asyncio
async def test_xlsx_reader(sample_xlsx):
    from services.extractor.excel_reader import ExcelReader
    reader = ExcelReader()
    result = await reader.read_bytes(sample_xlsx, "test.xlsx")
    assert result.total_rows == 10
    assert result.valid_rows == 7
    assert result.skipped_rows == 2
    assert result.duplicate_rows == 1
    assert len(result.products) == 7
    assert any("skipped" in w for w in result.warnings)
    assert any("duplicate" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_deduplication_by_url():
    from services.extractor.excel_reader import ExcelReader
    reader = ExcelReader()
    rows = [
        {"url": "https://example.com/a", "name": "First"},
        {"url": "https://example.com/a", "name": "Duplicate"},
        {"url": "https://example.com/b", "name": "Unique"},
    ]
    result = reader.parse_rows(rows)
    assert result.valid_rows == 2
    assert result.duplicate_rows == 1
    assert result.products[0].product_name == "First"


@pytest.mark.asyncio
async def test_invalid_urls_skipped():
    from services.extractor.excel_reader import ExcelReader
    reader = ExcelReader()
    rows = [
        {"url": "not-a-url", "name": "Bad"},
        {"url": "", "name": "Empty"},
        {"url": "https://valid.com", "name": "Good"},
    ]
    result = reader.parse_rows(rows)
    assert result.valid_rows == 1
    assert result.skipped_rows == 2
    assert result.products[0].product_url == "https://valid.com"


@pytest.mark.asyncio
async def test_column_name_auto_detection():
    from services.extractor.excel_reader import COLUMN_MAP
    assert COLUMN_MAP["url"] == "product_url"
    assert COLUMN_MAP["link"] == "product_url"
    assert COLUMN_MAP["product link"] == "product_url"
    assert COLUMN_MAP["name"] == "product_name"
    assert COLUMN_MAP["title"] == "product_name"
    assert COLUMN_MAP["priority"] == "priority"
    assert COLUMN_MAP["category"] == "category"
    assert COLUMN_MAP["notes"] == "notes"
    assert COLUMN_MAP["note"] == "notes"


@pytest.mark.asyncio
async def test_priority_parsing():
    from services.extractor.excel_reader import ExcelReader
    reader = ExcelReader()
    rows = [
        {"url": "https://example.com/a", "priority": "5"},
        {"url": "https://example.com/b", "priority": "invalid"},
        {"url": "https://example.com/c"},
    ]
    result = reader.parse_rows(rows)
    assert result.products[0].priority == 5
    assert result.products[1].priority == 0
    assert result.products[2].priority == 0


@pytest.mark.asyncio
async def test_extracted_product_dataclass():
    from services.extractor.excel_reader import ExtractedProduct
    p = ExtractedProduct(product_url="https://example.com", product_name="Test", priority=3, row_number=5)
    assert p.product_url == "https://example.com"
    assert p.product_name == "Test"
    assert p.priority == 3
    assert p.row_number == 5


@pytest.mark.asyncio
async def test_unsupported_format():
    from services.extractor.excel_reader import ExcelReader
    reader = ExcelReader()
    with pytest.raises(ValueError, match="Unsupported file format"):
        await reader.read_bytes(b"data", "test.txt")
