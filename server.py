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
        return {"calls": {"total": 0, "booked": 0, "not_booked": 0}, "performance": {}, "latency": {}}

    total = 0
    booked = 0
    durations = []
    tool_latencies = []
    ttfbs = []
    turn_latencies = []

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

            # Turn latencies (TTFB and turn)
            for turn in data.get("turns", []):
                if turn.get("ttfb_ms"):
                    ttfbs.append(turn["ttfb_ms"])
                if turn.get("turn_latency_ms"):
                    turn_latencies.append(turn["turn_latency_ms"])
        except Exception:
            continue

    # Calculate p95
    def p95(values):
        if len(values) < 2:
            return None
        sorted_vals = sorted(values)
        idx = int(len(sorted_vals) * 0.95)
        return round(sorted_vals[min(idx, len(sorted_vals) - 1)], 2)

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
        "latency": {
            "avg_ttfb_ms": round(sum(ttfbs) / len(ttfbs), 2) if ttfbs else None,
            "p95_ttfb_ms": p95(ttfbs),
            "target_ttfb_ms": 900,
            "avg_turn_latency_ms": round(sum(turn_latencies) / len(turn_latencies), 2) if turn_latencies else None,
            "p95_turn_latency_ms": p95(turn_latencies),
            "target_p95_turn_ms": 2500,
        },
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
