#!/usr/bin/env python3
"""
Diagnostic tool — shows pairwise cosine similarity between all stored alerts.
Run this to find the right SIMILARITY_THRESHOLD for your embedding model.

Usage:
  python diagnose_similarity.py              # read from DB
  python diagnose_similarity.py --scenario oom_cascade  # generate + embed inline (no DB needed)
"""
import sys
import json
import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env", override=True)

from src.tools.embeddings import embed_alerts, alert_to_text, MODEL


def cosine_sim(a: list[float], b: list[float]) -> float:
    """Cosine similarity (normalized vectors → dot product)."""
    return sum(x * y for x, y in zip(a, b))


def show_pairs(alerts: list[dict], embeddings: list[list[float]]) -> None:
    print(f"\nModel: {MODEL}")
    print(f"Alerts: {len(alerts)}\n")
    print("─" * 80)

    pairs = []
    for i in range(len(alerts)):
        for j in range(i + 1, len(alerts)):
            sim = cosine_sim(embeddings[i], embeddings[j])
            pairs.append((sim, i, j))
    pairs.sort(reverse=True)

    for sim, i, j in pairs:
        a_name = alerts[i]["labels"].get("alertname", "?")
        b_name = alerts[j]["labels"].get("alertname", "?")
        bar = "█" * int(sim * 30)
        print(f"  {sim:.3f}  {bar}")
        print(f"         [{i}] {a_name}")
        print(f"         [{j}] {b_name}")
        print()

    sims = [s for s, _, _ in pairs]
    print("─" * 80)
    print(f"Min: {min(sims):.3f}  Max: {max(sims):.3f}  Mean: {sum(sims)/len(sims):.3f}")
    print()

    # Threshold recommendations
    for t in [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]:
        count = sum(1 for s in sims if s >= t)
        print(f"  threshold={t:.2f} → {count}/{len(sims)} pairs match")

    print()
    print("Tip: set SIMILARITY_THRESHOLD in .env to a value that catches")
    print("all correlated pairs while leaving noise pairs below the line.")


def from_scenario(scenario_name: str) -> None:
    sys.path.insert(0, str(Path(__file__).parent))
    from synthetic.generate_alerts import generate_scenario, generate_mixed

    if scenario_name == "mixed":
        alerts = generate_mixed()
    else:
        alerts = generate_scenario(scenario_name)

    print(f"\nGenerated {len(alerts)} synthetic alerts (scenario: {scenario_name})")
    print("\nAlert texts being embedded:")
    for i, a in enumerate(alerts):
        print(f"  [{i}] {alert_to_text(a)[:100]}")

    print("\nEmbedding locally...")
    embeddings = embed_alerts(alerts)
    show_pairs(alerts, embeddings)


def from_db() -> None:
    import psycopg2
    import psycopg2.extras
    from pgvector.psycopg2 import register_vector

    conn = psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=int(os.environ.get("PGPORT", 5432)),
        dbname=os.environ.get("PGDATABASE", "alerts"),
        user=os.environ.get("PGUSER", "alertcorr"),
        password=os.environ.get("PGPASSWORD", "alertcorr"),
    )
    register_vector(conn)

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT id, name, labels, annotations, embedding
            FROM alerts
            WHERE embedding IS NOT NULL
            ORDER BY received_at DESC
            LIMIT 50
        """)
        rows = cur.fetchall()
    conn.close()

    if not rows:
        print("No alerts with embeddings found in DB. Run: make correlate first.")
        return

    alerts = [{"labels": r["labels"], "annotations": r["annotations"]} for r in rows]
    embeddings = [list(r["embedding"]) for r in rows]
    show_pairs(alerts, embeddings)


def main():
    parser = argparse.ArgumentParser(description="Diagnose similarity threshold for alert-correlator")
    parser.add_argument("--scenario", "-s",
                        choices=["oom_cascade", "node_pressure", "security_incident", "noise", "mixed"],
                        help="Generate synthetic alerts inline (no DB required)")
    args = parser.parse_args()

    if args.scenario:
        from_scenario(args.scenario)
    else:
        from_db()


if __name__ == "__main__":
    main()
