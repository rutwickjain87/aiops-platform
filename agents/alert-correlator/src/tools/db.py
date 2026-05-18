"""
PostgreSQL / pgvector client for the Alert Correlator.
Handles connection lifecycle, alert upserts, and vector similarity queries.
"""
import os
import json
import logging
from typing import Optional
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector

log = logging.getLogger(__name__)


def _conn_params() -> dict:
    return {
        "host": os.environ.get("PGHOST", "localhost"),
        "port": int(os.environ.get("PGPORT", 5432)),
        "dbname": os.environ.get("PGDATABASE", "alerts"),
        "user": os.environ.get("PGUSER", "alertcorr"),
        "password": os.environ.get("PGPASSWORD", "alertcorr"),
    }


@contextmanager
def get_conn():
    """Context manager — yields a psycopg2 connection, auto-commits or rolls back."""
    conn = psycopg2.connect(**_conn_params())
    register_vector(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Alert persistence
# ---------------------------------------------------------------------------

def upsert_alert(conn, alert: dict, embedding: list[float]) -> int:
    """
    Insert or update an alert row. Returns the row id.
    Conflicts on fingerprint → updates embedding and received_at.
    """
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})
    fingerprint = alert["fingerprint"]
    alertname = labels.get("alertname", "unknown")
    severity = labels.get("severity", "warning")
    started_at = alert.get("startsAt")

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO alerts
                (fingerprint, name, severity, labels, annotations, started_at, embedding, status)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (fingerprint) DO UPDATE SET
                embedding   = EXCLUDED.embedding,
                received_at = NOW(),
                status      = EXCLUDED.status
            RETURNING id
            """,
            (
                fingerprint,
                alertname,
                severity,
                json.dumps(labels),
                json.dumps(annotations),
                started_at,
                embedding,
                alert.get("status", "firing"),
            ),
        )
        row_id = cur.fetchone()[0]
    log.debug("Upserted alert id=%d fingerprint=%s", row_id, fingerprint)
    return row_id


# ---------------------------------------------------------------------------
# Similarity search
# ---------------------------------------------------------------------------

def _colocation_filter(labels: dict) -> tuple[str, tuple]:
    """
    Build a SQL WHERE clause fragment that requires candidate alerts to share
    at least one scope label (namespace, service, or node) with the anchor.

    Why: MiniLM detects structural similarity ("something is down") across
    unrelated namespaces, producing false-positive clusters. Requiring shared
    scope pins correlation to the same blast radius before even checking vectors.

    Returns (clause_str, params_tuple). If no scope labels found, returns
    empty strings so the query runs without any co-location constraint.
    """
    namespace = labels.get("namespace", "")
    service = labels.get("service", labels.get("job", ""))
    node = labels.get("node", "")

    conditions = []
    params = []

    if namespace:
        conditions.append("labels->>'namespace' = %s")
        params.append(namespace)
    if service:
        conditions.append("(labels->>'service' = %s OR labels->>'job' = %s)")
        params.extend([service, service])
    if node:
        conditions.append("labels->>'node' = %s")
        params.append(node)

    if not conditions:
        return "", ()

    # OR between conditions: match if sharing ANY of namespace, service, or node
    clause = "AND (" + " OR ".join(conditions) + ")"
    return clause, tuple(params)


def query_similar_alerts(
    conn,
    embedding: list[float],
    window_minutes: int,
    threshold: float,
    limit: int,
    exclude_fingerprint: Optional[str] = None,
    anchor_labels: Optional[dict] = None,
) -> list[dict]:
    """
    Return alerts within the time window whose embedding cosine similarity
    to `embedding` is >= threshold, ordered by similarity descending.

    Co-location pre-filter (anchor_labels):
      If provided, only considers alerts that share at least one of:
      namespace, service, or node with the anchor alert.
      This prevents cross-namespace structural false positives
      (e.g. CronJobFailed in 'batch' matching TargetDown in 'monitoring'
      just because both describe "something is down").
    """
    # Build the co-location filter clause from anchor labels
    colocation_clause, colocation_params = _colocation_filter(anchor_labels or {})

    exclude_clause = "AND fingerprint != %s" if exclude_fingerprint else ""
    exclude_params = (exclude_fingerprint,) if exclude_fingerprint else ()

    sql = f"""
        SELECT * FROM (
            SELECT
                id,
                fingerprint,
                name,
                severity,
                labels,
                annotations,
                started_at,
                received_at,
                status,
                1 - (embedding <=> %s::vector) AS similarity
            FROM alerts
            WHERE
                received_at >= NOW() - INTERVAL '%s minutes'
                AND status = 'firing'
                AND embedding IS NOT NULL
                {exclude_clause}
                {colocation_clause}
        ) sub
        WHERE similarity >= %s
        ORDER BY similarity DESC
        LIMIT %s
    """
    params = (
        embedding,
        window_minutes,
        *exclude_params,
        *colocation_params,
        threshold,
        limit,
    )

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    result = []
    for row in rows:
        d = dict(row)
        d["labels"] = d["labels"] if isinstance(d["labels"], dict) else json.loads(d["labels"])
        d["annotations"] = d["annotations"] if isinstance(d["annotations"], dict) else json.loads(d["annotations"])
        result.append(d)
    return result


# ---------------------------------------------------------------------------
# Incident persistence
# ---------------------------------------------------------------------------

def insert_incident(conn, incident: dict) -> int:
    """Persist a new incident. Returns the row id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO incidents
                (incident_id, title, severity, alert_ids, root_cause, summary)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (incident_id) DO NOTHING
            RETURNING id
            """,
            (
                incident["incident_id"],
                incident["title"],
                incident["severity"],
                incident["alert_ids"],
                incident.get("root_cause"),
                incident.get("summary"),
            ),
        )
        row = cur.fetchone()
    return row[0] if row else -1


def get_alert_count(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM alerts")
        return cur.fetchone()[0]
