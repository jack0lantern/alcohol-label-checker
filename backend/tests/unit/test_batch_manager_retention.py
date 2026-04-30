import base64
from pathlib import Path

from app.domain.models import FieldResult, GroundTruthFields, LabelExtractedFields
from app.services import batch_manager
from app.services.batch_manager import _verify_item_payload

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "tests/fixtures/labels"


def test_verify_item_payload_clears_intermediate_artifacts(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    cleared_artifacts: list[tuple[object, ...]] = []

    def _track_clear_single_artifacts(*artifacts: object) -> None:
        cleared_artifacts.append(artifacts)

    class _StubEngine:
        def extract_text(self, _: bytes) -> str:
            return '{"brand_name":"Acme Brewing"}'

    monkeypatch.setattr(
        "app.services.batch_manager.clear_single_artifacts",
        _track_clear_single_artifacts,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.batch_manager.extract_ground_truth",
        lambda _: GroundTruthFields(
            brand_name="Acme Brewing",
            class_type="MALT BEVERAGE",
            alcohol_content="5% alc/vol",
            net_contents="12 fl oz",
            government_warning="warning",
        ),
    )
    monkeypatch.setattr("app.services.batch_manager.preprocess_image", lambda payload: payload)
    monkeypatch.setattr("app.services.batch_manager.TesseractEngine", lambda: _StubEngine())
    monkeypatch.setattr(
        "app.services.batch_manager.extract_fields",
        lambda _: LabelExtractedFields(
            brand_name="Acme Brewing",
            class_type="MALT BEVERAGE",
            alcohol_content="5% alc/vol",
            net_contents="12 fl oz",
            government_warning="warning",
        ),
    )
    monkeypatch.setattr(
        "app.services.batch_manager.match_fields",
        lambda _ground, _fields: {
            "brand_name": FieldResult(
                field_name="brand_name",
                expected_value="Acme Brewing",
                extracted_value="Acme Brewing",
                status="pass",
            )
        },
    )

    pdf_bytes = (FIXTURES_ROOT / "forms/realistic_clean_lager_f510031.pdf").read_bytes()
    result = batch_manager._verify_item_payload(  # noqa: SLF001
        {
            "form_payload": {"pdf_base64": base64.b64encode(pdf_bytes).decode("ascii")},
            "label_payloads": [{"brand_name": "Acme Brewing"}],
        }
    )

    assert result["status"] in {"pass", "review_required"}
    assert len(cleared_artifacts) == 1
    assert isinstance(cleared_artifacts[0][0], bytearray)
    assert isinstance(cleared_artifacts[0][1], bytearray)


def test_get_job_snapshot_purges_expired_completed_jobs(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    expired_record = batch_manager.BatchJobRecord(
        job_id="job-expired",
        status="completed",
        total=0,
        processed=0,
        items=[],
    )
    expired_record.completed_at = 100.0

    with batch_manager._jobs_lock:  # noqa: SLF001
        batch_manager._jobs["job-expired"] = expired_record  # noqa: SLF001

    monkeypatch.setattr("app.services.batch_manager._COMPLETED_JOB_TTL_SECONDS", 5)
    monkeypatch.setattr("app.services.batch_manager._current_time", lambda: 106.0)

    snapshot = batch_manager.get_job_snapshot("job-expired")
    assert snapshot is None

    with batch_manager._jobs_lock:  # noqa: SLF001
        assert "job-expired" not in batch_manager._jobs  # noqa: SLF001


def test_verify_item_payload_decodes_pdf_base64() -> None:
    pdf_bytes = (FIXTURES_ROOT / "forms/realistic_clean_lager_f510031.pdf").read_bytes()
    image_bytes = (FIXTURES_ROOT / "images/realistic_clean_lager.png").read_bytes()

    item_payload = {
        "form_payload": {"pdf_base64": base64.b64encode(pdf_bytes).decode("ascii")},
        "label_payloads": [{"image_base64": base64.b64encode(image_bytes).decode("ascii")}],
    }

    result = _verify_item_payload(item_payload)
    assert result["status"] in {"pass", "fail", "review_required"}
    assert "field_results" in result
