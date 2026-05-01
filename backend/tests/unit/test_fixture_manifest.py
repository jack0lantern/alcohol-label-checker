import json
from hashlib import sha256
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPO_ROOT / "tests/fixtures/labels/fixtures_manifest.json"
EXPECTED_GENERATED_AT_UTC = "1970-01-01T00:00:00Z"


def test_fixture_manifest_references_existing_files() -> None:
    assert MANIFEST_PATH.exists(), "Fixture manifest is missing"

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    fixtures = manifest.get("fixtures")
    generated_at_utc = manifest.get("generated_at_utc")

    assert isinstance(fixtures, list), "Manifest fixtures must be a list"
    assert fixtures, "Manifest fixtures list must not be empty"
    assert generated_at_utc == EXPECTED_GENERATED_AT_UTC, (
        "Manifest generated_at_utc must be deterministic"
    )

    image_digests_by_fixture: dict[str, str] = {}
    for fixture in fixtures:
        fixture_id = fixture.get("fixture_id")
        assert isinstance(fixture_id, str) and fixture_id, (
            "Fixture fixture_id must be a non-empty string"
        )

        sample_type = fixture.get("sample_type")
        assert isinstance(sample_type, str) and sample_type, (
            "Fixture sample_type must be a non-empty string"
        )

        for field in ("image", "form", "truth", "expected"):
            raw_path = fixture.get(field)
            assert isinstance(raw_path, str) and raw_path, (
                f"Fixture {field} path must be a non-empty string"
            )
            assert not Path(raw_path).is_absolute(), (
                f"Fixture {field} path must be repo-relative: {raw_path}"
            )

            resolved_path = REPO_ROOT / raw_path
            assert resolved_path.exists(), (
                f"Manifest references missing {field} file: {raw_path}"
            )

            if field == "image":
                digest = sha256(resolved_path.read_bytes()).hexdigest()
                image_digests_by_fixture[fixture_id] = digest

            checksum_field = f"{field}_sha256"
            checksum_value = fixture.get(checksum_field)
            assert isinstance(checksum_value, str) and len(checksum_value) == 64, (
                f"Fixture must include {checksum_field} checksum"
            )
            assert checksum_value == sha256(resolved_path.read_bytes()).hexdigest(), (
                f"{checksum_field} mismatch for {raw_path}"
            )

    assert len(set(image_digests_by_fixture.values())) == len(image_digests_by_fixture), (
        "Each fixture image must be content-distinct to avoid placeholder regressions"
    )
