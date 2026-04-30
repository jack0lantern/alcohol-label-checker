from difflib import SequenceMatcher

from app.domain.models import FieldResult, FieldValue, GroundTruthFields, LabelExtractedFields, MatchStatus

WARNING_REVIEW_THRESHOLD = 0.97


def match_fields(
    ground_truth: GroundTruthFields, extracted: LabelExtractedFields
) -> dict[str, FieldResult]:
    results: dict[str, FieldResult] = {}

    for field_name, expected_value in ground_truth.general_fields().items():
        extracted_value = extracted.general_fields()[field_name]
        normalized_expected = _normalize_general(expected_value)
        normalized_extracted = _normalize_general(extracted_value)
        status = "pass" if normalized_expected == normalized_extracted else "fail"
        results[field_name] = FieldResult(
            field_name=field_name,
            expected_value=expected_value,
            extracted_value=extracted_value,
            status=status,
        )

    warning_expected = ground_truth.government_warning
    warning_extracted = extracted.government_warning
    warning_status = _match_government_warning(warning_expected, warning_extracted)
    results["government_warning"] = FieldResult(
        field_name="government_warning",
        expected_value=ground_truth.government_warning,
        extracted_value=extracted.government_warning,
        status=warning_status,
    )

    return results


def _match_government_warning(expected: FieldValue, extracted: FieldValue) -> MatchStatus:
    if extracted == expected:
        return "pass"

    similarity = SequenceMatcher(None, _as_similarity_text(expected), _as_similarity_text(extracted)).ratio()
    if similarity >= WARNING_REVIEW_THRESHOLD:
        return "review_required"

    return "fail"


def _normalize_general(value: FieldValue) -> str:
    if value is None:
        return ""
    return value.strip().casefold()


def _as_similarity_text(value: FieldValue) -> str:
    if value is None:
        return ""
    return value
