"""FastAPI backend for metrics and health checks."""
import os
import time

import structlog
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request

load_dotenv()
log = structlog.get_logger()

app = FastAPI(title="Neurality Health Voice Agent")

# Simple metrics tracking
_metrics = {
    "calls_total": 0,
    "calls_completed": 0,
    "calls_failed": 0,
    "call_durations_sec": [],
}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/metrics")
async def metrics():
    """Metrics endpoint for monitoring."""
    durations = _metrics["call_durations_sec"]

    return {
        "calls": {
            "total": _metrics["calls_total"],
            "completed": _metrics["calls_completed"],
            "failed": _metrics["calls_failed"],
        },
        "call_duration": {
            "avg_sec": sum(durations) / len(durations) if durations else 0,
            "total_calls_with_duration": len(durations),
        },
    }


@app.post("/voice/status")
async def voice_status(
    request: Request,
    CallSid: str = Form(default=""),
    CallStatus: str = Form(default=""),
    Duration: str = Form(default=""),
):
    """
    Twilio call status webhook (optional).
    Configure in Twilio to track call outcomes.
    """
    log.info(
        "call_status_update",
        call_sid=CallSid,
        status=CallStatus,
        duration=Duration,
    )

    _metrics["calls_total"] += 1

    if CallStatus == "completed":
        _metrics["calls_completed"] += 1
        if Duration:
            try:
                _metrics["call_durations_sec"].append(int(Duration))
            except ValueError:
                pass
    elif CallStatus in ("failed", "busy", "no-answer"):
        _metrics["calls_failed"] += 1

    return {"received": True}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
