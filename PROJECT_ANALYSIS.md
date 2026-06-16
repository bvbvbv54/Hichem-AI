# ImageFactory — Complete Project Analysis

## Overview

ImageFactory is a "Set-and-Forget AI Image Generation Platform" optimized for e-commerce. It transforms supplier products (Alibaba, AliExpress, 1688, etc.) into premium European-market marketing assets using AI (Claude for text, Replicate/StabilityAI/OpenAI/OpenRouter for images).

**Stack:** FastAPI + Celery + PostgreSQL + Redis + Next.js dashboard
**Deployment:** Docker Compose on 4 vCPU / 8 GB RAM single server

---

## Architecture: User Request → FastAPI → Celery → Claude → Nano Banana → Storage → Delivery

---

## File-by-File Breakdown

### 1. Core Config & Entry Points

#### `pyproject.toml`
Python project config. Dependencies split into `[api]`, `[worker]`, `[all]` extras. Uses Black/Ruff formatting, pytest with asyncio mode.

#### `configs/settings.py` (135 lines)
Single `Settings` pydantic-settings class reading from `.env`. Manages all config: app name/version, API host/port/rate-limit, DB/Redis URLs, Claude/OpenRouter/Replicate/StabilityAI API keys, storage/delivery backends, Celery concurrency, smoke test limits, logging format.

#### `configs/logging.py` (49 lines)
Structured logging via structlog. Supports JSON (production) or console (dev) output formats.

#### `configs/pricing.py` (78 lines)
Hard-coded pricing table for ~30+ AI models (Claude, GPT, Gemini, Flux, Stable Diffusion) and cost computation functions (`compute_text_cost`, `compute_image_cost`).

---

### 2. API Layer (FastAPI)

#### `api/app.py` (85 lines)
Creates the FastAPI app with CORS, auth middleware, rate limiting, and 16 route modules:
- health, generation, jobs, templates, products, auth, users, projects, assets, analytics, admin, notifications, dashboard, events, verification, consumption, google_drive

#### `api/middleware/auth.py` (78 lines)
Two middleware classes:
- `AuthMiddleware` — checks `X-API-Key` header or `Authorization: Bearer` token (skip for docs, health, SSE, verification)
- `RateLimitMiddleware` — in-memory per-IP rate limiter

#### `api/dependencies.py` (35 lines)
FastAPI dependency injection: `verify_api_key`, `get_job_repo`, `get_asset_repo`.

#### API Routes

- **`api/routes/health.py`** — `GET /health` and `GET /health/ready` (checks DB)
- **`api/routes/generation.py`** — `POST /generate` (single image job), `POST /generate/bulk` (batch of jobs). Creates DB records, dispatches Celery tasks.
- **`api/routes/jobs.py`** — Full CRUD for jobs: list (with status/project filters), get, status, cancel, retry, bulk progress, stats
- **`api/routes/templates.py`** — List/get prompt templates (product_mockup, lifestyle, blog_thumbnail, etc.)
- **`api/routes/products.py`** — Upload Excel/CSV with product URLs, scrape images from each URL, submit AI generation (auto mode or manual)
- **`api/routes/verification.py`** — Smoke test (end-to-end pipeline verification), dry run (cost preview), health checks, readiness check
- **`api/routes/consumption.py`** — Fetches live pricing from Gemini & OpenRouter APIs, estimates costs
- **`api/routes/dashboard.py`** — Stats (total/queued/processing/completed/failed counts), system status, queue info
- **`api/routes/events.py`** — Server-Sent Events endpoint via Redis pub/sub for real-time job updates
- **`api/routes/notifications.py`** — List/mark-read notifications
- **`api/routes/users.py`** — API key management (list, create, delete)
- **`api/routes/projects.py`** — Project CRUD + product listing per project
- **`api/routes/google_drive.py`** — OAuth flow for Google Drive, upload runs, list uploads

#### `api/schemas/generation.py` — Pydantic models: `GenerationRequest`, `BulkGenerationRequest`, `ImageGenerationResponse`, `BulkGenerationResponse`
#### `api/schemas/job.py` — Pydantic models: `JobResponse`, `JobListResponse`, `JobStatusResponse`, `BatchJobResponse`

---

### 3. Worker Layer (Celery)

#### `workers/celery_app.py` (30 lines)
Celery app config: broker/backend from settings, includes tasks (generation, delivery, product), JSON serializer, 10-min hard limit, 9-min soft limit, prefetch=1.

#### `workers/worker.py` (8 lines)
Celery entry point: `celery -A workers.worker worker --loglevel=info`

#### Tasks

##### `tasks/generation.py` (573 lines)
Main task file. Contains:
- `process_generation` — Single image generation pipeline: Claude prompt generation/enhancement → Nano Banana image generation → LocalStorage → Delivery backends. Includes retry logic with exponential backoff.
- `process_bulk_generation` — Batch processing from uploaded products: reads `products.json`, generates images per product (auto-detect count from scraped images or fixed count), creates child jobs, tracks progress.
- `process_smoke_test` — Minimal end-to-end test: creates sample product, calls Claude (1 text call), generates 1 tiny image, stores, delivers.

All tasks use `run_async()` to bridge Celery's sync execution with async code. Has a hacky engine lifecycle management (resets global `_engine`/`_smaker` per call).

##### `tasks/delivery.py` (74 lines)
- `deliver_asset` — Delivers a single asset to all configured delivery backends (local/S3/webhook). Retries 3x with 60s delay.

##### `tasks/product.py` (262 lines)
- `process_single_product` — Full product localization pipeline: extract URL → analyze images → AI reposition → generate premium images → write output files (product-data.json, product-copy.json, generation-log.json)
- `process_product_batch` — Reads Excel/CSV, dispatches each product URL as a child job, tracks batch progress

---

### 4. Services

#### Claude (`services/claude/`)

- **`client.py`** (133 lines) — `ClaudeClient` wrapping Anthropic API. Methods: `generate_text`, `generate_prompt` (creates prompt from subject/style/mood/context), `enhance_prompt`, `optimize_for_platform`. Uses httpx with tenacity retry (3 attempts, exp backoff).
- **`enhancer.py`** (56 lines) — `PromptEnhancer` orchestrates template-based generation + enhancement pipeline.
- **`templates.py`** (289 lines) — Dataclass `PromptTemplate` with 10 templates across 3 categories:
  - **E-commerce:** `product_mockup`, `lifestyle`, `marketing_banner`
  - **Content:** `blog_thumbnail`, `instagram_creative`, `linkedin_creative`, `youtube_thumbnail`
  - **SaaS:** `landing_page`, `feature_illustration`, `marketing_asset`

#### Nano Banana (`services/nano_banana/`)

- **`models.py`** (28 lines) — `GenerationRequest` (prompt, dimensions, model, seed, steps, guidance) and `GenerationResult` (image bytes + metadata)
- **`client.py`** (296 lines) — Provider-isolated architecture:
  - `BaseImageProvider` ABC
  - `ReplicateProvider` — Polls predictions, downloads results
  - `StabilityAIProvider` — Uses REST API with base64 results
  - `OpenAIProvider` — DALL-E 3 wrapper (1 image/call limit)
  - `NanoBananaClient` — Facade that selects provider based on settings

#### Storage (`services/storage/`)

- **`base.py`** — `StorageBackend` ABC with `store`/`retrieve`/`delete`/`exists`. `StorageResult` dataclass.
- **`local.py`** — Local filesystem storage using `aiofiles`. `get_storage_backend()` factory.
- **`s3.py`** — S3-compatible storage via boto3.
- **`google_drive.py`** (192 lines) — `GoogleDriveManager` with OAuth2 flow, folder creation, file upload, public link sharing. Uses `google-auth-oauthlib`, `google-api-python-client`.

#### Delivery (`services/delivery/`)

- **`base.py`** — `DeliveryBackend` ABC with `deliver`/`check_health`. `DeliveryResult` dataclass.
- **`local.py`** — Copies to local delivery folder. `create_delivery_backends()` factory reads comma-separated config.
- **`s3.py`** — Uploads to S3 bucket.
- **`webhook.py`** — POSTs base64-encoded image + metadata to configured URL with HMAC-SHA256 signature.

#### Extractors (`services/extractor/`)

- **`product_extractor.py`** — Chain-of-responsibility: tries AlibabaParser → AliExpressParser → GenericParser
- **`excel_reader.py`** — Reads .xlsx (openpyxl) and .csv files, normalizes headers (URL/Link → product_url, Title → product_title, etc.)
- **Parsers (`services/extractor/parsers/`):**
  - `base.py` — `ExtractedProduct` dataclass + `BaseParser` ABC
  - `alibaba.py` — Regex-based URL detection, BeautifulSoup scraping for title/description/price/images
  - `aliexpress.py` — Similar + attempts JSON-LD extraction
  - `generic.py` — Fallback using OG meta tags

#### Repositioning (`services/repositioning/`)

- **`engine.py`** (158 lines) — `ProductRepositioningEngine`: 4-step Claude pipeline:
  1. `_analyze_product` — extracts features/materials/design/angles as JSON
  2. `_create_positioning` — generates premium European brand concept (never mention China/suppliers)
  3. `_generate_marketing_copy` — creates titles, descriptions, SEO keywords, selling points
  4. `_generate_image_briefs` — generates prompts for hero/lifestyle/detail/banner images

#### Image Analysis (`services/image_analysis/`)

- **`analyzer.py`** (131 lines) — `ImageAnalyzer`: extracts color palettes via quantization + Claude vision analysis for product type, characteristics, quality scoring, premium suggestions

#### Translation (`services/translation/`)

- **`service.py`** (42 lines) — `TranslationService`: `translate` (target language) and `detect_and_translate` (auto-detect → English) using Claude

#### Product Scraper (`services/product_scraper/`)

- **`scraper.py`** (179 lines) — `ProductScraper`: fetches product pages, extracts image URLs (alicdn patterns, BeautifulSoup parsing), downloads up to 10 images. Special handling for 1688.com (mobile page, offer ID extraction).

#### OpenRouter (`services/openrouter/`)

- **`client.py`** (154 lines) — `OpenRouterClient`: tries 5 image models in sequence (`gemini-2.5-flash-image`, `gemini-3.1-flash-image-preview`, `gemini-3-pro-image-preview`, `flux.2-pro`, `gpt-5.4-image-2`). Handles rate limiting (429 retry), supports aspect ratio config, reference image upload.

#### Verification (`services/verification/`)

- **`smoke_test.py`** (312 lines) — `SmokeTestEngine`: runs system checks → DB → Redis → queues Celery worker task → polls for completion. `SmokeTest`/`SmokeTestResult`/`SmokeTestStep` dataclasses.
- **`dry_run.py`** — `DryRunEngine`: estimates cost/duration without consuming credits (6 steps for smoke test, 10 for full job)
- **`cost_controller.py`** — `CostController`: enforces hard budgets (text calls, image calls, retries, total cost). `BudgetExceededError`.
- **`system_checks.py`** — `SystemChecker`: validates all 8 components (API, DB, Redis, Worker, Storage, Delivery, AI Provider, Queue) with 3.5s timeouts each.

#### Other Services

- **`event_bus.py`** — Simple Redis pub/sub for job status events (`publish` function, `events` channel)
- **`notifications.py`** (172 lines) — `NotificationService`: Redis-based notification storage with 24h TTL, pagination (1000 items), read tracking. `NotificationEvent` pydantic model with severity levels.
- **`consumption_analysis.py`** (207 lines) — Live cost analysis: fetches Gemini pricing from `ai.google.dev/pricing`, fetches OpenRouter models from API, provides POST templates for Gemini/NanoBanana/AI Studio, estimates costs across all models

---

### 5. Database Layer

#### `database/session.py` (73 lines)
Async SQLAlchemy engine with retry (3 attempts on startup), `async_session` factory, `init_db`/`close_db` lifecycle, `get_session` FastAPI dependency.

#### `database/repository.py` (119 lines)
- `JobRepository` — CRUD for jobs: create, get, update, update_status, list (with filters), list_by_parent, get_stats
- `AssetRepository` — CRUD for assets: create, get, list_by_job, update, delete

#### SQLAlchemy Models (`database/models/`)

- **`job.py`** — `Job` table: id, type, status (indexed), prompt, template, dimensions, parameters (JSON), meta (JSON), project_name, error_message, retry tracking, timestamps, parent_job_id, is_bulk_item. Has `assets` relationship.
- **`asset.py`** — `Asset` table: id, job_id (FK → jobs), filename, file_path, dimensions, mime_type, delivery_status, meta (JSON)
- **`user.py`** — `User` (name, email, password_hash, role), `ApiKey` (user_id, name, key), `Project` (user_id, name, status, counters), `Notification` (user_id, type, title, message, read status)

---

### 6. Domain Models

#### `models/enums.py`
- `JobStatus` — 12 states: pending → queued → processing → enhancing_prompt → generating → storing → delivering → completed/failed/partially_completed/cancelled/retrying
- `JobType` — single, bulk, scheduled
- `ImageProvider` — replicate, stabilityai, openai
- `TemplateCategory` — 11 categories
- `DeliveryStatus` — pending, delivering, delivered, failed

#### `models/job.py` — `JobModel` pydantic with all job fields
#### `models/asset.py` — `AssetModel` pydantic with all asset fields

---

### 7. Standalone Scripts

#### `validate_deployment.py` (195 lines)
Pre-deployment validation: checks .env exists, required keys present, Docker installed, DB/Redis config valid, API keys configured, SSL warnings, storage config consistency.

#### `test_1688.py` (59 lines)
One-shot script testing 5 different 1688 API approaches: mobile page, JSONP API, ajax API, offer detail query, offer API. Prints status codes and found image URLs.

#### `test_scraper.py` (12 lines)
Quick smoke test for ProductScraper on a 1688 URL.

---

### 8. Tests (`tests/`)

| Test File | What It Tests |
|-----------|---------------|
| `conftest.py` | Fixtures: test_settings, mock_claude, mock_nano_banana, mock_storage, mock_delivery, async_client |
| `test_api.py` | Health check, unauthorized access, templates CRUD, generate (prompt/subject), bulk generate, job lookup, stats |
| `test_models.py` | Enum values, JobModel defaults, AssetModel defaults |
| `test_claude.py` | generate_prompt, enhance_prompt, translation, template listing, product repositioning |
| `test_extractor.py` | CSV reader, header normalization, Alibaba/AliExpress/Generic parser detection, ProductExtractor parser selection, ImageAnalyzer |
| `test_storage.py` | LocalStorage store/retrieve/delete/exists, LocalDelivery, backend selection, delivery creation |
| `test_nano_banana.py` | GenerationRequest/Result models, provider selection, mock generation |
| `test_verification.py` | CostController budgets/summary, DryRun previews, SystemChecker, SmokeTestStep/Result models, SmokeTestEngine creation, cost limits, API endpoint shape |

---

### 9. Docker & Deployment

#### `docker-compose.yml` (176 lines)
5 services: postgres (16-alpine), redis (7-alpine), api (FastAPI), worker (Celery), dashboard (Next.js). Optional flower (monitoring). Healthchecks, resource limits (2G DB, 1G Redis/API, 2G Worker, 512M Dashboard). Shared outputs volume.

#### Dockerfiles
- `Dockerfile.base` — Python 3.12-slim + system deps + base requirements
- `Dockerfile.api` — Uvicorn serving FastAPI on port 8000
- `Dockerfile.worker` — Celery worker with concurrency=4
- `Dockerfile.dashboard` — Multi-stage Next.js build (deps → builder → runner)

---

### 10. Dashboard (`dashboard/`)

Next.js 15 app with:
- Radix UI components (accordion, dialog, dropdown, tabs, toast, etc.)
- Tailwind CSS + shadcn/ui style (class-variance-authority, tailwind-merge)
- React Query for data fetching
- Zustand for state management
- Recharts for charts
- React Dropzone for file uploads
- react-hook-form + zod for form validation
- `date-fns` for dates
- `lucide-react` for icons
- Dark/light theme support (`next-themes`)

---

### 11. Known Issues / Dead / Redundant Features

1. **Dead routes referenced in `app.py` but files may not exist:** `auth`, `assets`, `analytics`, `admin` routers are imported but their route files were never created (or are empty). The app will crash on import if these files don't exist.

2. **`run_async()` in tasks/generation.py** — Resets global engine/smaker on every call. Fragile design — if an engine is mid-query when reset, it causes connection leaks.

3. **`run_async()` in tasks/delivery.py and tasks/product.py** — Different implementation (creates new event loop, doesn't save/restore engine). Inconsistent with generation.py.

4. **`GoogleDriveManager`** — Requires google API client libraries but they're not in pyproject.toml. The `upload_to_drive` endpoint in `google_drive.py` is a stub that returns fake data. The `list_uploads` endpoint returns an empty list with TODO comment.

5. **`NotificationService` (notifications.py)** — Duplicates the `Notification` DB model-based notifications route (`api/routes/notifications.py`). The service uses Redis pub/sub + Redis storage, while the API routes use PostgreSQL via SQLAlchemy. Both coexist as separate notification systems.

6. **`dashboard/routes/dashboard.py`** — Hardcoded `"healthy"` status for API, Worker, Queue, etc. in `/dashboard/status`.

7. **`configs/pricing.py`** — Model names hardcoded. `get_model_pricing()` uses fuzzy substring matching which can return wrong pricing. `compute_image_cost_from_pixels()` uses hardcoded per-provider rates that are unrealistic.

8. **`api/routes/products.py`** — The `/products/upload` endpoint should return a batch_id but the frontend flow expects a job_id. The `/products/generate` endpoint creates a bulk job but there's no way to track individual product status within the batch.

9. **`services/extractor`** — The Alibaba and AliExpress parsers do basic scraping that is likely to break as these sites have anti-bot measures. The 1688 scraper in `product_scraper/scraper.py` has 5 different approaches tested in `test_1688.py`, none guaranteed to work reliably.

10. **Duplicated functionality:** `ProductScraper` (scrapes images from URLs) and `ProductExtractor` (extracts product data from URLs) are similar but separate services. The `/products/upload` endpoint uses `ProductScraper`, while the product pipeline (`tasks/product.py`) uses `ProductExtractor` + `ImageAnalyzer`.

11. **`services/verification/system_checks.py`** — `check_worker()` tries `GET celery:workers` which is not a standard Redis command for Celery monitoring. It will raise an error.

12. **`.env` file** — Excluded from git (in `.gitignore`) but `validate_deployment.py` and `settings.py` expect it to exist.

13. **Missing `gen_request.json`** — A JSON file exists at root with sample generation request, but no code references it. Appears to be documentation artifact.

14. **`smoke_test_mode` setting** — Referenced in settings but never actually checked in code paths. The smoke test has its own `CostController` instead.

15. **The dashboard routes reference `Job.type != "bulk"` filter** — This is problematic because `Job.type` is stored as SQLAlchemy column but the filter is done in Python with `hasattr` which will always be True.

16. **`services/notification.py`** uses `model_dump_json()` (Pydantic v2) but the NotificationEvent has `created_at: datetime = None` as default which will cause validation errors.

17. **`workers/worker.py`** calls `celery_app.start()` in `__main__` block but the correct entry point is usually `celery -A workers.worker worker`. The `__main__` block is misleading.
