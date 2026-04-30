from fastapi.testclient import TestClient

from app.main import create_app


def test_batch_websocket_streams_progress_events() -> None:
    app = create_app()
    client = TestClient(app)

    warning_text = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects."
    )

    create_response = client.post(
        "/verify/batch",
        json={
            "items": [
                {
                    "item_id": "item-1",
                    "form_payload": {
                        "brand_name": "A",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    },
                    "label_payloads": [{
                        "brand_name": "A",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    }],
                },
                {
                    "item_id": "item-2",
                    "form_payload": {
                        "brand_name": "B",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    },
                    "label_payloads": [{
                        "brand_name": "DIFFERENT",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    }],
                },
                {
                    "item_id": "item-3",
                    "form_payload": {
                        "brand_name": "C",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    },
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
    assert processed_outcome_matrix == {
        "item-1": "pass",
        "item-2": "fail",
        "item-3": "review_required",
    }
    assert events[-1]["event_type"] == "job_completed"
    assert events[-1]["status"] == "completed_with_failures"
    assert events[-1]["processed"] == events[-1]["total"]
