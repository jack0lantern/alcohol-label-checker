import json
import tempfile

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
                "alcoholic beverages during pregnancy because of the risk of birth defects."
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
            "alcoholic beverages during pregnancy because of the risk of birth defects."
        ),
    }

    response = client.post(
        "/verify/single",
        files={
            "form_pdf": ("form.pdf", json.dumps(label_payload).encode("utf-8"), "application/pdf"),
            "label_image": ("label.png", json.dumps(label_payload).encode("utf-8"), "image/png"),
        },
    )

    assert response.status_code == 500
