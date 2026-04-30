import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPO_ROOT / "tests/fixtures/labels/fixtures_manifest.json"
REQUIRED_SAMPLE_TYPES = {"realistic", "generated", "adversarial"}


def test_fixture_manifest_references_existing_files() -> None:
    assert MANIFEST_PATH.exists(), "Fixture manifest is missing"

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    fixtures = manifest.get("fixtures")

    assert isinstance(fixtures, list), "Manifest fixtures must be a list"
    assert fixtures, "Manifest fixtures list must not be empty"

    sample_types = set()
    for fixture in fixtures:
        sample_type = fixture.get("sample_type")
        assert isinstance(sample_type, str) and sample_type, (
            "Fixture sample_type must be a non-empty string"
        )
        sample_types.add(sample_type)

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

    assert REQUIRED_SAMPLE_TYPES.issubset(sample_types), (
        "Manifest must include realistic, generated, and adversarial samples"
    )
