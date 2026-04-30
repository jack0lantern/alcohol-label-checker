import asyncio

from fastapi import APIRouter, WebSocket

from app.services.batch_manager import get_events_since, get_job_snapshot, is_job_finished

router = APIRouter()


@router.websocket("/ws/batch/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    cursor = 0

    if get_job_snapshot(job_id) is None:
        await websocket.send_json({"event_type": "error", "job_id": job_id, "message": "Batch job not found"})
        await websocket.close()
        return

    while True:
        events, cursor = get_events_since(job_id, cursor)
        for event in events:
            await websocket.send_json(event)

        if is_job_finished(job_id):
            trailing_events, cursor = get_events_since(job_id, cursor)
            for event in trailing_events:
                await websocket.send_json(event)
            break

        await asyncio.sleep(0.05)

    await websocket.close()
