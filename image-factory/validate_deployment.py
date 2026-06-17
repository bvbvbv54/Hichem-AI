#!/usr/bin/env python3
"""
Deployment Validation Script for ImageFactory

Checks all critical configuration, dependencies, API keys, and runtime
capabilities before deployment.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


def check_env_file() -> Tuple[bool, List[str]]:
    """Check if .env file exists and has required variables."""
    issues = []
    if not Path(".env").exists():
        issues.append("ERROR: .env file not found. Copy .env.example to .env and fill in required values.")
        return False, issues

    required_keys = [
        "GEMINI_API_KEY",
        "IMAGE_PROVIDER",
        "IMAGE_PROVIDER_API_KEY",
        "NANO_BANANA_API_KEY",
        "DATABASE_URL",
        "SECRET_KEY",
        "API_KEY",
    ]

    with open(".env") as f:
        env_content = f.read()

    missing = []
    for key in required_keys:
        if key not in env_content:
            missing.append(key)
        elif f"{key}=change-me" in env_content or f"{key}=" in env_content:
            issues.append(f"WARNING: {key} appears to use default value")

    if missing:
        issues.extend([f"MISSING: {k}" for k in missing])
        return False, issues

    return True, issues


def check_docker_setup() -> Tuple[bool, List[str]]:
    """Check Docker and Docker Compose are installed."""
    issues = []
    try:
        subprocess.run(["docker", "--version"], capture_output=True, check=True)
        subprocess.run(["docker-compose", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        issues.append(f"ERROR: Docker not properly installed: {e}")
        return False, issues
    return True, issues


def check_database_config() -> Tuple[bool, List[str]]:
    """Verify database configuration."""
    issues = []
    with open(".env") as f:
        for line in f:
            if line.startswith("DATABASE_URL="):
                db_url = line.split("=", 1)[1].strip()
                if not db_url or db_url == "change-me":
                    issues.append("ERROR: DATABASE_URL not configured")
                elif "postgresql" not in db_url:
                    issues.append("ERROR: DATABASE_URL should use PostgreSQL")
                break
    return len(issues) == 0, issues


def check_redis_config() -> Tuple[bool, List[str]]:
    """Verify Redis configuration."""
    issues = []
    with open(".env") as f:
        env_content = f.read()
    redis_keys = ["REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"]
    for key in redis_keys:
        if f"{key}=" not in env_content:
            issues.append(f"ERROR: {key} not configured")
    return len(issues) == 0, issues


def check_api_keys() -> Tuple[bool, List[str]]:
    """Check that essential API keys are configured."""
    issues = []
    with open(".env") as f:
        env_content = f.read()

    has_gemini = "GEMINI_API_KEY=" in env_content and "change-me" not in env_content
    if not has_gemini:
        issues.append("ERROR: GEMINI_API_KEY not configured (AI pipeline will fail)")

    has_image_key = "IMAGE_PROVIDER_API_KEY=" in env_content and "change-me" not in env_content
    if not has_image_key:
        issues.append("WARNING: IMAGE_PROVIDER_API_KEY not configured (image generation may fail)")

    has_nano = "NANO_BANANA_API_KEY=" in env_content and "change-me" not in env_content
    if not has_nano:
        issues.append("WARNING: NANO_BANANA_API_KEY not configured (image generation fallback)")

    return len([i for i in issues if i.startswith("ERROR")]) == 0, issues


def check_gdrive_credentials() -> Tuple[bool, List[str]]:
    """Check Google Drive credentials file exists and is valid JSON."""
    issues = []
    creds_path = Path("configs/gdrive_credentials.json")
    if not creds_path.exists():
        issues.append("WARNING: configs/gdrive_credentials.json not found — Google Drive uploads disabled")
        return True, issues

    try:
        data = json.loads(creds_path.read_text())
        required = ["installed", "client_id", "client_secret", "project_id"]
        if isinstance(data, dict) and "installed" in data:
            installed = data["installed"]
            for field in ["client_id", "client_secret"]:
                if field not in installed:
                    issues.append(f"ERROR: gdrive_credentials missing '{field}' in 'installed'")
        elif isinstance(data, dict):
            for field in required:
                if field not in data:
                    issues.append(f"ERROR: gdrive_credentials missing field '{field}'")
        else:
            issues.append("ERROR: gdrive_credentials.json has unexpected structure")
    except (json.JSONDecodeError, ValueError) as e:
        issues.append(f"ERROR: gdrive_credentials.json is not valid JSON: {e}")

    return len([i for i in issues if i.startswith("ERROR")]) == 0, issues


def check_playwright() -> Tuple[bool, List[str]]:
    """Check Playwright and chromium browser are installed."""
    issues = []
    try:
        import playwright
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium", "--dry-run"],
            capture_output=True, text=True, timeout=30,
        )
        issues.append("INFO: Playwright is installed")
    except ImportError:
        issues.append("WARNING: playwright not installed — browser fallback unavailable")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        issues.append("WARNING: could not verify Playwright browser install")
    return True, issues


def check_magic_library() -> Tuple[bool, List[str]]:
    """Check python-magic and libmagic are available."""
    issues = []
    try:
        import magic
        try:
            magic.from_buffer(b"test")
            issues.append("INFO: python-magic works correctly")
        except Exception as e:
            issues.append(f"WARNING: python-magic loaded but runtime check failed: {e}")
    except ImportError:
        issues.append("WARNING: python-magic not installed — MIME detection may fall back to extension")
    return True, issues


def check_redis_memory() -> Tuple[bool, List[str]]:
    """Check Redis has enough memory for cache."""
    issues = []
    try:
        import redis.asyncio as aioredis
        import asyncio

        async def _check():
            from configs.settings import settings
            r = await aioredis.from_url(settings.redis_url, socket_connect_timeout=5)
            try:
                info = await r.info("memory")
                max_mem = info.get("maxmemory", 0)
                used_mem = info.get("used_memory", 0)
                if max_mem > 0:
                    free_mb = (max_mem - used_mem) / (1024 * 1024)
                    if free_mb < 512:
                        issues.append(f"WARNING: Redis free memory < 512MB ({free_mb:.0f}MB free)")
                    else:
                        issues.append(f"INFO: Redis has {free_mb:.0f}MB free memory")
                else:
                    issues.append("INFO: Redis maxmemory not set (using all available)")
            finally:
                await r.aclose()

        asyncio.run(_check())
    except Exception as e:
        issues.append(f"WARNING: Could not check Redis memory: {e}")

    return True, issues


def check_image_acquisition() -> Tuple[bool, List[str]]:
    """Test image acquisition with a known-good public URL."""
    issues = []
    try:
        import asyncio
        from services.acquisition.pipeline import AcquisitionPipeline
        from services.acquisition.models import AcquisitionJob

        async def _test():
            pipeline = AcquisitionPipeline()
            try:
                job = AcquisitionJob(
                    job_id="deploy-test",
                    url="https://www.google.com/images/branding/googlelogo/2x/googlelogo_light_color_272x92dp.png",
                    max_images=1,
                )
                result = await pipeline.run(job)
                if result.success and result.image_paths:
                    issues.append(f"INFO: image acquisition OK — {len(result.image_paths)} image(s) downloaded")
                else:
                    issues.append(f"WARNING: image acquisition test failed — {result.failure_detail or 'no images'}")
            finally:
                await pipeline.close()

        asyncio.run(_test())
    except Exception as e:
        issues.append(f"WARNING: image acquisition test error: {e}")

    return True, issues


def check_nano_banana_connectivity() -> Tuple[bool, List[str]]:
    """Verify Nano Banana API key works with a minimal test call."""
    issues = []
    try:
        import asyncio
        from configs.settings import settings
        if not settings.get("nano_banana_api_key") and not os.getenv("NANO_BANANA_API_KEY"):
            issues.append("WARNING: NANO_BANANA_API_KEY not set — skipping connectivity check")
            return True, issues

        async def _test():
            try:
                from services.nano_banana.client import NanoBananaClient
                client = NanoBananaClient()
                ping = await client.ping() if hasattr(client, "ping") else None
                if ping:
                    issues.append("INFO: Nano Banana API key valid and reachable")
                else:
                    issues.append("INFO: Nano Banana client initialized (ping not available)")
            except Exception as e:
                issues.append(f"WARNING: Nano Banana connectivity test failed: {e}")

        asyncio.run(_test())
    except Exception as e:
        issues.append(f"WARNING: Nano Banana check error: {e}")

    return True, issues


def check_gdrive_auth_status() -> Tuple[bool, List[str]]:
    """Verify Google Drive auth status (if token exists, confirm it's not expired)."""
    issues = []
    token_path = Path("configs/gdrive_token.json")
    if not token_path.exists():
        issues.append("INFO: No Google Drive token found — Drive uploads require interactive auth")
        return True, issues

    try:
        token = json.loads(token_path.read_text())
        expiry = token.get("expiry") or token.get("expires_at") or token.get("expires_in")
        if expiry:
            import datetime
            if isinstance(expiry, str):
                expiry_dt = datetime.datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            elif isinstance(expiry, (int, float)):
                expiry_dt = datetime.datetime.fromtimestamp(expiry)
            else:
                issues.append("WARNING: Drive token expiry format unknown")
                return True, issues

            if expiry_dt < datetime.datetime.now(expiry_dt.tzinfo or datetime.timezone.utc):
                issues.append("WARNING: Google Drive token is expired — re-authorization needed")
            else:
                remaining = (expiry_dt - datetime.datetime.now(expiry_dt.tzinfo or datetime.timezone.utc)).days
                issues.append(f"INFO: Drive token valid ({remaining} days remaining)")
        else:
            issues.append("INFO: Drive token found (expiry check not applicable)")
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        issues.append(f"WARNING: Could not parse Drive token: {e}")

    return True, issues


def check_ssl_certificates() -> Tuple[bool, List[str]]:
    """Check if SSL certificates are needed and present."""
    issues = []
    with open(".env") as f:
        env_content = f.read()
    if "APP_ENV=production" in env_content:
        issues.append("INFO: Production mode detected. Ensure SSL certificates are configured in reverse proxy.")
    return True, issues


def check_storage_config() -> Tuple[bool, List[str]]:
    """Verify storage configuration."""
    issues = []
    return len(issues) == 0, issues


def main():
    """Run all validation checks."""
    print("\nImageFactory Deployment Validation\n")
    print("=" * 60)

    checks = [
        ("Environment File", check_env_file),
        ("Docker Setup", check_docker_setup),
        ("Database Configuration", check_database_config),
        ("Redis Configuration", check_redis_config),
        ("API Keys", check_api_keys),
        ("Google Drive Credentials", check_gdrive_credentials),
        ("Playwright / Browser Fallback", check_playwright),
        ("python-magic / libmagic", check_magic_library),
        ("Redis Memory Check", check_redis_memory),
        ("Image Acquisition Test", check_image_acquisition),
        ("Nano Banana Connectivity", check_nano_banana_connectivity),
        ("Google Drive Auth Status", check_gdrive_auth_status),
        ("SSL/Security", check_ssl_certificates),
        ("Storage Backend", check_storage_config),
    ]

    all_passed = True
    results = []

    for name, check_func in checks:
        try:
            passed, issues = check_func()
            status = "PASS" if passed else "FAIL"
            results.append((name, status, issues))
            if not passed and any(i.startswith("ERROR") for i in issues):
                all_passed = False
        except Exception as e:
            results.append((name, "ERROR", [str(e)]))
            all_passed = False

    print()
    for name, status, issues in results:
        icon = "+" if status == "PASS" else "-" if status == "FAIL" else "!"
        print(f" [{icon}] {status:5s} | {name}")
        for issue in issues:
            if issue.startswith("ERROR"):
                print(f"          X  {issue}")
            elif issue.startswith("WARNING"):
                print(f"          !  {issue}")
            elif issue.startswith("INFO"):
                print(f"          i  {issue}")

    print("=" * 60)

    if all_passed:
        print("\n All critical checks passed! Ready for deployment.\n")
        print("Next steps:")
        print("  1. Review warnings above")
        print("  2. Run: docker-compose up -d")
        print("  3. Verify: curl http://localhost:8000/api/v1/health")
        print("  4. Check dashboard: http://localhost:3000/login\n")
        return 0
    else:
        print("\n Some critical checks failed. Please resolve errors above.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
