# ImageFactory - System Setup & Troubleshooting Guide

## ✅ System Status - ALL SERVICES RUNNING

All containers are now up and healthy:

```
✓ imagefactory-api       (http://localhost:8000) - Healthy
✓ imagefactory-dashboard (http://localhost:3000) - Running
✓ imagefactory-worker    - Running (Celery task processing)
✓ imagefactory-postgres  - Healthy (Database)
✓ imagefactory-redis     - Healthy (Cache & Message Broker)
```

---

## 🔧 What Was Fixed

### Issue: Dashboard Stuck in Loading After Login
**Root Cause:** The SSE (Server-Sent Events) connection for real-time updates was blocking the dashboard from rendering, causing an infinite loading loop after successful authentication.

### Fixes Applied:

#### 1. **Enhanced SSE Connection Handler** (`dashboard/src/hooks/use-sse.ts`)
- ✅ Added graceful error handling and reconnection logic
- ✅ Implemented exponential backoff (max 5 reconnection attempts)
- ✅ Connection no longer blocks dashboard rendering
- ✅ Automatic reconnection with increasing delays (1s, 2s, 4s, 8s, 16s)

#### 2. **Improved Server Events Endpoint** (`api/routes/events.py`)
- ✅ Added robust Redis connection timeout handling (10 seconds)
- ✅ Proper message timeout handling (30 seconds)
- ✅ Heartbeat mechanism to keep connections alive
- ✅ Better error logging and cleanup
- ✅ Added `Transfer-Encoding: chunked` for proper streaming

#### 3. **Dashboard Layout Protection** (`dashboard/src/app/(dashboard)/layout.tsx`)
- ✅ Added hydration timeout (5 seconds) to prevent infinite loading
- ✅ SSE initialization is now non-blocking
- ✅ Dashboard loads even if SSE connection has issues
- ✅ Real-time updates are optional enhancements, not blockers

---

## 🚀 How to Use the System

### Access Points

| Service | URL | Purpose |
|---------|-----|---------|
| **Dashboard** | http://localhost:3000 | User interface for image generation, project management |
| **API** | http://localhost:8000 | REST API endpoints |
| **API Docs** | http://localhost:8000/docs | Swagger UI documentation |
| **Redis CLI** | localhost:6379 | Cache and job queue |
| **PostgreSQL** | localhost:5432 | Database (user: imagefactory, pass: imagefactory) |

### Default Login Credentials

```
Email:    hichem
Password: foufou
Role:     admin (full access)
```

### Login Flow

1. Navigate to **http://localhost:3000**
2. Click "Sign in"
3. Enter credentials:
   - Email: `hichem`
   - Password: `foufou`
4. ✅ Dashboard should now load immediately (no more infinite loading)
5. You'll see the dashboard with real-time stats and project management

---

## 📊 Dashboard Features

Once logged in, you have access to:

### Real-Time Monitoring
- **Progress Ring** - Overall completion percentage
- **Status Breakdown** - Completed, Processing, In Queue, Failed counts
- **System Readiness** - Component health checks

### Queue Management
- Active jobs count
- Waiting jobs in queue
- Failed jobs
- Worker activity status
- Estimated completion time

### Project Management
- Create and manage projects
- Upload product lists (Excel/CSV)
- Track generation jobs
- Download generated images

### System Insights
- AI credits usage
- Processing time averages
- Storage utilization
- Performance metrics

---

## 🔌 API Quick Reference

### Authentication
All requests require the `X-API-Key` header:
```bash
X-API-Key: dev-api-key-12345
```

### Key Endpoints

**Health Check**
```bash
GET /api/v1/health
```

**Login**
```bash
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "hichem",
  "password": "foufou"
}
```

**Get Dashboard Stats**
```bash
GET /api/v1/dashboard/stats
Authorization: Bearer <token>
```

**Generate Images**
```bash
POST /api/v1/generate
Authorization: Bearer <token>
Content-Type: application/json

{
  "subject": "red luxury handbag",
  "use_claude": true,
  "num_images": 1
}
```

---

## 🐳 Docker Management

### View All Containers
```bash
docker compose ps
```

### View Container Logs
```bash
# API logs
docker logs imagefactory-api --tail 100 -f

# Dashboard logs
docker logs imagefactory-dashboard --tail 100 -f

# Worker logs
docker logs imagefactory-worker --tail 100 -f
```

### Restart Services
```bash
# Restart all services
docker compose restart

# Restart specific service
docker compose restart dashboard
docker compose restart api
docker compose restart worker
```

### Rebuild and Deploy
```bash
# Rebuild all services
docker compose up -d --build

# Rebuild specific service
docker compose up -d --build dashboard
```

### Clean Up
```bash
# Stop all containers
docker compose down

# Remove volumes (WARNING: deletes data)
docker compose down -v
```

---

## 🔍 Troubleshooting

### Dashboard Still Loading?

1. **Check browser console** (F12 → Console tab)
   - Look for CORS errors or network failures

2. **Clear browser cache**
   - Hard refresh: `Ctrl+Shift+R` (Windows/Linux) or `Cmd+Shift+R` (Mac)
   - Or clear cookies for localhost:3000

3. **Check API is responding**
   ```bash
   # From another terminal
   $response = Invoke-WebRequest -Uri http://localhost:8000/api/v1/health -UseBasicParsing
   $response.Content  # Should show {"status": "ok"}
   ```

4. **Check Redis is accessible**
   ```bash
   docker exec imagefactory-redis redis-cli ping
   # Should return: PONG
   ```

5. **Restart the dashboard**
   ```bash
   docker compose restart dashboard
   ```

### API Returns 500 Error?

1. Check API logs:
   ```bash
   docker logs imagefactory-api --tail 50 -f
   ```

2. Verify database connection:
   ```bash
   docker logs imagefactory-postgres --tail 20 | grep ERROR
   ```

3. Restart API:
   ```bash
   docker compose restart api
   ```

### Real-Time Updates Not Working?

- This is **non-critical** - the dashboard will still function
- Real-time updates use SSE and will reconnect automatically
- Refresh the page to get latest data manually
- Check `/api/v1/events` endpoint is accessible

### Worker Not Processing Jobs?

1. Check worker logs:
   ```bash
   docker logs imagefactory-worker --tail 100 -f
   ```

2. Verify Redis connection:
   ```bash
   docker exec imagefactory-redis redis-cli
   > KEYS celery:*
   ```

3. Restart worker:
   ```bash
   docker compose restart worker
   ```

---

## 📝 Configuration

### Environment Variables
Located in `.env` file in the project root:

```bash
# API Configuration
API_PORT=8000
API_KEY=dev-api-key-12345
DEBUG=true

# Database
DATABASE_URL=postgresql+asyncpg://imagefactory:imagefactory@postgres:5432/imagefactory

# Redis
REDIS_URL=redis://redis:6379/0

# Claude API
CLAUDE_API_KEY=sk-ant-dev-key
CLAUDE_MODEL=claude-opus-4-20250805

# Image Provider
IMAGE_PROVIDER=replicate
IMAGE_PROVIDER_API_KEY=dev-key
```

### Update Configuration
1. Edit `.env` file
2. Restart services:
   ```bash
   docker compose restart api dashboard worker
   ```

---

## 🎯 Next Steps

1. **Test the API** - Use the Swagger UI at http://localhost:8000/docs
2. **Create a project** - Via dashboard or API
3. **Upload products** - Excel/CSV files with product data
4. **Generate images** - Watch real-time progress in dashboard
5. **Download results** - Access generated images via the UI

---

## 📚 Additional Resources

- **API Documentation**: http://localhost:8000/docs
- **Project README**: `README.md`
- **Architecture Guide**: `PIPELINE_ARCHITECTURE.md`
- **Deployment Info**: `DEPLOYMENT.md`

---

## ✨ Summary

Your ImageFactory system is now **fully operational** with:
- ✅ Authentication working smoothly
- ✅ Dashboard loading instantly after login
- ✅ Real-time updates with automatic reconnection
- ✅ All backend services healthy
- ✅ Database and cache ready for use

**Start using it now at http://localhost:3000** 🚀
