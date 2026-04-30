import base64
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "tests/fixtures/labels"


def _b64_pdf(name: str) -> str:
    return base64.b64encode((FIXTURES_ROOT / "forms" / name).read_bytes()).decode("ascii")


def _b64_image(name: str) -> str:
    return base64.b64encode((FIXTURES_ROOT / "images" / name).read_bytes()).decode("ascii")


def test_batch_websocket_streams_progress_events() -> None:
    app = create_app()
    client = TestClient(app)

    create_response = client.post(
        "/verify/batch",
        json={
            "items": [
                {
                    "item_id": "item-1",
                    "form_payload": {"pdf_base64": _b64_pdf("realistic_clean_lager_f510031.pdf")},
                    "label_payloads": [{"image_base64": _b64_image("realistic_clean_lager.png")}],
                },
                {
                    "item_id": "item-2",
                    "form_payload": {"pdf_base64": _b64_pdf("realistic_clean_lager_f510031.pdf")},
                    "label_payloads": [{"image_base64": _b64_image("realistic_clean_lager.png")}],
                },
                {
                    "item_id": "item-3",
                    "form_payload": {"pdf_base64": _b64_pdf("realistic_clean_lager_f510031.pdf")},
                    "label_payloads": ["invalid-json-object"],
                },
            ]
        },
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
