from __future__ import annotations

from models.enums import JobStatus, JobType, TemplateCategory


def test_job_status_values():
    assert JobStatus.PENDING.value == "pending"
    assert JobStatus.COMPLETED.value == "completed"
    assert JobStatus.FAILED.value == "failed"
    assert JobStatus.RETRYING.value == "retrying"


def test_job_type_values():
    assert JobType.SINGLE.value == "single"
    assert JobType.BULK.value == "bulk"


def test_template_categories():
    assert TemplateCategory.PRODUCT_MOCKUP.value == "product_mockup"
    assert TemplateCategory.LIFESTYLE.value == "lifestyle"
    assert TemplateCategory.LANDING_PAGE.value == "landing_page"


def test_job_model_defaults():
    from models.job import JobModel

    job = JobModel(id="test-id", type="single", status="pending")
    assert job.width == 1024
    assert job.height == 1024
    assert job.num_images == 1
    assert job.max_retries == 3
    assert job.progress == 0.0


def test_asset_model():
    from models.asset import AssetModel

    asset = AssetModel(
        id="asset-1",
        job_id="job-1",
        filename="test.png",
        file_path="/tmp/test.png",
    )
    assert asset.delivery_status == "pending"
    assert asset.mime_type == "image/png"
