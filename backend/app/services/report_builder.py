from typing import Any


def build_batch_report(job_snapshot: dict[str, Any]) -> dict[str, Any]:
    items = job_snapshot["items"]
    summary = job_snapshot["summary"]
    review_required_count = sum(1 for item in items if item["status"] == "review_required")
    completed_count = sum(1 for item in items if item["status"] == "completed")

    return {
        "job_id": job_snapshot["job_id"],
        "status": job_snapshot["status"],
        "summary": {
            "processed": summary["processed"],
            "total": summary["total"],
            "completed": completed_count,
            "review_required": review_required_count,
        },
        "items": [
            {
                "item_id": item["item_id"],
                "status": item["status"],
                "attempts": item["attempts"],
                "overall_status": item["overall_status"],
                "field_results": item["field_results"],
                "error": item["error"],
            }
            for item in items
        ],
    }
