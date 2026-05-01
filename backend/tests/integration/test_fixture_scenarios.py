"""Fixture-driven integration tests for generated and adversarial label scenarios.

Each test loads fixture data from tests/fixtures/labels/ and exercises the
/verify/single or /verify/batch endpoint.

JSON injection: truth JSON is uploaded as the "label image" file. The backend
detects non-image bytes and parses them as extracted field values directly,
bypassing real OCR. This gives deterministic assertions on the matcher logic.

Real OCR: the synthetic PNG image is uploaded. Tesseract reads the rendered
text and the assertions verify that the pipeline correctly flags the scenario.
"""

import json
import time
from difflib import SequenceMatcher
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "tests/fixtures/labels"


def _load_form(fixture_id: str) -> dict:
    return json.loads((FIXTURES_ROOT / "forms" / f"{fixture_id}.json").read_text(encoding="utf-8"))


def _load_truth(fixture_id: str) -> dict:
    return json.loads((FIXTURES_ROOT / "truth" / f"{fixture_id}.json").read_text(encoding="utf-8"))


def _load_image(fixture_id: str) -> bytes:
    return (FIXTURES_ROOT / "images" / f"{fixture_id}.png").read_bytes()


def _single(client: TestClient, form: dict, label_bytes: bytes, label_name: str = "label.png") -> dict:
    response = client.post(
        "/verify/single",
        files=[
            ("form_pdf", ("form.pdf", json.dumps(form).encode("utf-8"), "application/pdf")),
            ("label_images", (label_name, label_bytes, "image/png")),
        ],
    )
    assert response.status_code == 200, response.text
    return response.json()


def _similarity(a: str, b: str | None) -> float:
    if b is None:
        return 0.0
    return SequenceMatcher(None, a.casefold().strip(), b.casefold().strip()).ratio()


# ---------------------------------------------------------------------------
# generated_citrus_ipa – clean label, all fields should pass
# ---------------------------------------------------------------------------

def test_generated_citrus_ipa_passes_json_injection() -> None:
    """All fields match when truth JSON is injected directly as extracted values."""
    client = TestClient(create_app())
    form = _load_form("generated_citrus_ipa")
    truth = _load_truth("generated_citrus_ipa")

    body = _single(client, form, json.dumps(truth).encode("utf-8"))

    assert body["status"] == "pass"
    for field, result in body["field_results"].items():
        assert result["status"] == "pass", f"{field}: expected pass, got {result['status']}"


def test_generated_citrus_ipa_passes_real_ocr() -> None:
    """Real Tesseract OCR on the synthetic PNG extracts values similar to declared form values."""
    client = TestClient(create_app())
    form = _load_form("generated_citrus_ipa")
    image = _load_image("generated_citrus_ipa")

    body = _single(client, form, image)
    fr = body["field_results"]

    assert _similarity(form["brand_name"], fr["brand_name"]["extracted_value"]) >= 0.8
    assert _similarity(form["class_type"], fr["class_type"]["extracted_value"]) >= 0.8
    assert _similarity(form["alcohol_content"], fr["alcohol_content"]["extracted_value"]) >= 0.6
    assert _similarity(form["net_contents"], fr["net_contents"]["extracted_value"]) >= 0.6
    assert _similarity(form["government_warning"], fr["government_warning"]["extracted_value"]) >= 0.8


# ---------------------------------------------------------------------------
# adversarial_warning_typo – one-char typo triggers review_required
# ---------------------------------------------------------------------------

def test_adversarial_warning_typo_yields_review_required() -> None:
    """One-char typo in government warning ('GOVERNMET') produces review_required, not pass or fail."""
    client = TestClient(create_app())
    form = _load_form("adversarial_warning_typo")   # correct warning
    truth = _load_truth("adversarial_warning_typo")  # typo warning

    body = _single(client, form, json.dumps(truth).encode("utf-8"))

    assert body["status"] == "review_required"
    assert body["field_results"]["government_warning"]["status"] == "review_required"
    assert body["field_results"]["brand_name"]["status"] == "pass"
    assert body["field_results"]["class_type"]["status"] == "pass"
    assert body["field_results"]["alcohol_content"]["status"] == "pass"
    assert body["field_results"]["net_contents"]["status"] == "pass"


def test_adversarial_warning_typo_expected_values_are_present() -> None:
    """The response carries both the declared and extracted warning text for human review."""
    client = TestClient(create_app())
    form = _load_form("adversarial_warning_typo")
    truth = _load_truth("adversarial_warning_typo")

    body = _single(client, form, json.dumps(truth).encode("utf-8"))

    gw = body["field_results"]["government_warning"]
    assert gw["expected_value"] == form["government_warning"]
    assert gw["extracted_value"] == truth["government_warning"]
    assert gw["expected_value"] != gw["extracted_value"]


# ---------------------------------------------------------------------------
# adversarial_wrong_abv – label shows 7.0% but form declares 5.0%
# ---------------------------------------------------------------------------

def test_adversarial_wrong_abv_yields_fail() -> None:
    """Mismatched alcohol content (5.0% declared vs 7.0% on label) produces alcohol_content fail."""
    client = TestClient(create_app())
    form = _load_form("adversarial_wrong_abv")   # 5.0% ALC/VOL
    truth = _load_truth("adversarial_wrong_abv")  # 7.0% ALC/VOL

    body = _single(client, form, json.dumps(truth).encode("utf-8"))

    assert body["status"] == "fail"
    abv = body["field_results"]["alcohol_content"]
    assert abv["status"] == "fail"
    assert abv["expected_value"] == form["alcohol_content"]
    assert abv["extracted_value"] == truth["alcohol_content"]
    assert body["field_results"]["brand_name"]["status"] == "pass"
    assert body["field_results"]["class_type"]["status"] == "pass"
    assert body["field_results"]["net_contents"]["status"] == "pass"
    assert body["field_results"]["government_warning"]["status"] == "pass"


def test_adversarial_wrong_abv_real_ocr_flags_mismatch() -> None:
    """Real OCR reads 7.0% from the image; the pipeline must not yield pass for alcohol_content."""
    client = TestClient(create_app())
    form = _load_form("adversarial_wrong_abv")
    image = _load_image("adversarial_wrong_abv")

    body = _single(client, form, image)

    assert body["field_results"]["alcohol_content"]["status"] != "pass"


# ---------------------------------------------------------------------------
# Batch: mix of clean and adversarial items
# ---------------------------------------------------------------------------

def _wait_batch(client: TestClient, job_id: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"/verify/batch/{job_id}/report")
        if r.status_code == 200:
            return r.json()
        time.sleep(0.05)
    raise AssertionError(f"batch job {job_id} did not complete within {timeout}s")


def test_batch_clean_and_adversarial_items_reported_correctly() -> None:
    """Batch with one clean item and one adversarial-wrong-abv item: clean passes, adversarial fails."""
    client = TestClient(create_app())

    form_clean = _load_form("generated_citrus_ipa")
    truth_clean = _load_truth("generated_citrus_ipa")
    form_adv = _load_form("adversarial_wrong_abv")
    truth_adv = _load_truth("adversarial_wrong_abv")

    mapping = json.dumps({
        "items": [
            {"item_id": "clean", "form_filename": "form_clean.pdf", "label_filenames": ["label_clean.png"]},
            {"item_id": "adv",   "form_filename": "form_adv.pdf",   "label_filenames": ["label_adv.png"]},
        ]
    })

    response = client.post(
        "/verify/batch",
        data={"mapping": mapping},
        files=[
            ("files", ("form_clean.pdf", json.dumps(form_clean).encode("utf-8"), "application/pdf")),
            ("files", ("label_clean.png", json.dumps(truth_clean).encode("utf-8"), "image/png")),
            ("files", ("form_adv.pdf",   json.dumps(form_adv).encode("utf-8"),   "application/pdf")),
            ("files", ("label_adv.png",  json.dumps(truth_adv).encode("utf-8"),  "image/png")),
        ],
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]

    report = _wait_batch(client, job_id)

    assert report["summary"]["total"] == 2
    by_id = {item["item_id"]: item["overall_status"] for item in report["items"]}
    assert by_id["clean"] == "pass"
    assert by_id["adv"] == "fail"


def test_batch_review_required_item_counted_separately() -> None:
    """Batch with a warning-typo item is counted as review_required in the summary."""
    client = TestClient(create_app())

    form_typo = _load_form("adversarial_warning_typo")
    truth_typo = _load_truth("adversarial_warning_typo")

    mapping = json.dumps({
        "items": [
            {"item_id": "typo", "form_filename": "form_typo.pdf", "label_filenames": ["label_typo.png"]},
        ]
    })

    response = client.post(
        "/verify/batch",
        data={"mapping": mapping},
        files=[
            ("files", ("form_typo.pdf",  json.dumps(form_typo).encode("utf-8"),  "application/pdf")),
            ("files", ("label_typo.png", json.dumps(truth_typo).encode("utf-8"), "image/png")),
        ],
    )
    assert response.status_code == 202, response.text
    report = _wait_batch(client, response.json()["job_id"])

    assert report["summary"]["total"] == 1
    assert report["summary"]["review_required"] == 1
    assert report["summary"]["fail"] == 0
    assert report["summary"]["pass"] == 0
