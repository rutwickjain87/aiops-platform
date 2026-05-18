"""
Voyage AI embedding client for alert text.
Model: voyage-3-lite (1024 dims, optimised for technical text, cheapest tier).
Batches up to 128 inputs per API call.
"""
import os
import logging
from functools import lru_cache

import voyageai

log = logging.getLogger(__name__)

MODEL = "voyage-3-lite"  # 1024 dims, good for short technical strings
BATCH_SIZE = 128          # Voyage API limit per call


@lru_cache(maxsize=1)
def _client() -> voyageai.Client:
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        raise RuntimeError("VOYAGE_API_KEY not set")
    return voyageai.Client(api_key=api_key)


def alert_to_text(alert: dict) -> str:
    """
    Convert an AlertManager alert dict to a single string for embedding.
    Format: "<alertname> severity=<sev> <label_kv_pairs> | <summary> | <description>"
    This gives Voyage AI rich signal without overwhelming it.
    """
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})

    alertname = labels.get("alertname", "unknown")
    severity = labels.get("severity", "info")

    # Extra labels (namespace, pod, service, node, etc.) — sorted for stability
    extra = " ".join(
        f"{k}={v}"
        for k, v in sorted(labels.items())
        if k not in ("alertname", "severity")
    )

    summary = annotations.get("summary", "")
    description = annotations.get("description", "")

    parts = [f"{alertname} severity={severity}"]
    if extra:
        parts.append(extra)
    parts.append("|")
    if summary:
        parts.append(summary)
    if description:
        parts.append("|")
        parts.append(description[:300])  # cap at 300 chars — Voyage context is limited

    return " ".join(parts)


def embed_alerts(alerts: list[dict]) -> list[list[float]]:
    """
    Embed a list of alert dicts. Returns parallel list of embedding vectors.
    Batches automatically.
    """
    texts = [alert_to_text(a) for a in alerts]
    return embed_texts(texts)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of raw text strings. Returns parallel list of embedding vectors."""
    client = _client()
    embeddings = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        log.debug("Embedding batch %d-%d via Voyage AI", i, i + len(batch))
        result = client.embed(batch, model=MODEL, input_type="query")
        embeddings.extend(result.embeddings)
    return embeddings


def embed_single(alert: dict) -> list[float]:
    """Convenience wrapper for a single alert."""
    return embed_alerts([alert])[0]
