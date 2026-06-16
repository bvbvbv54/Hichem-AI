# ImageFactory - Full Pipeline Architecture & Operational Guide

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER INTERFACE LAYER                         │
├─────────────────────────────────────────────────────────────────┤
│  Next.js Dashboard (React 18)                                   │
│  - Project Management                                            │
│  - Real-time Job Monitoring (SSE)                              │
│  - Asset Gallery                                                │
│  - Analytics & Reporting                                        │
└──────────────┬──────────────────────────────────────────────────┘
               │ HTTP/REST (Port 3000)
┌──────────────▼──────────────────────────────────────────────────┐
│                    API GATEWAY LAYER                             │
├─────────────────────────────────────────────────────────────────┤
│  FastAPI + Uvicorn (Port 8000)                                  │
│  - Authentication & Rate Limiting                               │
│  - Request Validation & Schema Management                       │
│  - API Key Management                                           │
│  - CORS & Security Headers                                      │
│                                                                  │
│  Core Routes:                                                    │
│  ├─ /auth - User authentication                                │
│  ├─ /generation - Image generation endpoints                   │
│  ├─ /jobs - Job lifecycle management                           │
│  ├─ /projects - Project CRUD operations                        │
│  ├─ /assets - Generated asset management                       │
│  ├─ /products - Product localization                           │
│  ├─ /dashboard - Real-time system stats                        │
│  ├─ /health - System health checks                             │
│  └─ /events - Server-Sent Events (real-time updates)           │
└──────┬─────────────┬──────────────────┬────────────────────────┘
       │             │                  │
       │ Task Queue  │ Real-time         │ Data Store
       │ (Celery)    │ Updates (SSE)     │ (PostgreSQL/Redis)
       │             │                  │
┌──────▼─────────────▼──────────────────▼────────────────────────┐
│              MESSAGE BROKER & CACHING LAYER                     │
├─────────────────────────────────────────────────────────────────┤
│  Redis (Port 6379)                                              │
│  - Celery Broker (Queue: DB 1)                                 │
│  - Result Backend (DB 2)                                       │
│  - Session Cache (DB 0)                                        │
└──────┬──────────────────────────────────────────────────────────┘
       │ Task Distribution
┌──────▼──────────────────────────────────────────────────────────┐
│                    WORKER LAYER (Celery)                        │
├─────────────────────────────────────────────────────────────────┤
│  Image Generation Worker                                        │
│                                                                  │
│  Task Pipeline:                                                 │
│  1. Generate Prompt (Claude AI)                                │
│  2. Create Image (Nano Banana - Replicate/OpenAI)             │
│  3. Process Assets (Resize, Optimize)                          │
│  4. Store Generated Image                                       │
│  5. Update Job Status                                           │
│  6. Trigger Delivery                                            │
│                                                                  │
│  Additional Workers:                                            │
│  - Product Extractor (URL → Product Data)                      │
│  - Product Repositioning (Transform for EU market)             │
│  - Delivery Manager (Local FS / S3 / Webhook)                  │
└──────┬──────────────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────────┐
│             EXTERNAL SERVICE INTEGRATIONS                        │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌──────────────────┐    ┌────────────┐ │
│  │  Claude API     │    │  Image Provider  │    │  Storage   │ │
│  │  (Anthropic)    │    │  (Nano Banana)   │    │  Backend   │ │
│  │                 │    │                  │    │            │ │
│  │ - Prompt Gen    │    │ - Replicate      │    │ - Local    │ │
│  │ - Enhancement   │    │ - OpenAI DALL-E │    │ - S3       │ │
│  │ - Translation   │    │ - StabilityAI    │    │ - Custom   │ │
│  └─────────────────┘    └──────────────────┘    └────────────┘ │
│                                                                  │
│  ┌─────────────────────────────┐    ┌──────────────────────┐   │
│  │  Product Scrapers           │    │  Delivery Backends   │   │
│  │                             │    │                      │   │
│  │ - Alibaba / AliExpress      │    │ - Local Filesystem   │   │
│  │ - Generic URL Extraction    │    │ - S3-compatible      │   │
│  │ - Metadata Enrichment       │    │ - Webhook Delivery   │   │
│  └─────────────────────────────┘    └──────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────────┐
│              DATA PERSISTENCE LAYER                              │
├─────────────────────────────────────────────────────────────────┤
│  PostgreSQL 16 (Port 5432)                                      │
│                                                                  │
│  Tables:                                                         │
│  - users (Authentication & API Keys)                           │
│  - projects (User Projects)                                     │
│  - jobs (Generation Jobs with Status)                          │
│  - assets (Generated Images Metadata)                          │
│  - notifications (Real-time User Notifications)                │
│  - job_logs (Audit Trail)                                      │
└─────────────────────────────────────────────────────────────────┘
```

## 2. Request Flow - Image Generation Pipeline

### Complete Request Lifecycle

```
1. USER INITIATES REQUEST
   ├─ Dashboard Form Input or API POST /generation
   ├─ Payload: { subject, template, num_images, project, use_claude }
   └─ Authentication: X-API-Key or Bearer Token

2. API VALIDATION & RATE LIMITING
   ├─ Check API Key (Middleware)
   ├─ Validate Request Schema
   ├─ Apply Rate Limiting (100 req/min default)
   ├─ Create Job Record (status: "pending")
   └─ Return Job ID to Client

3. ENQUEUE IN CELERY
   ├─ Add Task to Redis Queue
   ├─ Set Task Timeout (600s soft, 540s hard)
   ├─ Trigger SSE Event: "job_created"
   └─ Return Immediately to Client

4. WORKER PROCESSES TASK
   └─ Step A: GENERATE PROMPT (if use_claude=true)
       ├─ Call Claude API with Template + Subject
       ├─ Template Example: "Generate product mockup for {subject}"
       ├─ Receive Enhanced Prompt
       ├─ Store in Job Metadata
       └─ Retry 3x with exponential backoff on failure

   └─ Step B: GENERATE IMAGE (Nano Banana Provider)
       ├─ Select Provider (Replicate/OpenAI/StabilityAI)
       ├─ Call Provider API with Prompt
       ├─ Poll for Completion (every 2s)
       ├─ Store Image URL
       ├─ Download Image to Local Cache
       └─ Retry 3x on Provider Failure

   └─ Step C: PROCESS & STORE
       ├─ Validate Image (Format, Size)
       ├─ Generate Thumbnails (256x256, 512x512)
       ├─ Create Asset Records in DB
       ├─ Upload to Storage Backend (Local/S3)
       └─ Update Job Status: "completed"

   └─ Step D: TRIGGER DELIVERY
       ├─ Check Delivery Backend Config
       ├─ Move to Output Location (S3 / Webhook)
       ├─ Send Delivery Webhook (if configured)
       ├─ Record Delivery Status
       └─ Emit SSE Event: "job_complete"

5. CLIENT RECEIVES UPDATES
   ├─ Real-time via SSE: job_created → job_processing → job_complete
   ├─ Poll API: GET /jobs/{id} for status
   ├─ Get Assets: GET /jobs/{id}/assets
   └─ Download/View Generated Images

6. FAILURE HANDLING
   ├─ Max Retries: 3 per task
   ├─ Backoff: 30s exponential delay
   ├─ On Max Retries: status = "failed"
   ├─ Emit SSE: "job_failed"
   ├─ Record Error in Logs
   └─ User can Manually Retry via API: POST /jobs/{id}/retry
```

## 3. Database Schema

```sql
-- Users & Authentication
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR UNIQUE NOT NULL,
    password_hash VARCHAR NOT NULL,
    api_key VARCHAR UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- API Keys Management
CREATE TABLE api_keys (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    name VARCHAR NOT NULL,
    key VARCHAR UNIQUE NOT NULL,
    last_used TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Projects (Organizational Unit)
CREATE TABLE projects (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    name VARCHAR NOT NULL,
    config JSON, -- Storage backend, delivery settings
    created_at TIMESTAMP DEFAULT NOW()
);

-- Jobs (Image Generation Tasks)
CREATE TABLE jobs (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    status VARCHAR DEFAULT 'pending', -- pending, processing, completed, failed
    request_payload JSON NOT NULL,
    result JSON, -- Image URLs, metadata
    error_message VARCHAR,
    retries INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Assets (Generated Images)
CREATE TABLE assets (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id),
    image_url VARCHAR NOT NULL,
    thumbnail_url VARCHAR,
    metadata JSON, -- Dimensions, size, hash
    created_at TIMESTAMP DEFAULT NOW()
);

-- Notifications (Real-time User Alerts)
CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    type VARCHAR, -- job_complete, job_failed, delivery_complete
    payload JSON NOT NULL,
    read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Audit Log
CREATE TABLE job_logs (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id),
    event_type VARCHAR, -- created, processing, completed, failed, retry
    details JSON,
    timestamp TIMESTAMP DEFAULT NOW()
);
```

## 4. Configuration & Environment Variables

### Critical Configuration

```env
# ───── IMAGE GENERATION ─────
# Must be set for image generation to work
IMAGE_PROVIDER=replicate          # or openai, stabilityai
IMAGE_PROVIDER_API_KEY=r8_***     # Nano Banana API key
REPLICATE_API_KEY=r8_***          # For Replicate provider
OPENAI_API_KEY=sk-***             # For OpenAI DALL-E
STABILITYAI_API_KEY=sk-***        # For StabilityAI

# ───── PROMPT GENERATION ─────
# Must be set for prompt enhancement
CLAUDE_API_KEY=sk-ant-***         # Anthropic Claude
CLAUDE_MODEL=claude-sonnet-4-20250514

# ───── INFRASTRUCTURE ─────
DATABASE_URL=postgresql+asyncpg://imagefactory:imagefactory@postgres:5432/imagefactory
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# ───── SECURITY ─────
SECRET_KEY=<random-32-char-string>  # For FastAPI
API_KEY=<custom-api-key>            # For Dashboard/API auth

# ───── STORAGE & DELIVERY ─────
STORAGE_BACKEND=local              # or s3
DELIVERY_BACKENDS=local            # or s3, webhook
STORAGE_LOCAL_PATH=/app/outputs
DELIVERY_LOCAL_PATH=/app/outputs
```

### Performance Tuning

```env
# API Performance
API_WORKERS=4                       # Increase for high traffic
DATABASE_POOL_SIZE=20               # Connection pool size
DATABASE_MAX_OVERFLOW=40            # Additional connections

# Worker Performance
CELERY_WORKER_CONCURRENCY=4         # Parallel task processing
IMAGE_PROVIDER_TIMEOUT=120          # Provider call timeout
IMAGE_PROVIDER_MAX_RETRIES=3        # Retry attempts

# Rate Limiting
API_RATE_LIMIT=100                  # Requests per period
API_RATE_LIMIT_PERIOD=60            # Period in seconds
```

## 5. Operational Workflows

### Workflow A: Single Image Generation

```
User Request
    ↓
API: POST /generation
    ├─ Validate Payload
    ├─ Create Job (pending)
    ├─ Enqueue Celery Task
    └─ Return Job ID
    ↓
Worker: process_generation_task
    ├─ Generate Prompt (Claude)
    ├─ Call Image Provider
    ├─ Poll for Completion
    ├─ Download & Process Image
    ├─ Store in DB & S3
    ├─ Mark Job Complete
    └─ Emit SSE Event
    ↓
Dashboard: Real-time Updates
    ├─ Receive SSE: job_created
    ├─ Show Loading State
    ├─ Receive SSE: job_complete
    ├─ Display Generated Image
    └─ Allow Download/Share
```

### Workflow B: Bulk Product Generation

```
User Uploads XLSX
    ↓
API: POST /products/upload
    ├─ Parse Spreadsheet
    ├─ Create Parent Job
    ├─ Enqueue Sub-tasks (one per row)
    └─ Return Parent Job ID
    ↓
Workers: Parallel Processing
    ├─ Extract Product Data (if URL)
    ├─ Generate Prompt for Each Product
    ├─ Generate Image
    ├─ Store Result
    └─ Update Parent Progress
    ↓
Dashboard: Progress Tracking
    ├─ Show 15/100 products complete
    ├─ Update in real-time
    ├─ Export results when done
    └─ Allow Retry for Failed Items
```

### Workflow C: Product Repositioning (EU Market)

```
User Submits Product URL
    ↓
API: POST /products/url
    ├─ Extract Product Metadata
    ├─ Translate to EU Specifications
    ├─ Generate Product Images
    ├─ Create EU-friendly Description
    └─ Return Repositioned Product
    ↓
Services Used:
    ├─ Product Scraper (URL → Data)
    ├─ Claude (Repositioning & Translation)
    ├─ Image Provider (Mockups)
    └─ Translation API (Multilingual)
    ↓
Output:
    ├─ EU-compliant description
    ├─ Multiple product images
    ├─ Localized metadata
    └─ Ready for EU marketplace
```

## 6. Monitoring & Observability

### Health Checks

```bash
# API Health
GET /api/v1/health
# Response: {"status": "healthy", "timestamp": "2024-01-15T10:30:00Z"}

# Readiness Check (includes DB)
GET /api/v1/health/ready
# Response: {"status": "ready", "database": "connected", "redis": "connected"}

# Dashboard Status
GET /api/v1/dashboard/status
# Response: System stats, queue length, active workers
```

### Key Metrics to Monitor

```
API Metrics:
- Request latency (p50, p95, p99)
- Error rate (4xx, 5xx)
- Requests per second
- Auth failures

Worker Metrics:
- Task queue depth
- Task success rate
- Task latency (p50, p95, p99)
- Active workers
- Task retry rate

Database Metrics:
- Connection pool usage
- Query latency
- Transaction count
- Disk space usage

System Metrics:
- CPU utilization
- Memory usage
- Disk I/O
- Network I/O
```

### Logging Strategy

```
Structured JSON Logging:

{
  "timestamp": "2024-01-15T10:30:00.123Z",
  "level": "INFO",
  "module": "workers.generation",
  "event": "image_generation_started",
  "job_id": "uuid-123",
  "user_id": "user-456",
  "provider": "replicate",
  "duration_ms": 45000,
  "status": "success",
  "trace_id": "trace-789"
}

Log Levels:
- DEBUG: Detailed diagnostic info
- INFO: Workflow milestones
- WARNING: Recoverable issues
- ERROR: Task failures
- CRITICAL: System failures
```

## 7. Error Handling & Recovery

### Common Failure Scenarios

| Scenario | Cause | Recovery |
|----------|-------|----------|
| Image Generation Timeout | Provider slow | Retry (3x), fallback provider |
| Database Connection Error | Network issue | Reconnect, exponential backoff |
| Out of Memory | Large batch | Split into smaller batches |
| API Rate Limit | Quota exceeded | Backoff, queue retry |
| Storage Write Failure | Disk full | Clean old files, alert admin |

### Retry Strategy

```python
# Task Configuration in Celery
@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_kwargs={'countdown': 2 ** self.request.retries}
)
def process_generation_task(self, job_id):
    try:
        # Generate image
        pass
    except (ConnectionError, TimeoutError) as exc:
        # Exponential backoff: 2s, 4s, 8s
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
```

## 8. Deployment Checklist

- [ ] All required API keys configured in `.env`
- [ ] Database URL points to production PostgreSQL
- [ ] Redis URL points to production Redis instance
- [ ] Storage backend configured (S3 or local with backups)
- [ ] SSL certificate configured in reverse proxy
- [ ] API rate limiting configured appropriately
- [ ] Database backups scheduled (hourly/daily)
- [ ] Monitoring and alerting set up
- [ ] Log aggregation configured
- [ ] Deployment validation script passed
- [ ] Load testing completed
- [ ] Rollback plan documented
- [ ] Team trained on operations

## 9. Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| API Response (p95) | <200ms | Excluding generation time |
| Image Generation | 30-90s | Provider dependent |
| Worker Task Latency | <5s | Queue to processing |
| Database Query (p95) | <50ms | With proper indexes |
| Dashboard Load Time | <2s | First paint |
| Job Completion Rate | >99% | Auto-retries included |

## 10. Next Steps

1. **Run Deployment Validation**
   ```bash
   python validate_deployment.py
   ```

2. **Start Infrastructure**
   ```bash
   docker-compose up -d
   ```

3. **Verify Health**
   ```bash
   curl http://localhost:8000/api/v1/health/ready
   ```

4. **Test Generation**
   - Create account in dashboard (http://localhost:3000)
   - Submit test generation request
   - Monitor worker logs for task processing
   - Verify image appears in results

5. **Monitor in Production**
   - Set up Prometheus for metrics
   - Configure ELK Stack for logs
   - Set up Grafana dashboards
   - Configure alerting rules

## Support & Documentation

- **API Documentation**: http://localhost:8000/docs (Swagger UI)
- **Deployment Guide**: See DEPLOYMENT.md
- **Architecture Diagrams**: See images/ folder
- **Configuration Reference**: .env.example

---

**Status**: ✅ Ready for Production Deployment
**Last Updated**: 2024-01-15
**Version**: 1.0.0
