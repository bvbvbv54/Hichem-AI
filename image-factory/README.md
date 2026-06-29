# Image Factory — E-Commerce Image Acquisition & Generation

A production-ready platform that extracts product images from e-commerce supplier sites (Alibaba, AliExpress, 1688.com, and more) and generates premium marketing imagery with built-in prompts. Designed for 4 vCPU / 8 GB RAM single-server deployment.

```
User Links → Acquisition Pipeline → Image Extraction → Image Generation → R2 Cloudflare Storage → Export (ZIP / Google Drive)
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
| **amazon.com** | Fixed | `_extract_amazon_color_images_from_script()` | 7/7 main product images from `colorImages` JSON script, 0 contamination |
| **dhgate.com** | Fixed | `_extract_dhgate_gallery()` | `ul[spm-c="imagelist"]` gallery, `/m/0x0/` full-res upgrade, alt-text swatch/recommended rejection |
| **made-in-china.com** | Fixed | `_extract_mic_gallery()` | JSON-LD + `div.J-pic-list-wrap` gallery, `43f34j00`/`206f0j00` garbage filtered, 5 images per product |
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

### 4. R2 Cloudflare Storage (`services/storage/r2.py`)

All scraped and AI-generated images are uploaded to Cloudflare R2 (S3-compatible) immediately after acquisition/generation. Each asset stores a 7-day presigned URL in its metadata for downstream export. R2 credentials are configured as module-level constants in `r2.py`.

### 5. Image Export

Images can be exported via two endpoints under `/api/v1/export/`:
- **ZIP download** (`GET /export/project/{project_id}/zip`) — streams a ZIP archive organized by product and image type (scraped vs AI-generated), falling back to local storage when R2 is unreachable
- **Google Drive** (`POST /export/project/{project_id}/drive-export`) — uploads to a structured Drive folder hierarchy using a service account

### 6. Image Hash Ban Mechanism

Operators can **ban** scraped image hashes directly from the dashboard. Banned hashes are:

- **Persisted** in the `settings` table (key `banned_image_hashes`, JSON array) — survives worker restarts
- **Synced** to Redis (`global_rejected_hashes` SET) on first worker Redis connection via `_sync_banned_hashes()`
- **Enforced** by the downloader — any hash in the reject set is skipped before download

**API Endpoints** (`/api/v1/assets/`):
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/ban` | Add hash to ban list |
| `POST` | `/unban` | Remove hash from ban list |
| `GET`  | `/banned-hashes` | List all banned hashes |

**Dashboard UI**: Each scraped image thumbnail shows a red **Ban** button (on hover). Clicking it calls `POST /assets/ban` and shows a success toast. Banned images also display an "Image Banned" overlay.

### 7. Low-Image Count Detection

Products with **≤ 2 scraped images** are flagged with an `AlertTriangle` badge on the product detail page, indicating the scrape may be partial or failed.

---

## Dashboard (Next.js Frontend)

The management UI is a Next.js 15 app at `dashboard/`:

```bash
cd dashboard
npm install
npm run dev        # http://localhost:3000
```

In development without Docker, the dashboard proxies `/api/*` requests to `http://localhost:8000/api/*` (configurable via `NEXT_PUBLIC_API_HOST` or `API_HOST` in `.env.local`). The rewrite rules in `next.config.ts` handle this transparently.

### Dashboard Features
- **Product list** with status badges (scraped, generated, error)
- **Product detail** — scraped image gallery (with ban buttons), generated images, timestamps, metadata
- **Project view** — aggregate product cards with progress tracking
- **Settings** — Scrapfly key management, product type presets, account settings
- **Upload** — manual image upload (drag & drop)
- **Admin** — system health, Scrapfly admin page
- **Notifications** — real-time worker notifications (quota exhaustion, failures)

---

## API Reference

The FastAPI backend exposes auto-generated docs:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

---

## To Do Next

| # | Prompt | Site | Problem | Approach |
| |---|--------|------|---------|----------|
| 1 | **Backfill R2 URLs** | All | 5 legacy products exist in DB without R2 URLs | Write a one-off task to re-upload existing local assets to R2 |
| 2 | **Drive Auth UX** | Settings | Service account upload requires file-based config | Add a web UI for Drive credential upload |
| 3 | **Temu** | temu.com | CAPTCHA on all automated access | Implement realistic CAPTCHA mitigation — session reuse, rate limiting, or honest failure |
| 4 | **Model Pricing Admin** | All | Generation pricing is seeded via code | Add a settings UI to view/edit model pricing, set per-customer credit multipliers |
| 5 | **Cleanup Tasks** | System | `services/cleanup.py` and `tasks/cleanup.py` are new | Wire into a scheduled Celery beat or cron job |

---

## Configuration

All via environment variables (see `.env.example`).

### Required
- `API_KEY` — API gateway authentication
- `DATABASE_URL` — PostgreSQL connection string
- `SCRAPFLY_API_KEY` (or DB-managed) — Scrapfly for CN site access

### R2 (Cloudflare)
- `R2_ACCOUNT_ID`, `R2_ACCESS_KEY`, `R2_SECRET_KEY` — Cloudflare R2 credentials (configured in `services/storage/r2.py`)

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
│   ├── storage/            # Storage backends (local, R2 S3-compatible)
│   ├── delivery/           # Delivery backends (local, webhook)
│   ├── reference_scoring.py # Reference image scoring for selection
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
