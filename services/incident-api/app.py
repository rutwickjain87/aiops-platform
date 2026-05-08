# app.py — FastAPI entry point for the Incident API microservice
# Exposes REST endpoints consumed by the AIOps platform dashboard.

from __future__ import annotations

import db
import utils
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

app = FastAPI(title="Incident API", version="0.1.0")


# ── Models ────────────────────────────────────────────────────────────────────

class CreateIncidentRequest(BaseModel):
    title: str
    service: str
    severity: str       # expected: P1 | P2 | P3 | P4
    description: str


class AlertRuleRequest(BaseModel):
    expression: str     # e.g. "error_rate > 0.05 and latency_p99 > 500"
    context: dict       # metric values to evaluate against


class AlertConfigRequest(BaseModel):
    yaml_config: str    # raw YAML string from user


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str):
    """Get a single incident by ID."""
    incident = db.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@app.get("/incidents")
def search_incidents(
    service: str = Query(..., description="Service name"),
    severity: str = Query(..., description="Severity level"),
):
    """Search incidents by service and severity."""
    return db.search_incidents(service, severity)


@app.post("/incidents")
def create_incident(req: CreateIncidentRequest):
    """Create a new incident."""
    incident_id = db.create_incident(
        title=req.title,
        service=req.service,
        severity=req.severity,
        description=req.description,
    )
    return {"id": incident_id, "status": "created"}


@app.get("/logs")
def get_logs(
    service: str = Query(..., description="Service name (maps to /var/log/incident-api/<service>.log)"),
    lines: int = Query(100, description="Number of lines to return"),
):
    """Tail the log file for a given service."""
    try:
        return {"log": utils.read_service_log(service, lines)}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"No log file found for service '{service}'")


@app.get("/healthcheck")
def healthcheck(host: str = Query(..., description="Hostname to ping")):
    """Ping a host and return latency info."""
    return utils.ping_host(host)


@app.post("/alerts/evaluate")
def evaluate_alert(req: AlertRuleRequest):
    """Evaluate an alert rule expression against a context dict."""
    try:
        result = utils.evaluate_alert_rule(req.expression, req.context)
        return {"expression": req.expression, "result": result, "fires": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/alerts/config")
def load_alert_config(req: AlertConfigRequest):
    """Parse and validate an alert YAML config."""
    try:
        config = utils.load_alert_config(req.yaml_config)
        return {"parsed": config, "valid": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    import config as cfg
    import uvicorn
    uvicorn.run(app, host=cfg.HOST, port=cfg.PORT, reload=cfg.DEBUG)
