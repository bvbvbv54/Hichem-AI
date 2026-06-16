# ImageFactory - API Keys & Quick Reference Guide

## 🔑 Required API Keys Setup

### 1. Claude API (Prompt Generation)

**Provider**: Anthropic  
**Purpose**: Generate and enhance prompts for image generation  
**Cost**: Pay-as-you-go ($0.003 per 1K input tokens)

**Setup Steps**:
1. Go to https://console.anthropic.com
2. Sign up / Log in
3. Navigate to "API Keys"
4. Click "Create Key"
5. Copy the key: `sk-ant-...`
6. Add to `.env`:
```env
CLAUDE_API_KEY=sk-ant-xxxxxxxxxxxxx
CLAUDE_MODEL=claude-sonnet-4-20250514
```

**Test**:
```bash
curl -X POST https://api.anthropic.com/v1/messages \
  -H "x-api-key: sk-ant-xxxxxxxxxxxxx" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

---

### 2. Image Generation Provider (Nano Banana)

Choose ONE provider for image generation:

#### Option A: Replicate (Recommended for Beginners)

**Provider**: Replicate  
**Purpose**: Generate images using multiple AI models  
**Cost**: Pay-per-API-call ($0.0025 - $0.05 per image)  
**Models**: Stable Diffusion 3, FLUX, Proteus

**Setup Steps**:
1. Go to https://replicate.com
2. Sign up with GitHub / Google
3. Go to "API Tokens" in Settings
4. Copy your API token: `r8_...`
5. Add to `.env`:
```env
IMAGE_PROVIDER=replicate
REPLICATE_API_KEY=r8_xxxxxxxxxxxxx
IMAGE_PROVIDER_API_KEY=r8_xxxxxxxxxxxxx
```

**Test**:
```bash
curl -X POST https://api.replicate.com/v1/predictions \
  -H "Authorization: Bearer r8_xxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "version": "6d6f86db...",
    "input": {"prompt": "a beautiful sunset"}
  }'
```

---

#### Option B: OpenAI DALL-E

**Provider**: OpenAI  
**Purpose**: GPT-4 Vision + DALL-E 3  
**Cost**: $0.04 - $0.20 per image  
**Quality**: Highest quality, most consistent

**Setup Steps**:
1. Go to https://platform.openai.com
2. Sign up / Log in
3. Create API Key in "API Keys" section
4. Copy: `sk-proj-...`
5. Add to `.env`:
```env
IMAGE_PROVIDER=openai
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx
IMAGE_PROVIDER_API_KEY=sk-proj-xxxxxxxxxxxxx
```

**Pricing**: https://openai.com/pricing/dall-e-3

---

#### Option C: StabilityAI

**Provider**: StabilityAI  
**Purpose**: Stable Diffusion models  
**Cost**: $0.001 - $0.04 per image  
**Quality**: Good, very fast

**Setup Steps**:
1. Go to https://platform.stability.ai
2. Sign up
3. Create API Key
4. Copy: `sk-...`
5. Add to `.env`:
```env
IMAGE_PROVIDER=stabilityai
STABILITYAI_API_KEY=sk-xxxxxxxxxxxxx
IMAGE_PROVIDER_API_KEY=sk-xxxxxxxxxxxxx
```

---

### 3. Storage Backend (Optional)

#### Option A: AWS S3 (Production Recommended)

**Setup Steps**:
1. Create AWS Account or use existing
2. Navigate to IAM → Users → Create User
3. Attach policy: `AmazonS3FullAccess` (or custom policy for bucket)
4. Create Access Key
5. Copy: Access Key ID + Secret Access Key
6. Create S3 bucket: `imagefactory-outputs`
7. Add to `.env`:
```env
STORAGE_BACKEND=s3
STORAGE_S3_BUCKET=imagefactory-outputs
STORAGE_S3_ACCESS_KEY=AKIA...
STORAGE_S3_SECRET_KEY=...
STORAGE_S3_REGION=us-east-1
```

#### Option B: Local Storage (Development/Small Scale)
```env
STORAGE_BACKEND=local
STORAGE_LOCAL_PATH=/app/outputs
```

---

### 4. Optional: OpenRouter (Alternative Provider)

**Provider**: OpenRouter  
**Purpose**: Access multiple AI models through one API  
**Cost**: Varies by model

**Setup**:
1. Go to https://openrouter.ai
2. Sign up
3. Create API Key
4. Add to `.env`:
```env
OPENROUTER_API_KEY=sk-or-...
```

---

## 🚀 Complete .env Template

```env
# ============================================
# CRITICAL - MUST CONFIGURE FOR OPERATION
# ============================================

# Prompt Generation (Claude)
CLAUDE_API_KEY=sk-ant-xxxxxxxxxxxxx
CLAUDE_MODEL=claude-sonnet-4-20250514
CLAUDE_MAX_TOKENS=4096
CLAUDE_TEMPERATURE=0.7

# Image Generation (Pick ONE provider)
# Option 1: Replicate
IMAGE_PROVIDER=replicate
REPLICATE_API_KEY=r8_xxxxxxxxxxxxx
IMAGE_PROVIDER_API_KEY=r8_xxxxxxxxxxxxx

# Option 2: OpenAI
# IMAGE_PROVIDER=openai
# OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx
# IMAGE_PROVIDER_API_KEY=sk-proj-xxxxxxxxxxxxx

# Option 3: StabilityAI
# IMAGE_PROVIDER=stabilityai
# STABILITYAI_API_KEY=sk-xxxxxxxxxxxxx
# IMAGE_PROVIDER_API_KEY=sk-xxxxxxxxxxxxx

# Security Keys (CHANGE THESE!)
SECRET_KEY=your-random-32-char-secret-key-here-12345678
API_KEY=your-custom-api-key-here-change-me

# ============================================
# INFRASTRUCTURE (Usually defaults are OK)
# ============================================

APP_ENV=production
DEBUG=false
APP_NAME=ImageFactory
APP_VERSION=1.0.0

# Database
DATABASE_URL=postgresql+asyncpg://imagefactory:imagefactory@postgres:5432/imagefactory
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=40

# Redis & Celery (Usually defaults are OK)
REDIS_URL=redis://redis:6379/0
REDIS_BROKER_URL=redis://redis:6379/1
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
CELERY_WORKER_CONCURRENCY=4

# ============================================
# OPTIONAL - Customize as needed
# ============================================

# Storage (local by default, or configure S3)
STORAGE_BACKEND=local
STORAGE_LOCAL_PATH=/app/outputs

# For S3:
# STORAGE_BACKEND=s3
# STORAGE_S3_BUCKET=my-bucket
# STORAGE_S3_ACCESS_KEY=AKIA...
# STORAGE_S3_SECRET_KEY=...
# STORAGE_S3_REGION=us-east-1

# Delivery
DELIVERY_BACKENDS=local
DELIVERY_LOCAL_PATH=/app/outputs

# Image Generation Timeouts
IMAGE_PROVIDER_TIMEOUT=120
IMAGE_PROVIDER_MAX_RETRIES=3
IMAGE_PROVIDER_POLL_INTERVAL=2

# API Rate Limiting
API_RATE_LIMIT=100
API_RATE_LIMIT_PERIOD=60

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_OUTPUT=stdout
```

---

## 📋 Quick Start Checklist

### Before Starting Docker:

```bash
# 1. Copy template
cp .env.example .env

# 2. Edit with your credentials
nano .env
# Required to fill in:
#   - CLAUDE_API_KEY
#   - IMAGE_PROVIDER
#   - IMAGE_PROVIDER_API_KEY (or REPLICATE_API_KEY)
#   - SECRET_KEY (generate one)
#   - API_KEY (create a custom one)

# 3. Validate configuration
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

### Start Services:

```bash
# Start all containers
docker-compose up -d

# Verify health
docker-compose ps
# All should say "healthy" or "up"

# Test API
curl http://localhost:8000/api/v1/health
# Should return: {"status": "healthy"}

# Access Dashboard
# http://localhost:3000
```

### Test Image Generation:

```bash
# Get API Key from .env
API_KEY=$(grep "^API_KEY=" .env | cut -d'=' -f2)

# Make test request
curl -X POST http://localhost:8000/api/v1/generation \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "red apple on a wooden table",
    "use_claude": true,
    "num_images": 1,
    "width": 1024,
    "height": 1024,
    "project_name": "test"
  }'

# Response should be:
# {"job_id": "uuid-here", "status": "pending"}

# Check job status
curl http://localhost:8000/api/v1/jobs/uuid-here \
  -H "X-API-Key: $API_KEY"
```

---

## 🔍 Troubleshooting API Keys

### "Invalid API Key" Error

```bash
# 1. Verify key is in .env
grep CLAUDE_API_KEY .env

# 2. Restart container (env vars only loaded at startup)
docker-compose restart api

# 3. Check logs
docker-compose logs api | grep -i "api.*key\|auth"
```

### "Image Generation Failed"

```bash
# 1. Verify IMAGE_PROVIDER_API_KEY
grep IMAGE_PROVIDER_API_KEY .env
grep REPLICATE_API_KEY .env  # if using Replicate

# 2. Check provider status (example for Replicate)
curl -H "Authorization: Bearer YOUR_KEY" \
  https://api.replicate.com/v1/account

# 3. Check worker logs
docker-compose logs worker | tail -50
```

### "Prompt Generation Failed"

```bash
# 1. Verify Claude key format (starts with sk-ant-)
grep CLAUDE_API_KEY .env

# 2. Test Claude API directly
curl -X POST https://api.anthropic.com/v1/messages \
  -H "x-api-key: YOUR_CLAUDE_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model": "claude-sonnet-4-20250514", "max_tokens": 100, "messages": [{"role": "user", "content": "test"}]}'
```

---

## 💰 Cost Estimation

### Per Image Cost (Approximate)

| Component | Cost | Cumulative |
|-----------|------|------------|
| **Prompt Generation** (Claude) | $0.0003 | $0.0003 |
| **Image Generation** (Replicate) | $0.01 | $0.0103 |
| **Storage** (S3) | $0.023/GB | $0.0133+ |
| **Total per Image** | — | **~$0.02-0.05** |

### Monthly Estimates

| Usage | Cost | Notes |
|-------|------|-------|
| **100 images** | $2-5 | Dev/testing |
| **1000 images** | $20-50 | Small business |
| **10,000 images** | $200-500 | Growing business |
| **100,000 images** | $2,000-5,000 | Enterprise |

---

## 🔐 Security Best Practices

1. **Never commit .env to Git**
   ```bash
   # Add to .gitignore
   echo ".env" >> .gitignore
   echo ".env.local" >> .gitignore
   ```

2. **Rotate API keys regularly**
   - Set a reminder for quarterly rotation
   - Use key versioning where available

3. **Use separate keys per environment**
   - Dev key (with lower limits)
   - Staging key
   - Production key

4. **Monitor API usage**
   - Set billing alerts in provider dashboards
   - Log all API calls (for audit trail)

5. **Restrict API key permissions**
   - Use provider IAM policies to limit scope
   - Rotate if exposed

---

## 📞 Support & Links

| Service | Link | Support |
|---------|------|---------|
| **Anthropic Claude** | https://console.anthropic.com | support@anthropic.com |
| **Replicate** | https://replicate.com | support@replicate.com |
| **OpenAI** | https://platform.openai.com | help.openai.com |
| **StabilityAI** | https://platform.stability.ai | discord.gg/StabilityAI |
| **AWS S3** | https://console.aws.amazon.com | AWS Support Plan |

---

## Final Checklist Before Deployment

- [ ] CLAUDE_API_KEY configured and tested
- [ ] IMAGE_PROVIDER_API_KEY configured
- [ ] SECRET_KEY changed from default
- [ ] API_KEY changed from default
- [ ] DATABASE_URL points to production (if applicable)
- [ ] STORAGE_BACKEND configured
- [ ] .env added to .gitignore
- [ ] Validation script passes
- [ ] docker-compose up -d works
- [ ] API health check passes
- [ ] Dashboard loads at http://localhost:3000
- [ ] Test generation request succeeds

✅ **Once all items checked, you're ready to deploy!**

---

**Questions?** Check DEPLOYMENT.md or PIPELINE_ARCHITECTURE.md for more details.
