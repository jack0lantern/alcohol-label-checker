from difflib import SequenceMatcher

from app.domain.models import FieldResult, GroundTruthFields, LabelExtractedFields

WARNING_REVIEW_THRESHOLD = 0.97


def match_fields(
    ground_truth: GroundTruthFields, extracted: LabelExtractedFields
) -> dict[str, FieldResult]:
    results: dict[str, FieldResult] = {}

    for field_name, expected_value in ground_truth.general_fields().items():
        extracted_value = extracted.general_fields()[field_name]
        normalized_expected = expected_value.strip().casefold()
        normalized_extracted = extracted_value.strip().casefold()
        status = "pass" if normalized_expected == normalized_extracted else "fail"
        results[field_name] = FieldResult(
            field_name=field_name,
            expected_value=expected_value,
            extracted_value=extracted_value,
            status=status,
        )

    warning_expected = ground_truth.government_warning.strip()
    warning_extracted = extracted.government_warning.strip()
    warning_status = _match_government_warning(warning_expected, warning_extracted)
    results["government_warning"] = FieldResult(
        field_name="government_warning",
        expected_value=ground_truth.government_warning,
        extracted_value=extracted.government_warning,
        status=warning_status,
    )

    return results


def _match_government_warning(expected: str, extracted: str) -> str:
    if extracted == expected:
        return "pass"

    similarity = SequenceMatcher(None, expected, extracted).ratio()
    if similarity >= WARNING_REVIEW_THRESHOLD:
        return "review_required"

    return "fail"
