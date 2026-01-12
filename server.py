"""FastAPI backend for metrics and health checks."""
import json
import os
from datetime import datetime
from pathlib import Path

import structlog
from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()
log = structlog.get_logger()

app = FastAPI(title="Neurality Health Voice Agent")

AUDIT_DIR = Path(__file__).parent / "sample_outputs"


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/metrics")
async def metrics():
    """Metrics from audit files."""
    if not AUDIT_DIR.exists():
        return {"calls": {"total": 0, "booked": 0, "not_booked": 0}, "performance": {}}

    total = 0
    booked = 0
    durations = []
    tool_latencies = []

    for file in AUDIT_DIR.glob("call-*.json"):
        try:
            data = json.loads(file.read_text())
            total += 1

            if data.get("outcome", {}).get("booked"):
                booked += 1

            # Duration
            started = data.get("started_at")
            ended = data.get("ended_at")
            if started and ended:
                start_dt = datetime.fromisoformat(started)
                end_dt = datetime.fromisoformat(ended)
                durations.append((end_dt - start_dt).total_seconds())

            # Tool latencies
            for trace in data.get("tool_trace", []):
                if "duration_ms" in trace:
                    tool_latencies.append(trace["duration_ms"])
        except Exception:
            continue

    return {
        "calls": {
            "total": total,
            "booked": booked,
            "not_booked": total - booked,
        },
        "performance": {
            "avg_call_duration_sec": round(sum(durations) / len(durations), 2) if durations else 0,
            "total_tool_calls": len(tool_latencies),
            "avg_tool_latency_ms": round(sum(tool_latencies) / len(tool_latencies), 2) if tool_latencies else 0,
        },
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
