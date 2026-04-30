import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "tests/fixtures/labels"


def _wait_completed(client: TestClient, job_id: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/verify/batch/{job_id}/report")
        if response.status_code == 200:
            return response.json()
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not complete within {timeout}s")


def test_batch_verify_multipart_happy_path() -> None:
    app = create_app()
    client = TestClient(app)

    pdf_path = FIXTURES_ROOT / "forms/realistic_clean_lager_f510031.pdf"
    image_path = FIXTURES_ROOT / "images/realistic_clean_lager.png"

    mapping = json.dumps({
        "items": [
            {
                "item_id": "lager-1",
                "form_filename": pdf_path.name,
                "label_filenames": [image_path.name],
            }
        ]
    })

    with pdf_path.open("rb") as form_file, image_path.open("rb") as label_file:
        response = client.post(
            "/verify/batch",
            data={"mapping": mapping},
            files=[
                ("files", (pdf_path.name, form_file, "application/pdf")),
                ("files", (image_path.name, label_file, "image/png")),
            ],
        )

    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    report = _wait_completed(client, job_id)
    assert report["job_id"] == job_id
    assert report["summary"]["total"] == 1


def _post(client, mapping: str, files: list) -> object:
    return client.post("/verify/batch", data={"mapping": mapping}, files=files)


def test_batch_verify_invalid_mapping_json() -> None:
    app = create_app()
    client = TestClient(app)
    pdf_path = FIXTURES_ROOT / "forms/realistic_clean_lager_f510031.pdf"
    with pdf_path.open("rb") as f:
        response = _post(client, "{not json", [("files", (pdf_path.name, f, "application/pdf"))])
    assert response.status_code == 400
    assert "invalid mapping" in response.json()["detail"].lower()


def test_batch_verify_missing_referenced_file() -> None:
    app = create_app()
    client = TestClient(app)
    pdf_path = FIXTURES_ROOT / "forms/realistic_clean_lager_f510031.pdf"
    image_path = FIXTURES_ROOT / "images/realistic_clean_lager.png"
    mapping = json.dumps({"items": [{"item_id": "x", "form_filename": pdf_path.name, "label_filenames": ["does-not-exist.png"]}]})
    with pdf_path.open("rb") as form_file, image_path.open("rb") as label_file:
        response = _post(client, mapping, [("files", (pdf_path.name, form_file, "application/pdf")), ("files", (image_path.name, label_file, "image/png"))])
    assert response.status_code == 400
    assert "does-not-exist.png" in response.json()["detail"]


def test_batch_verify_duplicate_item_id() -> None:
    app = create_app()
    client = TestClient(app)
    pdf_path = FIXTURES_ROOT / "forms/realistic_clean_lager_f510031.pdf"
    image_path = FIXTURES_ROOT / "images/realistic_clean_lager.png"
    mapping = json.dumps({"items": [
        {"item_id": "dup", "form_filename": pdf_path.name, "label_filenames": [image_path.name]},
        {"item_id": "dup", "form_filename": pdf_path.name, "label_filenames": [image_path.name]},
    ]})
    with pdf_path.open("rb") as f1, image_path.open("rb") as f2:
        response = _post(client, mapping, [("files", (pdf_path.name, f1, "application/pdf")), ("files", (image_path.name, f2, "image/png"))])
    assert response.status_code == 400
    assert "duplicate item_id" in response.json()["detail"]


def test_batch_verify_label_count_out_of_range() -> None:
    app = create_app()
    client = TestClient(app)
    pdf_path = FIXTURES_ROOT / "forms/realistic_clean_lager_f510031.pdf"
    mapping = json.dumps({"items": [{"item_id": "x", "form_filename": pdf_path.name, "label_filenames": []}]})
    with pdf_path.open("rb") as f:
        response = _post(client, mapping, [("files", (pdf_path.name, f, "application/pdf"))])
    assert response.status_code == 400
    assert "1-10 labels" in response.json()["detail"]


def test_batch_verify_one_malformed_pdf_yields_review_required() -> None:
    app = create_app()
    client = TestClient(app)
    good_pdf = FIXTURES_ROOT / "forms/realistic_clean_lager_f510031.pdf"
    image = FIXTURES_ROOT / "images/realistic_clean_lager.png"
    mapping = json.dumps({"items": [
        {"item_id": "good", "form_filename": good_pdf.name, "label_filenames": [image.name]},
        {"item_id": "bad", "form_filename": "broken.pdf", "label_filenames": [image.name]},
    ]})
    with good_pdf.open("rb") as g, image.open("rb") as i:
        response = client.post(
            "/verify/batch",
            data={"mapping": mapping},
            files=[
                ("files", (good_pdf.name, g, "application/pdf")),
                ("files", (image.name, i, "image/png")),
                ("files", ("broken.pdf", b"this is not a pdf", "application/pdf")),
            ],
        )
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    report = _wait_completed(client, job_id)
    assert report["summary"]["total"] == 2
    statuses = {item["item_id"]: item["overall_status"] for item in report["items"]}
    assert statuses["bad"] == "review_required"
