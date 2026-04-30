import time
import json
from difflib import SequenceMatcher
from base64 import b64encode
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "tests/fixtures/labels"


def test_batch_verify_starts_job_and_builds_report() -> None:
    app = create_app()
    client = TestClient(app)

    warning_text = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects."
    )

    response = client.post(
        "/verify/batch",
        json={
            "items": [
                {
                    "item_id": "item-pass",
                    "form_payload": {
                        "brand_name": "Acme Brewing",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    },
                    "label_payloads": [{
                        "brand_name": "Acme Brewing",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    }],
                },
                {
                    "item_id": "item-retry-then-review",
                    "form_payload": {
                        "brand_name": "Bad Input",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    },
                    "label_payloads": ["invalid-json-object"],
                },
                {
                    "item_id": "item-fail",
                    "form_payload": {
                        "brand_name": "Acme Brewing",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    },
                    "label_payloads": [{
                        "brand_name": "Different Brewing",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    }],
                },
            ]
        },
    )

    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert isinstance(job_id, str)
    assert job_id != ""

    in_progress_report = client.get(f"/verify/batch/{job_id}/report")
    assert in_progress_report.status_code in {200, 202}

    completed_report = _wait_for_completed_report(client, job_id)
    assert completed_report["job_id"] == job_id
    assert completed_report["status"] == "completed_with_failures"
    assert completed_report["summary"]["processed"] == 3
    assert completed_report["summary"]["total"] == 3
    assert completed_report["summary"]["pass"] == 1
    assert completed_report["summary"]["fail"] == 1
    assert completed_report["summary"]["review_required"] == 1

    by_id = {item["item_id"]: item for item in completed_report["items"]}
    assert by_id["item-pass"]["status"] == "completed"
    assert by_id["item-pass"]["overall_status"] == "pass"
    assert by_id["item-fail"]["status"] == "completed"
    assert by_id["item-fail"]["overall_status"] == "fail"
    assert by_id["item-retry-then-review"]["status"] == "review_required"
    assert by_id["item-retry-then-review"]["overall_status"] == "review_required"
    assert by_id["item-retry-then-review"]["attempts"] == 2


def test_batch_verify_marks_pass_and_fail_only_job_as_completed_with_failures() -> None:
    app = create_app()
    client = TestClient(app)

    warning_text = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects."
    )

    response = client.post(
        "/verify/batch",
        json={
            "items": [
                {
                    "item_id": "item-pass",
                    "form_payload": {
                        "brand_name": "Acme Brewing",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    },
                    "label_payloads": [{
                        "brand_name": "Acme Brewing",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    }],
                },
                {
                    "item_id": "item-fail",
                    "form_payload": {
                        "brand_name": "Acme Brewing",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    },
                    "label_payloads": [{
                        "brand_name": "Different Brewing",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    }],
                },
            ]
        },
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    completed_report = _wait_for_completed_report(client, job_id)
    assert completed_report["status"] == "completed_with_failures"
    assert completed_report["summary"]["pass"] == 1
    assert completed_report["summary"]["fail"] == 1
    assert completed_report["summary"]["review_required"] == 0

    by_id = {item["item_id"]: item for item in completed_report["items"]}
    assert by_id["item-pass"]["status"] == "completed"
    assert by_id["item-pass"]["overall_status"] == "pass"
    assert by_id["item-fail"]["status"] == "completed"
    assert by_id["item-fail"]["overall_status"] == "fail"


def test_batch_report_download_can_purge_completed_job() -> None:
    app = create_app()
    client = TestClient(app)

    warning_text = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects."
    )

    response = client.post(
        "/verify/batch",
        json={
            "items": [
                {
                    "item_id": "item-pass",
                    "form_payload": {
                        "brand_name": "Acme Brewing",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    },
                    "label_payloads": [{
                        "brand_name": "Acme Brewing",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    }],
                }
            ]
        },
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    completed_report = _wait_for_completed_report(client, job_id)
    assert completed_report["status"] == "completed"

    purge_response = client.get(f"/verify/batch/{job_id}/report?purge=true")
    assert purge_response.status_code == 200
    assert purge_response.json()["job_id"] == job_id

    missing_response = client.get(f"/verify/batch/{job_id}/report")
    assert missing_response.status_code == 404


def test_batch_verify_uses_real_ocr_for_fixture_images() -> None:
    app = create_app()
    client = TestClient(app)

    realistic_form = json.loads((FIXTURES_ROOT / "forms/realistic_clean_lager.json").read_text(encoding="utf-8"))
    realistic_image = (FIXTURES_ROOT / "images/realistic_clean_lager.png").read_bytes()
    adversarial_form = json.loads((FIXTURES_ROOT / "forms/adversarial_wrong_abv.json").read_text(encoding="utf-8"))
    adversarial_image = (FIXTURES_ROOT / "images/adversarial_wrong_abv.png").read_bytes()

    response = client.post(
        "/verify/batch",
        json={
            "items": [
                {
                    "item_id": "ocr-pass",
                    "form_payload": realistic_form,
                    "label_payloads": [{"image_base64": b64encode(realistic_image).decode("ascii")}],
                },
                {
                    "item_id": "ocr-fail",
                    "form_payload": adversarial_form,
                    "label_payloads": [{"image_base64": b64encode(adversarial_image).decode("ascii")}],
                },
            ]
        },
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    completed_report = _wait_for_completed_report(client, job_id)
    by_id = {item["item_id"]: item for item in completed_report["items"]}

    assert by_id["ocr-pass"]["status"] == "completed"
    assert by_id["ocr-pass"]["overall_status"] in {"pass", "fail", "review_required"}
    assert by_id["ocr-fail"]["status"] == "completed"
    assert by_id["ocr-fail"]["overall_status"] in {"fail", "review_required"}
    assert _similarity(
        realistic_form["brand_name"],
        by_id["ocr-pass"]["field_results"]["brand_name"]["extracted_value"],
    ) >= 0.8
    assert _similarity(
        realistic_form["class_type"],
        by_id["ocr-pass"]["field_results"]["class_type"]["extracted_value"],
    ) >= 0.8
    assert _similarity(
        realistic_form["alcohol_content"],
        by_id["ocr-pass"]["field_results"]["alcohol_content"]["extracted_value"],
    ) >= 0.55
    assert _similarity(
        realistic_form["net_contents"],
        by_id["ocr-pass"]["field_results"]["net_contents"]["extracted_value"],
    ) >= 0.6
    assert any(
        field_result["extracted_value"] is not None
        for field_result in by_id["ocr-fail"]["field_results"].values()
    )


def test_batch_verify_rejects_item_with_more_than_ten_images() -> None:
    app = create_app()
    client = TestClient(app)

    warning_text = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects."
    )
    response = client.post(
        "/verify/batch",
        json={
            "items": [
                {
                    "item_id": "too-many-images",
                    "form_payload": {
                        "brand_name": "Acme Brewing",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    },
                    "label_payloads": [{"brand_name": "Acme Brewing"} for _ in range(11)],
                }
            ]
        },
    )

    assert response.status_code == 422


def test_batch_verify_aggregates_best_results_from_multiple_images() -> None:
    app = create_app()
    client = TestClient(app)

    warning_text = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects."
    )
    response = client.post(
        "/verify/batch",
        json={
            "items": [
                {
                    "item_id": "multi-image-pass",
                    "form_payload": {
                        "brand_name": "Acme Brewing",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    },
                    "label_payloads": [
                        {
                            "brand_name": "Wrong Brand",
                            "class_type": "MALT BEVERAGE",
                            "alcohol_content": "5% alc/vol",
                            "net_contents": "12 fl oz",
                            "government_warning": warning_text,
                        },
                        {
                            "brand_name": "Acme Brewing",
                            "class_type": "MALT BEVERAGE",
                            "alcohol_content": "5% alc/vol",
                            "net_contents": "12 fl oz",
                            "government_warning": warning_text,
                        },
                    ],
                }
            ]
        },
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    completed_report = _wait_for_completed_report(client, job_id)
    item = completed_report["items"][0]
    assert item["status"] == "completed"
    assert item["overall_status"] == "pass"
    assert item["field_results"]["brand_name"]["status"] == "pass"
    assert len(item["image_results"]) == 2


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


def _similarity(expected: str, extracted: str | None) -> float:
    if extracted is None:
        return 0.0
    return SequenceMatcher(None, expected.casefold(), extracted.casefold()).ratio()
