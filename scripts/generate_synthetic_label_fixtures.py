#!/usr/bin/env python3
"""Generate hermetic fixture assets for label verification tests."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


PNG_1X1_TRANSPARENT = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\x0bIDATx\x9cc``\x00\x00\x00\x02\x00\x01"
    b"\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
)


@dataclass(frozen=True)
class FixtureSpec:
    fixture_id: str
    sample_type: str
    source: str
    scenario: str
    notes: str
    truth: dict[str, str]
    extracted: dict[str, str]
    expected: dict[str, object]


def _build_fixture_specs() -> list[FixtureSpec]:
    warning = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects."
    )
    return [
        FixtureSpec(
            fixture_id="realistic_clean_lager",
            sample_type="realistic",
            source="manual-curation",
            scenario="single_pass",
            notes="Realistic production-ready label with exact legal warning text.",
            truth={
                "brand_name": "North Coast Lager",
                "class_type": "MALT BEVERAGE",
                "alcohol_content": "5.0% alc/vol",
                "net_contents": "12 fl oz",
                "government_warning": warning,
            },
            extracted={
                "brand_name": "North Coast Lager",
                "class_type": "MALT BEVERAGE",
                "alcohol_content": "5.0% alc/vol",
                "net_contents": "12 fl oz",
                "government_warning": warning,
            },
            expected={
                "overall_status": "pass",
                "field_statuses": {
                    "brand_name": "pass",
                    "class_type": "pass",
                    "alcohol_content": "pass",
                    "net_contents": "pass",
                    "government_warning": "pass",
                },
            },
        ),
        FixtureSpec(
            fixture_id="generated_citrus_ipa",
            sample_type="generated",
            source="synthetic-generator",
            scenario="single_pass",
            notes="Synthetic but valid label values generated for normal OCR pathways.",
            truth={
                "brand_name": "Citrus Bloom IPA",
                "class_type": "MALT BEVERAGE",
                "alcohol_content": "6.2% alc/vol",
                "net_contents": "16 fl oz",
                "government_warning": warning,
            },
            extracted={
                "brand_name": "Citrus Bloom IPA",
                "class_type": "MALT BEVERAGE",
                "alcohol_content": "6.2% alc/vol",
                "net_contents": "16 fl oz",
                "government_warning": warning,
            },
            expected={
                "overall_status": "pass",
                "field_statuses": {
                    "brand_name": "pass",
                    "class_type": "pass",
                    "alcohol_content": "pass",
                    "net_contents": "pass",
                    "government_warning": "pass",
                },
            },
        ),
        FixtureSpec(
            fixture_id="adversarial_warning_typo",
            sample_type="adversarial",
            source="targeted-mutation",
            scenario="review_required",
            notes="Single-character warning typo designed to trigger review_required outcome.",
            truth={
                "brand_name": "Ridge Trail Ale",
                "class_type": "MALT BEVERAGE",
                "alcohol_content": "5.8% alc/vol",
                "net_contents": "12 fl oz",
                "government_warning": warning,
            },
            extracted={
                "brand_name": "Ridge Trail Ale",
                "class_type": "MALT BEVERAGE",
                "alcohol_content": "5.8% alc/vol",
                "net_contents": "12 fl oz",
                "government_warning": warning.replace("alcoholic", "alcoh0lic"),
            },
            expected={
                "overall_status": "review_required",
                "field_statuses": {
                    "brand_name": "pass",
                    "class_type": "pass",
                    "alcohol_content": "pass",
                    "net_contents": "pass",
                    "government_warning": "review_required",
                },
            },
        ),
        FixtureSpec(
            fixture_id="adversarial_wrong_abv",
            sample_type="adversarial",
            source="targeted-mutation",
            scenario="single_fail",
            notes="ABV mismatch and warning mismatch trigger fail outcomes.",
            truth={
                "brand_name": "Fogline Stout",
                "class_type": "MALT BEVERAGE",
                "alcohol_content": "9.0% alc/vol",
                "net_contents": "12 fl oz",
                "government_warning": warning,
            },
            extracted={
                "brand_name": "Fogline Stout",
                "class_type": "MALT BEVERAGE",
                "alcohol_content": "5.0% alc/vol",
                "net_contents": "12 fl oz",
                "government_warning": "Drink responsibly.",
            },
            expected={
                "overall_status": "fail",
                "field_statuses": {
                    "brand_name": "pass",
                    "class_type": "pass",
                    "alcohol_content": "fail",
                    "net_contents": "pass",
                    "government_warning": "fail",
                },
            },
        ),
        FixtureSpec(
            fixture_id="generated_retry_then_review",
            sample_type="generated",
            source="synthetic-generator",
            scenario="retry_then_review",
            notes="Used by batch retry workflow where second attempt still requires review.",
            truth={
                "brand_name": "Blue Horizon Pils",
                "class_type": "MALT BEVERAGE",
                "alcohol_content": "4.6% alc/vol",
                "net_contents": "12 fl oz",
                "government_warning": warning,
            },
            extracted={
                "brand_name": "Blue Horizon Pils",
                "class_type": "MALT BEVERAGE",
                "alcohol_content": "4.6% alc/vol",
                "net_contents": "12 fl oz",
                "government_warning": f"{warning} ",
            },
            expected={
                "overall_status": "review_required",
                "field_statuses": {
                    "brand_name": "pass",
                    "class_type": "pass",
                    "alcohol_content": "pass",
                    "net_contents": "pass",
                    "government_warning": "review_required",
                },
            },
        ),
    ]


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _repo_relative_path(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _write_fixture_files(
    fixtures_dir: Path, fixture_specs: list[FixtureSpec], repo_root: Path
) -> list[dict[str, str]]:
    images_dir = fixtures_dir / "labels/images"
    forms_dir = fixtures_dir / "labels/forms"
    truth_dir = fixtures_dir / "labels/truth"
    expected_dir = fixtures_dir / "labels/expected"

    for directory in (images_dir, forms_dir, truth_dir, expected_dir):
        directory.mkdir(parents=True, exist_ok=True)

    manifest_fixtures: list[dict[str, str]] = []
    for spec in fixture_specs:
        image_path = images_dir / f"{spec.fixture_id}.png"
        form_path = forms_dir / f"{spec.fixture_id}.json"
        truth_path = truth_dir / f"{spec.fixture_id}.json"
        expected_path = expected_dir / f"{spec.fixture_id}.json"

        image_path.write_bytes(PNG_1X1_TRANSPARENT)
        _write_json(form_path, spec.extracted)
        _write_json(truth_path, spec.truth)
        _write_json(expected_path, spec.expected)

        manifest_fixtures.append(
            {
                "fixture_id": spec.fixture_id,
                "sample_type": spec.sample_type,
                "source": spec.source,
                "scenario": spec.scenario,
                "notes": spec.notes,
                "image": _repo_relative_path(image_path, repo_root),
                "form": _repo_relative_path(form_path, repo_root),
                "truth": _repo_relative_path(truth_path, repo_root),
                "expected": _repo_relative_path(expected_path, repo_root),
            }
        )

    return manifest_fixtures


def _write_manifest(fixtures_dir: Path, fixtures: list[dict[str, str]]) -> None:
    manifest = {
        "schema_version": 1,
        "description": "Hermetic offline fixture dataset for alcohol label verification.",
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "fixtures": fixtures,
    }
    _write_json(fixtures_dir / "labels/fixtures_manifest.json", manifest)


def _write_batch_csv_fixtures(fixtures_dir: Path) -> None:
    batch_dir = fixtures_dir / "batch"
    batch_dir.mkdir(parents=True, exist_ok=True)

    headers = [
        "fixture_id",
        "image_path",
        "form_path",
        "truth_path",
        "expected_path",
        "scenario",
    ]

    datasets: dict[str, list[list[str]]] = {
        "batch_all_pass.csv": [
            [
                "realistic_clean_lager",
                "tests/fixtures/labels/images/realistic_clean_lager.png",
                "tests/fixtures/labels/forms/realistic_clean_lager.json",
                "tests/fixtures/labels/truth/realistic_clean_lager.json",
                "tests/fixtures/labels/expected/realistic_clean_lager.json",
                "single_pass",
            ],
            [
                "generated_citrus_ipa",
                "tests/fixtures/labels/images/generated_citrus_ipa.png",
                "tests/fixtures/labels/forms/generated_citrus_ipa.json",
                "tests/fixtures/labels/truth/generated_citrus_ipa.json",
                "tests/fixtures/labels/expected/generated_citrus_ipa.json",
                "single_pass",
            ],
        ],
        "batch_mixed_results.csv": [
            [
                "realistic_clean_lager",
                "tests/fixtures/labels/images/realistic_clean_lager.png",
                "tests/fixtures/labels/forms/realistic_clean_lager.json",
                "tests/fixtures/labels/truth/realistic_clean_lager.json",
                "tests/fixtures/labels/expected/realistic_clean_lager.json",
                "single_pass",
            ],
            [
                "adversarial_warning_typo",
                "tests/fixtures/labels/images/adversarial_warning_typo.png",
                "tests/fixtures/labels/forms/adversarial_warning_typo.json",
                "tests/fixtures/labels/truth/adversarial_warning_typo.json",
                "tests/fixtures/labels/expected/adversarial_warning_typo.json",
                "review_required",
            ],
            [
                "adversarial_wrong_abv",
                "tests/fixtures/labels/images/adversarial_wrong_abv.png",
                "tests/fixtures/labels/forms/adversarial_wrong_abv.json",
                "tests/fixtures/labels/truth/adversarial_wrong_abv.json",
                "tests/fixtures/labels/expected/adversarial_wrong_abv.json",
                "single_fail",
            ],
        ],
        "batch_with_missing_file.csv": [
            [
                "realistic_clean_lager",
                "tests/fixtures/labels/images/realistic_clean_lager.png",
                "tests/fixtures/labels/forms/realistic_clean_lager.json",
                "tests/fixtures/labels/truth/realistic_clean_lager.json",
                "tests/fixtures/labels/expected/realistic_clean_lager.json",
                "single_pass",
            ],
            [
                "missing_fixture_image",
                "tests/fixtures/labels/images/missing_fixture_image.png",
                "tests/fixtures/labels/forms/generated_citrus_ipa.json",
                "tests/fixtures/labels/truth/generated_citrus_ipa.json",
                "tests/fixtures/labels/expected/generated_citrus_ipa.json",
                "missing_file",
            ],
        ],
        "batch_with_retry_then_review.csv": [
            [
                "generated_retry_then_review",
                "tests/fixtures/labels/images/generated_retry_then_review.png",
                "tests/fixtures/labels/forms/generated_retry_then_review.json",
                "tests/fixtures/labels/truth/generated_retry_then_review.json",
                "tests/fixtures/labels/expected/generated_retry_then_review.json",
                "retry_then_review",
            ]
        ],
    }

    for filename, rows in datasets.items():
        csv_path = batch_dir / filename
        with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(headers)
            writer.writerows(rows)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    fixtures_dir = repo_root / "tests/fixtures"
    fixture_specs = _build_fixture_specs()
    manifest_fixtures = _write_fixture_files(fixtures_dir, fixture_specs, repo_root)
    _write_manifest(fixtures_dir, manifest_fixtures)
    _write_batch_csv_fixtures(fixtures_dir)


if __name__ == "__main__":
    main()
