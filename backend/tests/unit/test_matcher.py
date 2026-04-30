from app.domain.models import GroundTruthFields, LabelExtractedFields
from app.services.matcher import match_fields


def test_general_fields_compare_case_insensitively() -> None:
    truth = GroundTruthFields(
        brand_name="Acme Brewing",
        class_type="MALT BEVERAGE",
        alcohol_content="5% alc/vol",
        net_contents="12 fl oz",
        government_warning="GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects.",
    )
    extracted = LabelExtractedFields(
        brand_name="acme brewing",
        class_type="malt beverage",
        alcohol_content="5% ALC/VOL",
        net_contents="12 FL OZ",
        government_warning="GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects.",
    )

    result = match_fields(truth, extracted)

    assert result["brand_name"].status == "pass"
    assert result["class_type"].status == "pass"
    assert result["alcohol_content"].status == "pass"
    assert result["net_contents"].status == "pass"


def test_government_warning_exact_match_passes() -> None:
    warning = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects."
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
        "alcoholic beverages during pregnancy because of the risk of birth defects."
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

    assert result["government_warning"].status in {"review_required", "fail"}


def test_government_warning_high_similarity_requires_review() -> None:
    truth_warning = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects."
    )
    extracted_warning = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoh0lic beverages during pregnancy because of the risk of birth defects."
    )
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
        "alcoholic beverages during pregnancy because of the risk of birth defects."
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
