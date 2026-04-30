from app.domain.models import GroundTruthFields, LabelExtractedFields
from app.services import matcher
from app.services.matcher import WARNING_REVIEW_THRESHOLD, match_fields


def test_general_fields_compare_case_insensitively() -> None:
    truth = GroundTruthFields(
        brand_name="Acme Brewing",
        class_type="MALT BEVERAGE",
        alcohol_content="5% alc/vol",
        net_contents="12 fl oz",
        government_warning=(
            "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic "
            "beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic "
            "beverages impairs your ability to drive a car or operate machinery, and may cause health problems."
        ),
    )
    extracted = LabelExtractedFields(
        brand_name="acme brewing",
        class_type="malt beverage",
        alcohol_content="5% ALC/VOL",
        net_contents="12 FL OZ",
        government_warning=(
            "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic "
            "beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic "
            "beverages impairs your ability to drive a car or operate machinery, and may cause health problems."
        ),
    )

    result = match_fields(truth, extracted)

    assert result["brand_name"].status == "pass"
    assert result["class_type"].status == "pass"
    assert result["alcohol_content"].status == "pass"
    assert result["net_contents"].status == "pass"


def test_government_warning_exact_match_passes() -> None:
    warning = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
        "operate machinery, and may cause health problems."
    )
    truth = GroundTruthFields(
        brand_name="Acme Brewing",
        class_type="MALT BEVERAGE",
        alcohol_content="5% alc/vol",
        net_contents="12 fl oz",
        government_warning=warning,
    )
    extracted = LabelExtractedFields(
        brand_name="Acme Brewing",
        class_type="MALT BEVERAGE",
        alcohol_content="5% alc/vol",
        net_contents="12 fl oz",
        government_warning=warning,
    )

    result = match_fields(truth, extracted)

    assert result["government_warning"].status == "pass"


def test_government_warning_whitespace_difference_not_exact_pass() -> None:
    warning = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
        "operate machinery, and may cause health problems."
    )
    truth = GroundTruthFields(
        brand_name="Acme Brewing",
        class_type="MALT BEVERAGE",
        alcohol_content="5% alc/vol",
        net_contents="12 fl oz",
        government_warning=warning,
    )
    extracted = LabelExtractedFields(
        brand_name="Acme Brewing",
        class_type="MALT BEVERAGE",
        alcohol_content="5% alc/vol",
        net_contents="12 fl oz",
        government_warning=f"{warning} ",
    )

    result = match_fields(truth, extracted)

    assert result["government_warning"].status == "review_required"


def test_government_warning_high_similarity_requires_review() -> None:
    truth_warning = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
        "operate machinery, and may cause health problems."
    )
    extracted_warning = truth_warning.replace("alcoholic", "alcoh0lic", 1)
    truth = GroundTruthFields(
        brand_name="Acme Brewing",
        class_type="MALT BEVERAGE",
        alcohol_content="5% alc/vol",
        net_contents="12 fl oz",
        government_warning=truth_warning,
    )
    extracted = LabelExtractedFields(
        brand_name="Acme Brewing",
        class_type="MALT BEVERAGE",
        alcohol_content="5% alc/vol",
        net_contents="12 fl oz",
        government_warning=extracted_warning,
    )

    result = match_fields(truth, extracted)

    assert result["government_warning"].status == "review_required"


def test_government_warning_low_similarity_fails() -> None:
    truth_warning = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
        "operate machinery, and may cause health problems."
    )
    extracted_warning = "Drink responsibly."
    truth = GroundTruthFields(
        brand_name="Acme Brewing",
        class_type="MALT BEVERAGE",
        alcohol_content="5% alc/vol",
        net_contents="12 fl oz",
        government_warning=truth_warning,
    )
    extracted = LabelExtractedFields(
        brand_name="Acme Brewing",
        class_type="MALT BEVERAGE",
        alcohol_content="5% alc/vol",
        net_contents="12 fl oz",
        government_warning=extracted_warning,
    )

    result = match_fields(truth, extracted)

    assert result["government_warning"].status == "fail"


def test_general_field_none_values_do_not_crash() -> None:
    truth = GroundTruthFields(
        brand_name=None,
        class_type="MALT BEVERAGE",
        alcohol_content=None,
        net_contents="12 fl oz",
        government_warning="GOVERNMENT WARNING",
    )
    extracted = LabelExtractedFields(
        brand_name=None,
        class_type="malt beverage",
        alcohol_content="",
        net_contents="12 FL OZ",
        government_warning="GOVERNMENT WARNING",
    )

    result = match_fields(truth, extracted)

    assert result["brand_name"].status == "pass"
    assert result["alcohol_content"].status == "pass"


def test_government_warning_none_does_not_crash() -> None:
    truth = GroundTruthFields(
        brand_name="Acme Brewing",
        class_type="MALT BEVERAGE",
        alcohol_content="5% alc/vol",
        net_contents="12 fl oz",
        government_warning=None,
    )
    extracted = LabelExtractedFields(
        brand_name="Acme Brewing",
        class_type="MALT BEVERAGE",
        alcohol_content="5% alc/vol",
        net_contents="12 fl oz",
        government_warning="GOVERNMENT WARNING",
    )

    result = match_fields(truth, extracted)

    assert result["government_warning"].status == "fail"


def test_government_warning_both_none_is_not_pass() -> None:
    truth = GroundTruthFields(
        brand_name="Acme Brewing",
        class_type="MALT BEVERAGE",
        alcohol_content="5% alc/vol",
        net_contents="12 fl oz",
        government_warning=None,
    )
    extracted = LabelExtractedFields(
        brand_name="Acme Brewing",
        class_type="MALT BEVERAGE",
        alcohol_content="5% alc/vol",
        net_contents="12 fl oz",
        government_warning=None,
    )

    result = match_fields(truth, extracted)

    assert result["government_warning"].status != "pass"


def test_government_warning_both_empty_is_not_pass() -> None:
    truth = GroundTruthFields(
        brand_name="Acme Brewing",
        class_type="MALT BEVERAGE",
        alcohol_content="5% alc/vol",
        net_contents="12 fl oz",
        government_warning="",
    )
    extracted = LabelExtractedFields(
        brand_name="Acme Brewing",
        class_type="MALT BEVERAGE",
        alcohol_content="5% alc/vol",
        net_contents="12 fl oz",
        government_warning="",
    )

    result = match_fields(truth, extracted)

    assert result["government_warning"].status != "pass"


def test_warning_similarity_equal_threshold_is_review_required(
    monkeypatch,
) -> None:
    class SequenceMatcherAtThreshold:
        def __init__(self, _isjunk, _expected, _extracted) -> None:
            pass

        def ratio(self) -> float:
            return WARNING_REVIEW_THRESHOLD

    monkeypatch.setattr(matcher, "SequenceMatcher", SequenceMatcherAtThreshold)

    status = matcher._match_government_warning("A", "B")

    assert status == "review_required"


def test_warning_similarity_below_threshold_is_fail(monkeypatch) -> None:
    class SequenceMatcherBelowThreshold:
        def __init__(self, _isjunk, _expected, _extracted) -> None:
            pass

        def ratio(self) -> float:
            return WARNING_REVIEW_THRESHOLD - 0.001

    monkeypatch.setattr(matcher, "SequenceMatcher", SequenceMatcherBelowThreshold)

    status = matcher._match_government_warning("A", "B")

    assert status == "fail"
