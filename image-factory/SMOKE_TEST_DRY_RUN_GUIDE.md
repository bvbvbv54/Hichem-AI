# 🧪 Smoke Test & Dry Run Explained

## What is a Dry Run?

**Dry Run** = Preview without spending money or resources

A **dry run** shows you exactly what will happen if you run a smoke test, but **without actually executing it**. It's like a rehearsal:

```
Normal Flow:                  Dry Run Flow:
1. Create sample data    →    1. SIMULATE creating sample data
2. Call Claude API       →    2. ESTIMATE Claude API costs
3. Call Image Gen API    →    3. ESTIMATE Image Gen API costs
4. Store results         →    4. Calculate total time & cost
5. Report status         →    5. Report what WOULD happen
```

### Dry Run Shows:
- ✅ What steps will execute
- ✅ Estimated cost in cents
- ✅ Estimated time per step
- ✅ Total estimated duration
- ✅ Any warnings or issues

### Dry Run Does NOT:
- ❌ Make actual API calls
- ❌ Generate real images
- ❌ Spend any API credits
- ❌ Create database records
- ❌ Consume any resources

---

## What is a Smoke Test?

**Smoke Test** = Full end-to-end system test with real resources

A **smoke test** actually runs the entire pipeline:

```
1. Generate sample product data
2. Call Claude API to enhance prompt
3. Call Image Generation provider (Replicate/StabilityAI/OpenAI)
4. Store generated images
5. Verify delivery backends work
6. Track actual costs spent
7. Report complete results
```

### Smoke Test Does:
- ✅ Makes real API calls to Claude
- ✅ Generates actual images
- ✅ Consumes API credits
- ✅ Stores images in your storage backend
- ✅ Tests delivery mechanism
- ✅ Reports actual costs, timing, errors

### When Smoke Test Fails:

Common failure reasons:
1. **Missing API Keys** - CLAUDE_API_KEY or IMAGE_PROVIDER_API_KEY not set
2. **API Key Invalid** - Expired or wrong credentials
3. **Insufficient Credits** - No balance in Replicate/StabilityAI account
4. **Network Issues** - Cannot reach API endpoints
5. **Database Problems** - Cannot save results
6. **Storage Issues** - Cannot write to storage backend

---

## Why Your Smoke Test Failed

From the dashboard screenshot, your smoke test likely failed because:

1. **AI Provider Connectivity** shows ⚠️ Warning - The image provider (Replicate/StabilityAI) isn't reachable or API key is invalid
2. **PostgreSQL DB** shows offline - Database connection issue
3. **Worker System** shows offline - Celery worker not running or not registered

### How to Fix:

**Option 1: Check Environment Variables**
```bash
# Verify .env file has valid API keys
docker compose exec api cat /app/.env | grep -i "API_KEY"
```

**Option 2: Check Logs**
```bash
# View API logs for specific error
docker logs imagefactory-api --tail 100 | grep -i "error\|failed"
```

**Option 3: Restart Services**
```bash
# Restart everything
docker compose restart

# Check status
docker compose ps
```

**Option 4: Run Health Check**
```bash
# Direct API health check
curl http://localhost:8000/api/v1/health

# Readiness check
curl http://localhost:8000/api/v1/health/ready
```

---

## When to Use Each

| Use Case | Dry Run | Smoke Test |
|----------|---------|-----------|
| **First time setup** | ✅ Start here | ❌ After dry run passes |
| **Before going live** | ✅ Verify estimates | ✅ Verify actual execution |
| **Budget check** | ✅ Yes | ❌ Costs real money |
| **Testing API keys** | ✅ Detects issues | ✅ Real validation |
| **Regular monitoring** | ❌ Not needed | ✅ Once per week |
| **Troubleshooting** | ✅ See what should happen | ✅ See what actually happens |

### Recommended Workflow:

```
1. Run Dry Run Preview
   ↓ (Review estimated costs & steps)
2. Fix any warnings shown
   ↓
3. Run Smoke Test
   ↓ (Verify real execution)
4. Review results
   ↓
5. Check estimated costs match actual
   ↓
6. Dashboard is ready for production!
```

---

## Dashboard Tracking

Both dry run and smoke test results appear in the System Readiness panel:

```
Last Smoke Test Status: [Shows latest result]
├─ Status: ✅ Passed / ❌ Failed
├─ Duration: 45.2 seconds
└─ Cost: $0.15

Smoke Test Runtime: Shows actual execution time
Smoke Test Cost Estimate: Shows credits consumed
```

The dashboard **automatically refreshes** every 5 seconds to show latest status.

---

## Example Flow in Dashboard

```
1. User clicks "Run Smoke Test"
   ↓
2. Button shows spinning loader
   ↓
3. System runs actual pipeline
   ├─ Generates test product
   ├─ Calls Claude API
   ├─ Generates test image
   └─ Stores results
   ↓
4. Dashboard updates with results
   ├─ Shows Pass/Fail status
   ├─ Shows time taken
   ├─ Shows cost in cents
   └─ Shows detailed step results
   ↓
5. User can now verify system readiness
```

---

## System Readiness Components

Dashboard monitors these components:

| Component | What It Does | Status Meanings |
|-----------|-------------|-----------------|
| **Backend API** | FastAPI server | 🟢 Running, 🔴 Down |
| **Worker System** | Celery task processing | 🟢 Active, 🔴 Offline |
| **Message Queue** | Redis job queue | 🟢 Connected, 🔴 Offline |
| **PostgreSQL DB** | Data persistence | 🟢 Connected, 🔴 Offline |
| **Redis Cache** | Caching layer | 🟢 Connected, 🔴 Offline |
| **Asset Storage** | File storage | 🟢 Writable, 🔴 Inaccessible |
| **Delivery Backends** | Output delivery | 🟢 Ready, 🟡 Warning |
| **AI Provider** | Image generation API | 🟢 Reachable, 🟡 Slow, 🔴 Down |

---

## Key Metrics Tracked

After smoke test completes:

- **Text API Calls Used** - How many Claude API calls were made
- **Image API Calls Used** - How many image generation calls
- **Total Duration** - Wall-clock time from start to finish
- **Estimated Cost** - Total API costs in cents (¢)
- **Detailed Steps** - Individual step timing and errors

Example result:
```
Text Calls: 1 (Claude prompt enhancement)
Image Calls: 1 (Generate test image)
Duration: 32.5 seconds
Cost: 0.47 cents ($0.0047)
Status: ✅ PASSED
```

---

## Summary

- **Dry Run** = Safe preview, no costs, shows estimates
- **Smoke Test** = Real execution, actual costs, verifies everything works
- Use Dry Run first to understand system
- Use Smoke Test to validate production readiness
- Check System Readiness panel after each test
- All components should be 🟢 Green for production
