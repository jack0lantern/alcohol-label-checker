import json

from fastapi.testclient import TestClient

from app.main import create_app


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
            "alcoholic beverages during pregnancy because of the risk of birth defects."
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
        files={
            "form_pdf": ("form.pdf", json.dumps(ground_truth_payload).encode("utf-8"), "application/pdf"),
            "label_image": ("label.png", json.dumps(label_payload).encode("utf-8"), "image/png"),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pass"
    assert body["field_results"]["brand_name"]["status"] == "pass"
    assert body["field_results"]["class_type"]["status"] == "pass"
    assert body["field_results"]["alcohol_content"]["status"] == "pass"
    assert body["field_results"]["net_contents"]["status"] == "pass"
    assert body["field_results"]["government_warning"]["status"] == "pass"
