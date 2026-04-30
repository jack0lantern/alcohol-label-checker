import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "tests/fixtures/labels"


def test_batch_websocket_streams_progress_events() -> None:
    app = create_app()
    client = TestClient(app)

    pdf_path = FIXTURES_ROOT / "forms/realistic_clean_lager_f510031.pdf"
    image_path = FIXTURES_ROOT / "images/realistic_clean_lager.png"

    mapping = json.dumps({
        "items": [
            {
                "item_id": "item-1",
                "form_filename": pdf_path.name,
                "label_filenames": [image_path.name],
            },
            {
                "item_id": "item-2",
                "form_filename": pdf_path.name,
                "label_filenames": [image_path.name],
            },
            {
                "item_id": "item-3",
                "form_filename": "broken_form.pdf",
                "label_filenames": [image_path.name],
            },
        ]
    })

    with pdf_path.open("rb") as form_file, image_path.open("rb") as label_file:
        create_response = client.post(
            "/verify/batch",
            data={"mapping": mapping},
            files=[
                ("files", (pdf_path.name, form_file, "application/pdf")),
                ("files", (image_path.name, label_file, "image/png")),
                ("files", ("broken_form.pdf", b"not-a-pdf", "application/pdf")),
            ],
        )
    assert create_response.status_code == 202
    job_id = create_response.json()["job_id"]

    events: list[dict[str, object]] = []
    with client.websocket_connect(f"/verify/batch/{job_id}/events") as websocket:
        while True:
            event = websocket.receive_json()
            events.append(event)
            if event["event_type"] == "job_completed":
                break

    assert len(events) >= 3
    assert events[0]["job_id"] == job_id
    item_processed_events = [event for event in events if event["event_type"] == "item_processed"]
    assert len(item_processed_events) == 3
    processed_lifecycle_matrix = {event["item_id"]: event["status"] for event in item_processed_events}
    assert processed_lifecycle_matrix == {
        "item-1": "completed",
        "item-2": "completed",
        "item-3": "review_required",
    }
    processed_outcome_matrix = {event["item_id"]: event["overall_status"] for event in item_processed_events}
    assert processed_outcome_matrix["item-3"] == "review_required"
    assert processed_outcome_matrix["item-1"] in {"pass", "fail", "review_required"}
    assert processed_outcome_matrix["item-2"] in {"pass", "fail", "review_required"}
    assert events[-1]["event_type"] == "job_completed"
    assert events[-1]["processed"] == events[-1]["total"]
    assert events[-1]["status"] == "completed_with_failures"
