import json
import tempfile
import time

from fastapi.testclient import TestClient

from app.domain.models import GroundTruthFields
from app.main import create_app


def test_single_verify_rejects_disk_write_attempts(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)

    def _extract_ground_truth_with_disk_write(_: bytes) -> GroundTruthFields:
        with tempfile.NamedTemporaryFile(mode="wb") as file_handle:
            file_handle.write(b"forbidden")
        return GroundTruthFields(
            brand_name="Acme Brewing",
            class_type="MALT BEVERAGE",
            alcohol_content="5% alc/vol",
            net_contents="12 fl oz",
            government_warning=(
                "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
                "alcoholic beverages during pregnancy because of the risk of birth defects. "
                "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
                "operate machinery, and may cause health problems."
            ),
        )

    monkeypatch.setattr(
        "app.api.routes_verify.extract_ground_truth",
        _extract_ground_truth_with_disk_write,
    )

    label_payload = {
        "brand_name": "Acme Brewing",
        "class_type": "MALT BEVERAGE",
        "alcohol_content": "5% alc/vol",
        "net_contents": "12 fl oz",
        "government_warning": (
            "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
            "alcoholic beverages during pregnancy because of the risk of birth defects. "
            "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
            "operate machinery, and may cause health problems."
        ),
    }

    response = client.post(
        "/verify/single",
        files=[
            ("form_pdf", ("form.pdf", json.dumps(label_payload).encode("utf-8"), "application/pdf")),
            ("label_images", ("label.png", json.dumps(label_payload).encode("utf-8"), "image/png")),
        ],
    )

    assert response.status_code == 500


def test_batch_verify_marks_item_review_required_on_disk_write_attempt(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app = create_app()
    client = TestClient(app)

    def _extract_ground_truth_with_disk_write(_: bytes) -> GroundTruthFields:
        with tempfile.NamedTemporaryFile(mode="wb") as file_handle:
            file_handle.write(b"forbidden")
        return GroundTruthFields(
            brand_name="Acme Brewing",
            class_type="MALT BEVERAGE",
            alcohol_content="5% alc/vol",
            net_contents="12 fl oz",
            government_warning=(
                "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
                "alcoholic beverages during pregnancy because of the risk of birth defects. "
                "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
                "operate machinery, and may cause health problems."
            ),
        )

    monkeypatch.setattr(
        "app.services.batch_manager.extract_ground_truth",
        _extract_ground_truth_with_disk_write,
    )

    label_payload = {
        "brand_name": "Acme Brewing",
        "class_type": "MALT BEVERAGE",
        "alcohol_content": "5% alc/vol",
        "net_contents": "12 fl oz",
        "government_warning": (
            "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
            "alcoholic beverages during pregnancy because of the risk of birth defects. "
            "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
            "operate machinery, and may cause health problems."
        ),
    }

    create_response = client.post(
        "/verify/batch",
        json={
            "items": [
                {
                    "item_id": "item-disk-write",
                    "form_payload": label_payload,
                    "label_payloads": [label_payload],
                }
            ]
        },
    )
    assert create_response.status_code == 202
    job_id = create_response.json()["job_id"]

    completed_report = _wait_for_completed_report(client, job_id)
    assert completed_report["status"] == "completed_with_failures"
    assert completed_report["summary"]["processed"] == 1
    item = completed_report["items"][0]
    assert item["status"] == "review_required"
    assert item["attempts"] == 2
    assert "Disk write attempted" in item["error"]


def _wait_for_completed_report(client: TestClient, job_id: str) -> dict[str, object]:
    timeout_at = time.time() + 5
    while time.time() < timeout_at:
        response = client.get(f"/verify/batch/{job_id}/report")
        assert response.status_code in {200, 202}
        body = response.json()
        if body["status"] in {"completed", "completed_with_failures"}:
            return body
        time.sleep(0.05)
    raise AssertionError("Timed out waiting for completed batch report")
