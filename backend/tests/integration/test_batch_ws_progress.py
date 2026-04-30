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
                    "label_payload": {
                        "brand_name": "A",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    },
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
                    "label_payload": {
                        "brand_name": "B",
                        "class_type": "MALT BEVERAGE",
                        "alcohol_content": "5% alc/vol",
                        "net_contents": "12 fl oz",
                        "government_warning": warning_text,
                    },
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
    assert any(event["event_type"] == "item_processed" for event in events)
    assert events[-1]["event_type"] == "job_completed"
    assert events[-1]["processed"] == events[-1]["total"]
