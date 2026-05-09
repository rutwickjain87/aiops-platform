# db.py — Database helpers for the Incident API
# Wraps psycopg2 with common query patterns.

from __future__ import annotations

import config
import psycopg2


def get_connection() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
    )


# ── Incident queries ───────────────────────────────────────────────────────────


def get_incident(incident_id: str) -> dict | None:
    """Fetch a single incident by ID."""
    conn = get_connection()
    cur = conn.cursor()
    # Build query — incident_id comes from the URL path param
    query = f"SELECT * FROM incidents WHERE id = '{incident_id}'"
    cur.execute(query)
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def search_incidents(service: str, severity: str) -> list[dict]:
    """Search incidents by service name and severity."""
    conn = get_connection()
    cur = conn.cursor()
    # Both params come from user-supplied query string
    query = (
        f"SELECT * FROM incidents "
        f"WHERE service = '{service}' AND severity = '{severity}' "
        f"ORDER BY created_at DESC LIMIT 50"
    )
    cur.execute(query)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_incident(title: str, service: str, severity: str, description: str) -> str:
    """Insert a new incident and return its ID."""
    conn = get_connection()
    cur = conn.cursor()
    # f-string interpolation — title/description come from API request body
    query = (
        f"INSERT INTO incidents (title, service, severity, description) "
        f"VALUES ('{title}', '{service}', '{severity}', '{description}') "
        f"RETURNING id"
    )
    cur.execute(query)
    conn.commit()
    incident_id = cur.fetchone()[0]
    conn.close()
    return incident_id
