import time

from fastapi.testclient import TestClient

from app.main import create_app


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
                    "label_payload": {
                        "brand_name": "Acme Brewing",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    },
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
                    "label_payload": "invalid-json-object",
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
                    "label_payload": {
                        "brand_name": "Different Brewing",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    },
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
                    "label_payload": {
                        "brand_name": "Acme Brewing",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    },
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
                    "label_payload": {
                        "brand_name": "Different Brewing",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    },
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
