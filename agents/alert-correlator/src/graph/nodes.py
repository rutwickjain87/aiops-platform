"""
LangGraph nodes for the Alert Correlator pipeline.

Pipeline:  ingest → embed → query_similar → cluster → emit_incident

Node contract: each node receives the full state dict, returns a partial dict
with only the keys it modified (LangGraph merges via reducer).
"""
import os
import logging
import hashlib
from datetime import datetime, timezone

from langchain_anthropic import ChatAnthropic

from ..tools.db import get_conn, upsert_alert, query_similar_alerts, insert_incident
from ..tools.embeddings import embed_alerts

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config from env (with sensible defaults)
# ---------------------------------------------------------------------------
WINDOW_MINUTES = int(os.environ.get("CORRELATION_WINDOW_MINUTES", 30))
THRESHOLD = float(os.environ.get("SIMILARITY_THRESHOLD", 0.85))
MAX_SIMILAR = int(os.environ.get("MAX_SIMILAR_ALERTS", 20))
MIN_CLUSTER = int(os.environ.get("MIN_CLUSTER_SIZE", 2))


# ---------------------------------------------------------------------------
# Node 1: ingest
# ---------------------------------------------------------------------------
def ingest(state: dict) -> dict:
    """
    Validate and normalise raw AlertManager payloads.
    Drops alerts missing fingerprint or alertname.
    """
    raw = state.get("raw_alerts", [])
    parsed = []
    errors = list(state.get("errors", []))

    for alert in raw:
        labels = alert.get("labels", {})
        fingerprint = alert.get("fingerprint") or _derive_fingerprint(labels)
        alertname = labels.get("alertname")
        if not alertname:
            errors.append(f"Skipped alert without alertname: {alert}")
            continue

        parsed.append({
            **alert,
            "fingerprint": fingerprint,
            "labels": {**labels, "alertname": alertname},
        })

    log.info("ingest: %d raw → %d parsed (%d skipped)", len(raw), len(parsed), len(raw) - len(parsed))
    return {
        "parsed_alerts": parsed,
        "errors": errors,
        "stats": {**(state.get("stats") or {}), "parsed": len(parsed)},
    }


def _derive_fingerprint(labels: dict) -> str:
    import json
    return hashlib.sha256(json.dumps(labels, sort_keys=True).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Node 2: embed
# ---------------------------------------------------------------------------
def embed(state: dict) -> dict:
    """
    Embed each parsed alert with Voyage AI and upsert into pgvector.
    Returns embedded_alerts: list of {alert, alert_id, embedding}.
    """
    parsed = state.get("parsed_alerts", [])
    errors = list(state.get("errors", []))

    if not parsed:
        return {"embedded_alerts": [], "errors": errors}

    try:
        vectors = embed_alerts(parsed)
    except Exception as exc:
        errors.append(f"Voyage AI embedding error: {exc}")
        return {"embedded_alerts": [], "errors": errors}

    embedded = []
    with get_conn() as conn:
        for alert, vector in zip(parsed, vectors):
            try:
                alert_id = upsert_alert(conn, alert, vector)
                embedded.append({"alert": alert, "alert_id": alert_id, "embedding": vector})
            except Exception as exc:
                errors.append(f"DB upsert error for {alert.get('fingerprint')}: {exc}")

    log.info("embed: %d alerts embedded and stored in pgvector", len(embedded))
    return {
        "embedded_alerts": embedded,
        "errors": errors,
        "stats": {**(state.get("stats") or {}), "embedded": len(embedded)},
    }


# ---------------------------------------------------------------------------
# Node 3: query_similar
# ---------------------------------------------------------------------------
def query_similar(state: dict) -> dict:
    """
    For each embedded alert, query pgvector for similar alerts within the
    time window. Builds similarity_groups.
    """
    embedded = state.get("embedded_alerts", [])
    errors = list(state.get("errors", []))
    groups = []

    with get_conn() as conn:
        for item in embedded:
            alert = item["alert"]
            alert_id = item["alert_id"]
            embedding = item["embedding"]
            fp = alert.get("fingerprint")

            try:
                similar = query_similar_alerts(
                    conn,
                    embedding=embedding,
                    window_minutes=WINDOW_MINUTES,
                    threshold=THRESHOLD,
                    limit=MAX_SIMILAR,
                    exclude_fingerprint=fp,
                    anchor_labels=alert.get("labels", {}),
                )
            except Exception as exc:
                errors.append(f"pgvector query error for alert {fp}: {exc}")
                similar = []

            if similar:
                groups.append({
                    "anchor_alert_id": alert_id,
                    "anchor_alert": alert,
                    "similar_alert_ids": [s["id"] for s in similar],
                    "similar_alerts": similar,
                    "scores": [s["similarity"] for s in similar],
                })

    similar_count = sum(len(g["similar_alert_ids"]) for g in groups)
    log.info("query_similar: found %d similarity groups (%d total similar alerts)", len(groups), similar_count)
    return {
        "similarity_groups": groups,
        "errors": errors,
        "stats": {**(state.get("stats") or {}), "similar_found": similar_count},
    }


# ---------------------------------------------------------------------------
# Node 4: cluster
# ---------------------------------------------------------------------------
def cluster(state: dict) -> dict:
    """
    Union-find clustering: merge overlapping similarity groups into incidents.
    Filters out clusters smaller than MIN_CLUSTER_SIZE.
    """
    groups = state.get("similarity_groups", [])
    embedded = state.get("embedded_alerts", [])

    # Build id → alert lookup
    id_to_alert = {item["alert_id"]: item["alert"] for item in embedded}

    # Union-Find
    parent: dict[int, int] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for group in groups:
        anchor = group["anchor_alert_id"]
        for sim_id in group["similar_alert_ids"]:
            union(anchor, sim_id)

    # Group by root
    from collections import defaultdict
    clusters_map: dict[int, set[int]] = defaultdict(set)
    all_ids = set()
    for group in groups:
        all_ids.add(group["anchor_alert_id"])
        all_ids.update(group["similar_alert_ids"])
    for alert_id in all_ids:
        clusters_map[find(alert_id)].add(alert_id)

    clusters = []
    for root, alert_ids in clusters_map.items():
        if len(alert_ids) < MIN_CLUSTER:
            continue
        # Representative: highest severity alert in cluster
        alerts_in_cluster = [id_to_alert[i] for i in alert_ids if i in id_to_alert]
        severity = _worst_severity([a.get("labels", {}).get("severity", "info") for a in alerts_in_cluster])
        rep = _pick_representative(alerts_in_cluster)
        clusters.append({
            "alert_ids": list(alert_ids),
            "representative_alert": rep,
            "severity": severity,
            "alert_count": len(alert_ids),
        })

    log.info("cluster: %d clusters (min_size=%d) from %d groups", len(clusters), MIN_CLUSTER, len(groups))
    return {
        "clusters": clusters,
        "stats": {**(state.get("stats") or {}), "clusters": len(clusters)},
    }


_SEV_ORDER = {"critical": 0, "error": 1, "warning": 2, "info": 3}

def _worst_severity(severities: list[str]) -> str:
    ranked = sorted(severities, key=lambda s: _SEV_ORDER.get(s, 99))
    return ranked[0] if ranked else "warning"

def _pick_representative(alerts: list[dict]) -> dict:
    if not alerts:
        return {}
    return sorted(alerts, key=lambda a: _SEV_ORDER.get(a.get("labels", {}).get("severity", "info"), 99))[0]


# ---------------------------------------------------------------------------
# Node 5: emit_incident
# ---------------------------------------------------------------------------
def emit_incident(state: dict) -> dict:
    """
    Use Claude to generate a structured incident title, root cause hypothesis,
    and summary for each cluster. Persist incidents to DB.
    """
    clusters = state.get("clusters", [])
    errors = list(state.get("errors", []))

    if not clusters:
        log.info("emit_incident: no clusters to process")
        return {"incidents": [], "errors": errors, "stats": {**(state.get("stats") or {}), "incidents": 0}}

    llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0, max_tokens=512)
    incidents = []

    with get_conn() as conn:
        for i, cluster in enumerate(clusters):
            rep = cluster["representative_alert"]
            labels = rep.get("labels", {})
            annotations = rep.get("annotations", {})
            alert_names = list({
                a.get("labels", {}).get("alertname", "?")
                for a in [rep]
            })

            # Summarise the cluster for the LLM
            cluster_summary = _format_cluster_for_llm(cluster)

            try:
                response = llm.invoke(
                    f"""You are an SRE incident commander. Given these correlated Kubernetes/cloud alerts, produce:
1. A concise incident title (≤10 words)
2. Root cause hypothesis (1-2 sentences)
3. A brief summary for the on-call engineer (2-3 sentences)

Respond ONLY in this exact JSON format:
{{
  "title": "...",
  "root_cause": "...",
  "summary": "..."
}}

Alerts:
{cluster_summary}"""
                )
                import json as _json
                content = response.content.strip()
                # Strip any markdown code fences if LLM adds them
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                parsed = _json.loads(content.strip())
            except Exception as exc:
                errors.append(f"LLM incident generation error for cluster {i}: {exc}")
                parsed = {
                    "title": f"Incident in {labels.get('namespace', 'unknown')} namespace",
                    "root_cause": "Could not determine root cause automatically.",
                    "summary": annotations.get("summary", ""),
                }

            incident_id = _incident_id(cluster)
            incident = {
                "incident_id": incident_id,
                "title": parsed.get("title", ""),
                "severity": cluster["severity"],
                "alert_ids": cluster["alert_ids"],
                "root_cause": parsed.get("root_cause", ""),
                "summary": parsed.get("summary", ""),
                "alert_count": cluster["alert_count"],
                "representative_alert": rep,
            }

            try:
                db_id = insert_incident(conn, incident)
                incident["db_id"] = db_id
            except Exception as exc:
                errors.append(f"Failed to persist incident {incident_id}: {exc}")

            incidents.append(incident)
            log.info("emit_incident: %s [%s] — %d alerts", incident_id, cluster["severity"], cluster["alert_count"])

    return {
        "incidents": incidents,
        "errors": errors,
        "stats": {**(state.get("stats") or {}), "incidents": len(incidents)},
    }


def _format_cluster_for_llm(cluster: dict) -> str:
    rep = cluster["representative_alert"]
    labels = rep.get("labels", {})
    annotations = rep.get("annotations", {})
    lines = [
        f"Alert count: {cluster['alert_count']}",
        f"Severity: {cluster['severity']}",
        f"Namespace: {labels.get('namespace', 'unknown')}",
        f"Representative alert: {labels.get('alertname', 'unknown')}",
        f"Summary: {annotations.get('summary', '')}",
        f"Description: {annotations.get('description', '')[:200]}",
    ]
    return "\n".join(lines)


def _incident_id(cluster: dict) -> str:
    """Generate a stable INC-YYYYMMDD-NNN id."""
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    # Use hash of sorted alert_ids for uniqueness within the day
    h = hashlib.sha256(str(sorted(cluster["alert_ids"])).encode()).hexdigest()[:4].upper()
    return f"INC-{date_str}-{h}"
