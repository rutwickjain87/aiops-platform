"""
Local embedding client for alert text using sentence-transformers.
Model: all-MiniLM-L6-v2 (384 dims, ~80MB, CPU-only, no API key required).

Why this model:
  - Runs entirely locally — no API calls, no cost per alert
  - 384 dims is small enough for fast IVFFlat search in pgvector
  - MiniLM is trained on 1B sentence pairs — good for short technical strings
  - First call triggers a one-time ~80MB download to ~/.cache/huggingface/

Swap the MODEL constant to upgrade (e.g. 'BAAI/bge-base-en-v1.5' for 768 dims,
better quality but requires updating init.sql vector() dimension to match).
"""
import logging
from functools import lru_cache

from sentence_transformers import SentenceTransformer

log = logging.getLogger(__name__)

MODEL = "all-MiniLM-L6-v2"   # 384 dims — change init.sql vector() if you swap
EMBEDDING_DIM = 384            # must match vector(<dim>) in init.sql
BATCH_SIZE = 64                # sentence-transformers handles batching internally


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    """Load model once and cache. First call downloads ~80MB to ~/.cache/huggingface/."""
    log.info("Loading sentence-transformers model '%s' (first call may download ~80MB)...", MODEL)
    m = SentenceTransformer(MODEL)
    log.info("Model loaded. Embedding dim: %d", m.get_sentence_embedding_dimension())
    return m


def alert_to_text(alert: dict) -> str:
    """
    Convert an AlertManager alert dict to a single string for embedding.

    Strategy: repeat the high-signal correlation labels (namespace, service, node)
    twice so the model weights them more heavily. MiniLM treats token frequency
    as importance signal — repeating shared labels pulls correlated alerts closer
    in embedding space without needing a domain-tuned model.

    Format:
      "<namespace> <service> <alertname> severity=<sev> <label_kv_pairs>
       | <summary> | <description[:200]>
       | namespace=<ns> service=<svc>"   ← repeated for emphasis
    """
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})

    alertname = labels.get("alertname", "unknown")
    severity = labels.get("severity", "info")
    namespace = labels.get("namespace", "")
    service = labels.get("service", labels.get("job", ""))
    node = labels.get("node", "")

    # All labels except alertname/severity (already prominent in prefix)
    extra = " ".join(
        f"{k}={v}"
        for k, v in sorted(labels.items())
        if k not in ("alertname", "severity")
    )

    summary = annotations.get("summary", "")
    description = annotations.get("description", "")

    # Prefix: high-signal location identifiers first
    prefix_parts = []
    if namespace:
        prefix_parts.append(namespace)
    if service:
        prefix_parts.append(service)
    if node:
        prefix_parts.append(node)
    prefix_parts.append(alertname)
    prefix_parts.append(f"severity={severity}")

    parts = [" ".join(prefix_parts)]
    if extra:
        parts.append(extra)
    parts.append("|")
    if summary:
        parts.append(summary)
    if description:
        parts.append("|")
        parts.append(description[:200])

    # Repeat shared-scope labels at the end for emphasis
    emphasis = []
    if namespace:
        emphasis.append(f"namespace={namespace}")
    if service:
        emphasis.append(f"service={service}")
    if node:
        emphasis.append(f"node={node}")
    if emphasis:
        parts.append("|")
        parts.append(" ".join(emphasis))

    return " ".join(parts)


def embed_alerts(alerts: list[dict]) -> list[list[float]]:
    """
    Embed a list of alert dicts. Returns a parallel list of embedding vectors.
    All computation is local — no network calls.
    """
    texts = [alert_to_text(a) for a in alerts]
    return embed_texts(texts)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of raw text strings. Returns parallel list of embedding vectors."""
    if not texts:
        return []
    model = _model()
    log.debug("Embedding %d texts locally with %s...", len(texts), MODEL)
    vectors = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=False,
        normalize_embeddings=True,   # cosine sim = dot product after L2 norm
        convert_to_numpy=True,
    )
    return [v.tolist() for v in vectors]


def embed_single(alert: dict) -> list[float]:
    """Convenience wrapper for a single alert."""
    return embed_alerts([alert])[0]
