from dataclasses import dataclass, field
from typing import Literal

MatchStatus = Literal["pass", "fail", "review_required"]
JobStatus = Literal["queued", "running", "completed", "completed_with_failures"]
ItemStatus = Literal["queued", "processing", "retrying", "completed", "review_required"]


@dataclass(slots=True)
class GroundTruthFields:
    brand_name: str
    class_type: str
    alcohol_content: str
    net_contents: str
    government_warning: str

    def general_fields(self) -> dict[str, str]:
        return {
            "brand_name": self.brand_name,
            "class_type": self.class_type,
            "alcohol_content": self.alcohol_content,
            "net_contents": self.net_contents,
        }


@dataclass(slots=True)
class LabelExtractedFields:
    brand_name: str
    class_type: str
    alcohol_content: str
    net_contents: str
    government_warning: str

    def general_fields(self) -> dict[str, str]:
        return {
            "brand_name": self.brand_name,
            "class_type": self.class_type,
            "alcohol_content": self.alcohol_content,
            "net_contents": self.net_contents,
        }


@dataclass(slots=True)
class FieldResult:
    field_name: str
    expected_value: str
    extracted_value: str
    status: MatchStatus


@dataclass(slots=True)
class ItemResult:
    item_id: str
    status: ItemStatus
    field_results: dict[str, FieldResult] = field(default_factory=dict)


@dataclass(slots=True)
class BatchJobState:
    job_id: str
    status: JobStatus
    item_results: dict[str, ItemResult] = field(default_factory=dict)
