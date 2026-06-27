# Image Factory — AI Image Generation Platform

A production-ready, set-and-forget AI image generation platform optimized for 4 vCPU / 8 GB RAM single-server deployment.

## Architecture

```
User Request → FastAPI → Celery → Claude (prompt) → Nano Banana (generate) → Storage → Delivery
```

### Services

| Service | Technology | Purpose |
|---------|-----------|---------|
| **API** | FastAPI + Uvicorn | REST endpoints, auth, rate limiting |
| **Worker** | Celery + Redis | Async job processing, retries |
| **PostgreSQL** | 16 Alpine | Job/asset persistence |
| **Redis** | 7 Alpine | Celery broker, result backend |
| **Flower** | (optional) | Celery monitoring |

### Modules

- **Claude Service** — Prompt generation, enhancement, optimization, product repositioning
- **Nano Banana** — Provider-isolated image generation (Replicate, StabilityAI, OpenAI)
- **Storage** — Pluggable backend (local FS, S3-compatible)
- **Delivery** — Pluggable backends (local folder, S3, webhook)
- **Product Extractor** — URL-based product data extraction (Alibaba, AliExpress, generic)
- **Product Repositioning** — AI-powered transformation of supplier products into premium European-market presentations
- **Translation** — Multilingual support via Claude

## Image Acquisition

The acquisition pipeline (`services/acquisition/`) extracts product images from Chinese e-commerce sites.

### Supported Sites

| Site | Status | Method | Notes |
|------|--------|--------|-------|
| **1688.com** | Fixed | Scrapfly CN + `_extract_1688_gallery()` | Images in IIFE JSON (`offerImgList`). Scoped extractor + raw-HTML fallback. |
| **alibaba.com** | Fixed | Scrapfly CN + `_extract_alibaba_gallery()` | Images in JSON-LD `Product.image`. JSON-LD extraction + raw-HTML fallback. |
| **aliexpress.com** | Fixed | Generic `extract_image_urls()` | Extraction works; placeholder GIF rejected by SHA256 hash in `image_downloader.py`. |

### Scrapfly Key Management

- Keys stored in DB (`settings` table) and managed via `/admin/scrapfly/keys` API.
- Per-key reset dates tracked in `scrapfly_key_manager._KEY_RESET_DATES` — keys auto-revive after their reset date.
- When all keys hit quota (`429` + `remaining=0`), `fetch_page()` enters a wait loop (polls every 5 min, max 24h) and sends a notification.
- Adding a new key via admin clears the quota-exhausted flag, causing waiting workers to resume immediately.

### Reject Filters (Placeholder Images)

Known-bad SHA256 hashes in `image_downloader._KNOWN_REJECTED_HASHES`:
- `a18efca9...` — AliExpress 150×150 animated loading placeholder GIF

To add a new reject hash without code changes, add it to the `global_rejected_hashes` Redis set.

## Quick Start

```bash
# 1. Clone and configure
git clone <repo> image-factory
cd image-factory
cp .env.example .env
# Edit .env with your API keys

# 2. Start everything
docker compose up -d

# 3. Verify
curl http://localhost:8000/api/v1/health

# 4. Generate an image
curl -X POST http://localhost:8000/api/v1/generate \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"subject": "red luxury handbag", "use_claude": true}'
```

## API Reference

### Authentication

All requests require the `X-API-Key` header. Set `API_KEY` in `.env`.

### Endpoints

**Health**
- `GET /api/v1/health` — Health check
- `GET /api/v1/health/ready` — Readiness (includes DB check)

**Generation**
- `POST /api/v1/generate` — Single image generation
- `POST /api/v1/generate/bulk` — Bulk generation

**Jobs**
- `GET /api/v1/jobs` — List all jobs (supports `status`, `project`, `limit`, `offset`)
- `GET /api/v1/jobs/{id}` — Job details with assets
- `GET /api/v1/jobs/{id}/status` — Quick status check
- `POST /api/v1/jobs/{id}/cancel` — Cancel a job
- `POST /api/v1/jobs/{id}/retry` — Retry a failed job
- `GET /api/v1/jobs/bulk/{parent_id}` — Bulk job progress
- `GET /api/v1/stats` — System statistics

**Templates**
- `GET /api/v1/templates` — List prompt templates (optional `category` filter)
- `GET /api/v1/templates/{name}` — Get specific template

**Products (Localization)**
- `POST /api/v1/products/upload` — Upload .xlsx/.csv spreadsheet for batch product localization
- `POST /api/v1/products/url` — Process a single product URL
- `GET /api/v1/products/{job_id}/output` — Get product localization output

### Generation Request Schema

```json
{
  "prompt": "Optional initial prompt",
  "subject": "Subject for Claude to create a prompt from",
  "template_name": "product_mockup",
  "template_parameters": {"product": "leather bag", "style": "minimalist"},
  "width": 1024,
  "height": 1024,
  "num_images": 1,
  "project_name": "my-project",
  "use_claude": true,
  "enhance_prompt": true,
  "style": "scandinavian",
  "mood": "elegant",
  "context": "Premium European brand"
}
```

## Prompt Templates

### E-commerce
- `product_mockup` — Professional product photography
- `lifestyle` — Lifestyle imagery with products in use
- `marketing_banner` — Campaign-ready banner graphics

### Content Creators
- `blog_thumbnail` — Click-worthy blog post thumbnails
- `instagram_creative` — Instagram feed and story creatives
- `linkedin_creative` — Professional B2B content
- `youtube_thumbnail` — High-CTR video thumbnails

### SaaS
- `landing_page` — Hero section graphics
- `feature_illustration` — Product feature showcases
- `marketing_asset` — General marketing materials

## Product Localization Workflow

The platform transforms supplier products into premium European-market presentations:

1. **Upload** an Excel/CSV file with product URLs (Alibaba, AliExpress, 1688, Temu, CJ Dropshipping, or generic supplier sites)
2. **Extract** product data and images via modular parsers
3. **Analyze** supplier images for product type, colors, materials, style
4. **Reposition** with Claude — generates premium brand concept, new title, tagline, brand story
5. **Generate** premium marketing images (hero, lifestyle, detail, banner)
6. **Package** output as ready-to-import Shopify/WooCommerce assets

Output structure:
```
outputs/
└── project-name/
    └── job-id/
        ├── generated-images/
        │   ├── hero_image_0.png
        │   ├── lifestyle_image_0.png
        │   ├── detail_image_0.png
        │   └── marketing_banner_0.png
        ├── product-copy.json    # New title, description, features, SEO keywords
        ├── product-data.json    # Extracted data, image analysis
        └── generation-log.json  # Processing metadata
```

## Configuration

All configuration via environment variables (see `.env.example`).

### Required Keys
- `CLAUDE_API_KEY` — Anthropic Claude API key
- `IMAGE_PROVIDER_API_KEY` — Replicate / StabilityAI / OpenAI key
- `API_KEY` — Your API gateway key
- `DATABASE_URL` — PostgreSQL connection string

### Deployment Settings
- `API_WORKERS=4` — Uvicorn workers (match vCPU count)
- `CELERY_WORKER_CONCURRENCY=4` — Celery workers
- `LOG_FORMAT=json` — Structured JSON logging

## Deployment

### VPS Requirements
- 4 vCPU, 8 GB RAM
- Docker Engine 24+
- Docker Compose v2+

### Production Deployment

```bash
# On your VPS:
git clone <repo> /opt/image-factory
cd /opt/image-factory
cp .env.example .env
# Edit .env with production settings
docker compose up -d

# Monitor
docker compose logs -f worker
docker compose logs -f api

# With monitoring (optional):
docker compose --profile monitoring up -d
# Flower UI at http://your-vps:5555
```

### Resource Allocation
| Service | Memory Limit | vCPU |
|---------|-------------|------|
| API | 1 GB | 1 |
| Worker | 2 GB | 2 |
| PostgreSQL | 2 GB | 1 |
| Redis | 1 GB | — |

## Error Handling

- **Retry policy**: Exponential backoff (2s → 4s → 8s → ... → 30s max)
- **Max retries**: 3 per task (configurable)
- **Dead-letter**: Failed jobs marked with status `failed` and error_message
- **Bulk isolation**: Each item in a bulk job fails independently
- **Recovery**: Failed jobs can be retried via API or automatically

## Testing

```bash
# Install test dependencies
pip install -e ".[all]" pytest pytest-asyncio httpx

# Run tests
pytest tests/ -v --asyncio-mode=auto
```

## Project Structure

```
image-factory/
├── api/                    # FastAPI application
│   ├── app.py
│   ├── routes/             # API endpoints
│   ├── schemas/            # Pydantic models
│   └── middleware/         # Auth, rate limiting
├── workers/                # Celery configuration
├── services/
│   ├── claude/             # Prompt generation & enhancement
│   ├── nano_banana/        # Image generation (provider-isolated)
│   ├── storage/            # Storage backends (local, S3)
│   ├── delivery/           # Delivery backends (local, S3, webhook)
│   ├── extractor/          # Product URL data extraction
│   ├── repositioning/      # AI product repositioning
│   ├── image_analysis/     # Supplier image analysis
│   └── translation/        # Multilingual support
├── database/               # SQLAlchemy models & migrations
├── models/                 # Domain models & enums
├── tasks/                  # Celery task definitions
├── configs/                # Settings & logging
├── docker/                 # Dockerfiles
├── tests/                  # Test suite
├── docker-compose.yml
├── .env.example
└── pyproject.toml
```

## Extending

### Add a new image provider
1. Create a class extending `BaseImageProvider` in `services/nano_banana/client.py`
2. Add it to `_create_provider` in `NanoBananaClient`
3. Add environment variables to `.env.example` and `settings.py`

### Add a new delivery backend
1. Create a class extending `DeliveryBackend` in `services/delivery/`
2. Add it to `create_delivery_backends()` in `services/delivery/local.py`

### Add a new prompt template
1. Add to `ECOMMERCE_TEMPLATES`, `CONTENT_TEMPLATES`, or `SAAS_TEMPLATES` in `services/claude/templates.py`

### Add a new supplier parser
1. Create a class extending `BaseParser` in `services/extractor/parsers/`
2. Add it to the `parsers` list in `ProductExtractor`
