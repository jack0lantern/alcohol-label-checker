import json
from difflib import SequenceMatcher
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "tests/fixtures/labels"


def test_single_verify_endpoint_returns_field_results() -> None:
    app = create_app()
    client = TestClient(app)

    ground_truth_payload = {
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
    label_payload = {
        "brand_name": "Acme Brewing",
        "class_type": "MALT BEVERAGE",
        "alcohol_content": "5% alc/vol",
        "net_contents": "12 fl oz",
        "government_warning": ground_truth_payload["government_warning"],
    }

    response = client.post(
        "/verify/single",
        files=[
            ("form_pdf", ("form.pdf", json.dumps(ground_truth_payload).encode("utf-8"), "application/pdf")),
            ("label_images", ("label.png", json.dumps(label_payload).encode("utf-8"), "image/png")),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "field_results", "image_results"}
    assert body["status"] == "pass"
    assert set(body["field_results"]) == {
        "brand_name",
        "class_type",
        "alcohol_content",
        "net_contents",
        "government_warning",
    }
    assert body["field_results"]["brand_name"]["status"] == "pass"
    assert body["field_results"]["class_type"]["status"] == "pass"
    assert body["field_results"]["alcohol_content"]["status"] == "pass"
    assert body["field_results"]["net_contents"]["status"] == "pass"
    assert body["field_results"]["government_warning"]["status"] == "pass"


def test_single_verify_endpoint_falls_back_for_binary_uploads() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/verify/single",
        files=[
            ("form_pdf", ("form.pdf", b"%PDF-1.4 binary-content", "application/pdf")),
            ("label_images", ("label.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", "image/png")),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "review_required"
    assert set(body["field_results"]) == {
        "brand_name",
        "class_type",
        "alcohol_content",
        "net_contents",
        "government_warning",
    }
    for field_result in body["field_results"].values():
        assert field_result["status"] == "review_required"
        assert field_result["expected_value"] is None
        assert field_result["extracted_value"] is None


def test_single_verify_uses_real_ocr_for_fixture_image() -> None:
    app = create_app()
    client = TestClient(app)

    form_payload = json.loads((FIXTURES_ROOT / "forms/realistic_clean_lager.json").read_text(encoding="utf-8"))
    image_bytes = (FIXTURES_ROOT / "images/realistic_clean_lager.png").read_bytes()

    response = client.post(
        "/verify/single",
        files=[
            ("form_pdf", ("form.pdf", json.dumps(form_payload).encode("utf-8"), "application/pdf")),
            ("label_images", ("label.png", image_bytes, "image/png")),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"pass", "fail", "review_required"}
    assert _similarity(
        form_payload["brand_name"],
        body["field_results"]["brand_name"]["extracted_value"],
    ) >= 0.8
    assert _similarity(
        form_payload["class_type"],
        body["field_results"]["class_type"]["extracted_value"],
    ) >= 0.8
    assert _similarity(
        form_payload["alcohol_content"],
        body["field_results"]["alcohol_content"]["extracted_value"],
    ) >= 0.55
    assert _similarity(
        form_payload["net_contents"],
        body["field_results"]["net_contents"]["extracted_value"],
    ) >= 0.6
    assert _similarity(
        form_payload["government_warning"],
        body["field_results"]["government_warning"]["extracted_value"],
    ) >= 0.8


def test_single_verify_blank_ttb_pdf_does_not_disable_ocr_on_label() -> None:
    """Real TTB PDF is binary UTF-8 must not trigger the global null fallback (UnicodeDecodeError path)."""
    app = create_app()
    client = TestClient(app)

    pdf_path = FIXTURES_ROOT / "forms/f510031.pdf"
    image_path = FIXTURES_ROOT / "images/realistic_clean_lager.png"
    assert pdf_path.is_file()

    response = client.post(
        "/verify/single",
        files=[
            ("form_pdf", ("f510031.pdf", pdf_path.read_bytes(), "application/pdf")),
            ("label_images", ("label.png", image_path.read_bytes(), "image/png")),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    # Blank form: no JSON ground truth, but label OCR must still populate extracted_value.
    assert body["field_results"]["brand_name"]["expected_value"] is None
    extracted = body["field_results"]["brand_name"]["extracted_value"]
    assert extracted is not None
    assert len(extracted.strip()) > 0


def test_single_verify_rejects_more_than_ten_images() -> None:
    app = create_app()
    client = TestClient(app)

    form_payload = {
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
    files: list[tuple[str, tuple[str, bytes, str]]] = [
        ("form_pdf", ("form.pdf", json.dumps(form_payload).encode("utf-8"), "application/pdf"))
    ]
    files.extend(
        ("label_images", (f"label-{index}.png", b"{}", "image/png"))
        for index in range(11)
    )

    response = client.post("/verify/single", files=files)
    assert response.status_code == 400
    assert response.json()["detail"] == "label_images must include between 1 and 10 files"


def test_single_verify_aggregates_best_results_from_multiple_images() -> None:
    app = create_app()
    client = TestClient(app)

    warning_text = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
        "operate machinery, and may cause health problems."
    )
    form_payload = {
        "brand_name": "Acme Brewing",
        "class_type": "MALT BEVERAGE",
        "alcohol_content": "5% alc/vol",
        "net_contents": "12 fl oz",
        "government_warning": warning_text,
    }
    bad_label_payload = {
        "brand_name": "Different Brewing",
        "class_type": "MALT BEVERAGE",
        "alcohol_content": "5% alc/vol",
        "net_contents": "12 fl oz",
        "government_warning": warning_text,
    }
    good_label_payload = {
        "brand_name": "Acme Brewing",
        "class_type": "MALT BEVERAGE",
        "alcohol_content": "5% alc/vol",
        "net_contents": "12 fl oz",
        "government_warning": warning_text,
    }

    response = client.post(
        "/verify/single",
        files=[
            ("form_pdf", ("form.pdf", json.dumps(form_payload).encode("utf-8"), "application/pdf")),
            ("label_images", ("bad-label.png", json.dumps(bad_label_payload).encode("utf-8"), "image/png")),
            ("label_images", ("good-label.png", json.dumps(good_label_payload).encode("utf-8"), "image/png")),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pass"
    assert len(body["image_results"]) == 2
    assert body["image_results"][0]["status"] == "fail"
    assert body["image_results"][1]["status"] == "pass"
    assert body["field_results"]["brand_name"]["status"] == "pass"
    assert body["field_results"]["brand_name"]["extracted_value"] == "Acme Brewing"


def _similarity(expected: str, extracted: str | None) -> float:
    if extracted is None:
        return 0.0
    return SequenceMatcher(None, expected.casefold(), extracted.casefold()).ratio()
