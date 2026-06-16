# ImageFactory Deployment Guide

## Pre-Deployment Checklist

### 1. Environment Configuration

```bash
cp .env.example .env
```

Edit `.env` and configure the following **REQUIRED** variables:

| Variable | Value | Purpose |
|----------|-------|---------|
| **CLAUDE_API_KEY** | `sk-ant-...` | Prompt generation via Claude API |
| **IMAGE_PROVIDER** | `replicate` or `openai` or `stabilityai` | Image generation provider |
| **IMAGE_PROVIDER_API_KEY** / **REPLICATE_API_KEY** | Your API key | Nano Banana provider credentials |
| **SECRET_KEY** | Random 32+ char string | FastAPI security key |
| **API_KEY** | Custom API key | Dashboard/API authentication |

**Optional but Recommended:**
- `OPENROUTER_API_KEY` - Alternative image generation provider
- `STORAGE_BACKEND` - `s3` for cloud storage (default: `local`)
- `DELIVERY_BACKENDS` - `s3` or `webhook` for delivery

### 2. System Requirements

**Minimum (Single Server):**
- 4 vCPU / 8 GB RAM
- 50 GB disk space for images
- Docker + Docker Compose

**Recommended (Production):**
- 8 vCPU / 16 GB RAM
- 200+ GB disk space (NVMe recommended)
- PostgreSQL 16+
- Redis 7+
- Reverse proxy (Nginx/HAProxy) with SSL

### 3. Validation

```bash
# Run pre-deployment validation
python validate_deployment.py

# Expected output:
# ✓ PASS | Environment File
# ✓ PASS | Docker Setup
# ✓ PASS | Database Configuration
# ✓ PASS | Redis Configuration
# ✓ PASS | API Keys
# ✓ PASS | SSL/Security
# ✓ PASS | Storage Backend
```

## Deployment Steps

### Step 1: Start Infrastructure

```bash
# Start all services (will create volumes and network)
docker-compose up -d

# Verify services are healthy
docker-compose ps

# Check logs for errors
docker-compose logs -f api
docker-compose logs -f worker
```

### Step 2: Health Checks

```bash
# API health (should return 200)
curl http://localhost:8000/api/v1/health

# Database readiness (should return 200)
curl http://localhost:8000/api/v1/health/ready

# Dashboard should be accessible at:
# http://localhost:3000
```

### Step 3: Verify Database Setup

```bash
# Check database connection
docker-compose exec api python -c "
import asyncio
from database.session import init_db
asyncio.run(init_db())
print('✓ Database initialized')
"
```

### Step 4: Create API Key

```bash
# Generate secure API key
openssl rand -hex 32
```

Use this value for `API_KEY` in `.env` and for `X-API-Key` header in requests.

### Step 5: Test Basic Flow

```bash
# 1. Create a project via dashboard (http://localhost:3000)
# 2. Or use API:
curl -X POST http://localhost:8000/api/v1/generation/text \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Generate a professional product photo",
    "subject": "luxury leather handbag",
    "width": 1024,
    "height": 1024
  }'

# 3. Monitor job status
curl http://localhost:8000/api/v1/jobs \
  -H "X-API-Key: your-api-key"
```

## Monitoring & Maintenance

### Container Status

```bash
# Check all services
docker-compose ps

# View real-time logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f api
docker-compose logs -f worker
docker-compose logs -f postgres
```

### Resource Usage

```bash
# Monitor container resources
docker stats

# Check disk space
docker exec imagefactory-api du -sh /app/outputs
```

### Database Maintenance

```bash
# Backup database
docker-compose exec postgres pg_dump \
  -U imagefactory imagefactory > backup_$(date +%Y%m%d).sql

# Restore from backup
docker-compose exec -T postgres psql \
  -U imagefactory imagefactory < backup_20240101.sql
```

### Redis Cleanup

```bash
# Check Redis keys
docker-compose exec redis redis-cli INFO

# Clear all data (use with caution!)
docker-compose exec redis redis-cli FLUSHALL
```

## Production Deployment (Docker Swarm / Kubernetes)

### Docker Swarm

```bash
# Initialize swarm
docker swarm init

# Deploy stack
docker stack deploy -c docker-compose.yml imagefactory

# View services
docker service ls
docker service logs imagefactory_api
```

### Kubernetes

```bash
# Create namespace
kubectl create namespace imagefactory

# Create secrets from .env
kubectl create secret generic imagefactory-env \
  --from-env-file=.env \
  -n imagefactory

# Deploy (using custom K8s manifests)
kubectl apply -f k8s/ -n imagefactory
```

## Performance Tuning

### API Performance

```env
# Increase worker count for high traffic
API_WORKERS=8
DATABASE_POOL_SIZE=30
DATABASE_MAX_OVERFLOW=60
```

### Worker Performance

```env
# Adjust concurrency based on CPU cores
CELERY_WORKER_CONCURRENCY=8
# Increase for CPU-bound tasks, decrease for memory-bound
```

### Database Performance

```bash
# Create indexes for common queries
docker-compose exec postgres psql -U imagefactory imagefactory << EOF
CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_assets_job ON assets(job_id);
EOF
```

## Troubleshooting

### Dashboard White Screen

**Issue:** Dashboard loads but shows blank page

**Solutions:**
1. Check browser console for errors (F12)
2. Verify API is healthy: `curl http://localhost:8000/api/v1/health`
3. Check dashboard logs: `docker-compose logs dashboard`
4. Clear browser cache and reload
5. Verify CORS is enabled in API

### Image Generation Fails

**Issue:** Jobs stuck in `processing` state

**Solutions:**
1. Verify API keys are set correctly in `.env`
2. Check worker logs: `docker-compose logs worker`
3. Verify Redis connection: `docker-compose exec redis redis-cli ping`
4. Check image provider limits (API rate limits, quota)
5. Restart worker: `docker-compose restart worker`

### Database Connection Error

**Issue:** API won't start, "database connection refused"

**Solutions:**
1. Ensure PostgreSQL is healthy: `docker-compose ps postgres`
2. Check PostgreSQL logs: `docker-compose logs postgres`
3. Verify DATABASE_URL is correct
4. Wait for PostgreSQL to be ready (health check)
5. Restart: `docker-compose restart postgres api`

### Memory Issues

**Issue:** Containers crash with OOM (Out of Memory)

**Solutions:**
1. Increase container memory limits in `docker-compose.yml`
2. Reduce `CELERY_WORKER_CONCURRENCY`
3. Enable image compression in storage settings
4. Monitor memory: `docker stats`

## Rollback Procedure

```bash
# Stop current deployment
docker-compose down

# Restore previous version
git checkout <previous-tag>

# Restore database backup
docker-compose up -d postgres
docker-compose exec -T postgres psql \
  -U imagefactory imagefactory < backup_20240101.sql

# Start services
docker-compose up -d
```

## Security Checklist

- [ ] Change all default passwords (`SECRET_KEY`, `API_KEY`)
- [ ] Store `.env` securely (not in Git, use secrets management)
- [ ] Enable HTTPS with valid SSL certificate
- [ ] Configure firewall rules (only allow required ports)
- [ ] Enable database encryption at rest
- [ ] Set up log aggregation and monitoring
- [ ] Enable API rate limiting (configured by default)
- [ ] Regular security updates and patching

## Performance Metrics

**Expected Performance (4vCPU / 8GB setup):**
- API Response Time: 50-200ms (p95)
- Image Generation: 30-90 seconds (provider dependent)
- Database Queries: 5-50ms (p95)
- Worker Queue Throughput: 2-5 images/second

## Support & Logs

All logs are stored in:
- API: `docker-compose logs api`
- Worker: `docker-compose logs worker`
- Database: `docker-compose logs postgres`

Enable JSON logging for parsing:
```env
LOG_FORMAT=json
LOG_OUTPUT=stdout
```

## Next Steps

1. Set up monitoring (Prometheus + Grafana)
2. Configure log aggregation (ELK Stack or similar)
3. Set up CI/CD pipeline for automated deployments
4. Implement automated backups
5. Set up alerting for critical services
