from app.domain.models import FieldResult, GroundTruthFields, LabelExtractedFields
from app.services import batch_manager


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

    result = batch_manager._verify_item_payload(  # noqa: SLF001
        {
            "form_payload": {"brand_name": "Acme Brewing"},
            "label_payload": {"brand_name": "Acme Brewing"},
        }
    )

    assert result["status"] == "pass"
    assert len(cleared_artifacts) == 1
    assert isinstance(cleared_artifacts[0][0], bytearray)
    assert isinstance(cleared_artifacts[0][1], bytearray)
