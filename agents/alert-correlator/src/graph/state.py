"""LangGraph state shape for the Alert Correlator pipeline."""
from typing import Optional, TypedDict


class AlertCorrelatorState(TypedDict):
    # --- Input ---
    raw_alerts: list[dict]          # List of AlertManager-format alert dicts

    # --- After ingest ---
    parsed_alerts: list[dict]       # Validated and normalised alerts

    # --- After embed ---
    embedded_alerts: list[dict]     # Each dict: {alert, alert_id, embedding}

    # --- After query_similar ---
    similarity_groups: list[dict]   # Each: {anchor_alert_id, similar_alert_ids, scores}

    # --- After cluster ---
    clusters: list[dict]            # Each: {alert_ids, severity, representative_alert}

    # --- After emit_incident ---
    incidents: list[dict]           # Structured incident dicts ready for downstream

    # --- Metadata ---
    errors: list[str]               # Non-fatal errors accumulated through the pipeline
    stats: dict                     # Counts: parsed, embedded, similar_found, clusters, incidents
