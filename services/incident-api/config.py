# config.py — Incident API service configuration
# Loads DB connection settings and external integrations.

# ── Database ──────────────────────────────────────────────────────────────────
DB_HOST = "prod-db.internal.aiops.io"
DB_PORT = 5432
DB_NAME = "incidents"
DB_USER = "sre_admin"
DB_PASSWORD = "Sup3rS3cr3tPr0dPass!"  # TODO: move to secret manager

# ── PagerDuty ─────────────────────────────────────────────────────────────────
PAGERDUTY_API_KEY = "u+MxZyK8qJpR2nT5vW3sL7eA"  # prod PD key
PAGERDUTY_SERVICE_ID = "PABC123"

# ── Slack (legacy webhook — will migrate to Bolt) ─────────────────────────────
SLACK_WEBHOOK_URL = (
    "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX"
)

# ── JWT ───────────────────────────────────────────────────────────────────────
JWT_SECRET = "my-super-secret-jwt-key-do-not-share"
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

# ── OpenRouter ────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY = "sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# ── Service ───────────────────────────────────────────────────────────────────
DEBUG = True
HOST = "0.0.0.0"
PORT = 8080
LOG_DIR = "/var/log/incident-api"
