# 🚀 ImageFactory Quick Start - READY TO USE

## ✅ System Status: ALL GREEN

```
┌─────────────────────────────────────────────────────┐
│ Service              Port    Status    Access        │
├─────────────────────────────────────────────────────┤
│ Dashboard            3000    ✅ Up     http://localhost:3000
│ API                  8000    ✅ Up     http://localhost:8000
│ API Docs                     ✅ Up     http://localhost:8000/docs
│ PostgreSQL           5432    ✅ Up     Internal
│ Redis                6379    ✅ Up     Internal
│ Worker                       ✅ Up     Processing jobs
└─────────────────────────────────────────────────────┘
```

## 🔐 Login Now

**Dashboard:** http://localhost:3000

```
Email:    hichem
Password: foufou
```

## 🎯 What You Can Do

### 1. View Real-Time Dashboard
- Live statistics and metrics
- Processing queue status
- Storage utilization
- System health

### 2. Create Projects
- Organize your image generations
- Group related batches
- Track progress by project

### 3. Upload Products
- Excel/CSV format
- Batch processing
- Bulk image generation

### 4. Generate Images
- AI-powered prompt enhancement (Claude)
- Multiple image providers supported
- Real-time job tracking

### 5. Download Results
- Generated images
- Processing reports
- Export data

## ⚙️ Key Endpoints

```bash
# Health Check
GET http://localhost:8000/api/v1/health

# Login
POST http://localhost:8000/api/v1/auth/login
{
  "email": "hichem",
  "password": "foufou"
}

# Dashboard Stats
GET http://localhost:8000/api/v1/dashboard/stats

# Generate Image
POST http://localhost:8000/api/v1/generate
{
  "subject": "red luxury handbag",
  "use_claude": true,
  "num_images": 1
}
```

## 🔧 Common Commands

```bash
# View status
docker compose ps

# View logs
docker logs imagefactory-dashboard -f
docker logs imagefactory-api -f
docker logs imagefactory-worker -f

# Restart service
docker compose restart dashboard
docker compose restart api
docker compose restart worker

# Rebuild service
docker compose up -d --build dashboard
```

## 📋 What Was Fixed

**Before:** Dashboard stuck in loading after login ❌
**After:** Dashboard loads instantly, real-time updates work ✅

### 3 Key Fixes:
1. **SSE Auto-Reconnection** - Exponential backoff, non-blocking
2. **Timeout Protection** - Connection timeout, message timeout
3. **Layout Safety** - Hydration timeout, fallback rendering

## 🎓 Documentation

See detailed information in:
- `SYSTEM_SETUP_GUIDE.md` - Comprehensive setup & troubleshooting
- `FIX_SUMMARY.md` - Technical details of fixes
- `README.md` - Project overview
- `PIPELINE_ARCHITECTURE.md` - System architecture

## ❓ Troubleshooting

**Dashboard not loading?**
- Hard refresh: Ctrl+Shift+R
- Clear cookies
- Check browser console (F12)

**API returning errors?**
- Check logs: `docker logs imagefactory-api`
- Restart API: `docker compose restart api`

**Real-time updates not working?**
- Refresh the page
- This is optional - dashboard works without it
- Check if Redis is healthy: `docker compose ps redis`

## 🎉 You're All Set!

Your ImageFactory system is fully operational and ready to generate images with AI-powered prompts.

**Start here:** http://localhost:3000

---

*Last Updated: 2026-06-13*
*All services deployed and healthy*
