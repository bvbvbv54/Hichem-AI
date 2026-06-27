# Image Factory — E-Commerce Image Acquisition & Generation

A production-ready platform that extracts product images from e-commerce supplier sites (Alibaba, AliExpress, 1688.com, and more) and generates premium marketing imagery with built-in prompts. Designed for 4 vCPU / 8 GB RAM single-server deployment.

```
User Links → Acquisition Pipeline → Image Extraction → Image Generation → Storage
```

---

## Pipeline

### 1. Acquisition (`services/acquisition/`)

Extracts product images from Chinese e-commerce sites via Scrapfly (CN-routed with `country=cn` + `render_js`) with Playwright browser fallback.

#### Supported Sites

| Site | Status | Method | Notes |
|------|--------|--------|-------|
| **1688.com** | Fixed | `_extract_1688_gallery()` | IIFE JSON (`offerImgList`) + raw-HTML regex fallback |
| **alibaba.com** | Fixed | `_extract_alibaba_gallery()` | JSON-LD `Product.image` + raw-HTML alicdn regex fallback |
| **aliexpress.com** | Fixed | Generic `extract_image_urls()` | Placeholder GIF rejected by SHA256 hash |
| **amazon.com** | ❌ To Do | — | Only 1 of many gallery images extracted |
| **dhgate.com** | ❌ To Do | — | Color-swatch + "More Choices" carousel pollution |
| **made-in-china.com** | ❌ To Do | — | Zero extraction despite accessible page |
| **jd.com** | ❌ To Do | Ban list | Block at the URL level |
| **taobao.com** | ❌ To Do | Ban list | Block at the URL level |
| **temu.com** | ❌ To Do | CAPTCHA | Needs mitigation strategy |

### 2. Image Extraction Pipeline

```
Scrapfly (CN) → Page Validity Check → Domain-Specific Extractor → Generic Extractor → Downloader
```

- **Page validity**: `validate_product_page()` checks H1 title + product ID before extracting
- **Domain dispatch**: `DOMAIN_IMAGE_EXTRACTORS` routes to site-specific gallery extractors
- **Fallback chain**: Scrapfly JS → Scrapfly no-JS → Playwright browser → HTTP fetch
- **Download validation**: SHA256/pHash dedup, 100×100 min dimensions, MIME-type check

### 3. Scrapfly Key Management

- Keys stored in DB (`settings` table), managed via `/admin/scrapfly/keys` API
- Per-key reset dates tracked — keys auto-revive after their monthly billing reset
- When all keys are exhausted (`429` + `remaining=0`), workers enter a wait loop (poll every 5 min, max 24h) and send a notification
- Adding a new key clears the quota-exhausted flag and resumes waiting workers

### 4. Placeholder Reject Filter

Known-bad SHA256 hashes prevent non-product images from entering the pipeline:

```
a18efca9...  AliExpress 150×150 animated loading GIF
```

Add new hashes to `image_downloader._KNOWN_REJECTED_HASHES` or the `global_rejected_hashes` Redis set.

---

## To Do Next

| # | Prompt | Site | Problem | Approach |
|---|--------|------|---------|----------|
| 4 | **Amazon** | amazon.com | Only 1 of many gallery images extracted | Investigate page structure — likely JS-loaded image gallery in `data-a-dynamic-image` or `data-old-hires` attributes |
| 5 | **DHgate** | dhgate.com | Color-swatch + "More Choices" carousel images pollute results | Add `dhgate.com` to `DOMAIN_IMAGE_EXTRACTORS` with scoped selectors from `profiles/dhgate.json`; reject swatch thumbnails by URL pattern |
| 6 | **Made-in-China** | made-in-china.com | Zero extraction despite accessible page | Check `_CN_PRIMARY_DOMAINS` routing, add domain-specific extractor |
| 7 | **Ban List** | jd.com, taobao.com | CAPTCHA blocks all extraction | Add to domain ban list at URL level — fail fast with clear reason |
| 8 | **Temu** | temu.com | CAPTCHA on all automated access | Implement realistic CAPTCHA mitigation — session reuse, rate limiting, or honest failure |
| 9 | **Final Validation** | All sites | Run all fixes end-to-end | Run `AcquisitionPipeline.run()` against live URLs for all fixed sites simultaneously |

---

## Configuration

All via environment variables (see `.env.example`).

### Required
- `API_KEY` — API gateway authentication
- `DATABASE_URL` — PostgreSQL connection string
- `SCRAPFLY_API_KEY` (or DB-managed) — Scrapfly for CN site access

### Image Providers
- `IMAGE_PROVIDER_API_KEY` — Replicate / StabilityAI / OpenAI (for generation)

### Optional
- `CLAUDE_API_KEY` — Reserved for future LLM-powered prompt enhancement
- `CELERY_WORKER_CONCURRENCY=4` — Worker count
- `LOG_FORMAT=json` — Structured logging

---

## Quick Start

```bash
# Clone and configure
git clone <repo> image-factory
cd image-factory
cp .env.example .env
# Edit .env with your API keys

# Start services
docker compose up -d

# Verify
curl http://localhost:8000/api/v1/health

# Submit a product URL for image extraction
curl -X POST http://localhost:8000/api/v1/products/url \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.alibaba.com/product-detail/..."}'
```

---

## Output Structure

```
outputs/
└── project-name/
    └── job-id/
        ├── images/
        │   ├── product_0.jpg
        │   ├── product_1.jpg
        │   └── ...
        ├── product-data.json   # Extracted metadata
        └── generation-log.json # Processing metadata
```

---

## Project Structure

```
image-factory/
├── api/                    # FastAPI application
│   ├── app.py
│   ├── routes/             # API endpoints
│   └── middleware/         # Auth, rate limiting
├── workers/                # Celery configuration
├── services/
│   ├── acquisition/        # Scrapfly client, image extractor, downloader, pipeline
│   │   ├── image_extractor.py   # Domain-specific + generic extractors
│   │   ├── image_downloader.py  # Download + SHA256/pHash dedup + reject filter
│   │   ├── scrapfly_client.py   # Scrapfly API client with key rotation
│   │   ├── pipeline.py          # Orchestration
│   │   └── browser_client.py    # Playwright fallback
│   ├── claude/             # Reserved for future LLM prompt enhancement
│   ├── nano_banana/        # Image generation providers
│   ├── storage/            # Storage backends (local, S3)
│   ├── delivery/           # Delivery backends (local, S3, webhook)
│   ├── extractor/          # Product URL data parsing
│   └── intelligence/       # Profiles, rate limiting, captcha management
├── database/               # SQLAlchemy models & migrations
├── models/                 # Domain models & enums
├── tasks/                  # Celery task definitions
├── configs/                # Settings & logging
├── docker/                 # Dockerfiles
├── tests/                  # Test suite
├── .env.example
├── docker-compose.yml
└── pyproject.toml
```

---

## Testing

```bash
pip install -e ".[all]" pytest pytest-asyncio httpx
pytest tests/ -v --asyncio-mode=auto
```

---

## Deployment

### Requirements
- 4 vCPU, 8 GB RAM
- Docker Engine 24+
- Docker Compose v2+

```bash
git clone <repo> /opt/image-factory
cd /opt/image-factory
cp .env.example .env
# Edit .env with production settings
docker compose up -d
```
