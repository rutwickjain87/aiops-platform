"""
_burst_with_socket.py — local-only driver that fires N alerts then runs Socket Mode.

This exists so the same process owns INCIDENT_STORE used by the button click
handlers (acknowledge / escalate / dismiss). Spawning trigger_alert from a
separate process creates a disconnected INCIDENT_STORE, which is why button
clicks failed earlier.

USAGE
─────
    METRICS_ENABLED=true METRICS_PORT=8000 \
        .venv/bin/python _burst_with_socket.py ALERT-001 ALERT-002 ALERT-003

After all alerts are posted, the script keeps Socket Mode active so Slack can
deliver interactive payloads (button clicks) back to this process.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time

from dotenv import load_dotenv

load_dotenv()

# Verbose slack_bolt logging so we see every inbound event on the websocket
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
for noisy in ("urllib3", "websockets", "websocket"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

import bot  # noqa: E402  — module-level setup of App / planner / INCIDENT_STORE
from handlers import INCIDENT_STORE  # noqa: E402
from metrics import start_metrics_server  # noqa: E402
from slack_bolt.adapter.socket_mode import SocketModeHandler  # noqa: E402


@bot.app.middleware
def _trace_every_event(logger, body, next):  # noqa: A002
    print(f"[trace] inbound: type={body.get('type')} "
          f"action={(body.get('actions') or [{}])[0].get('action_id')} "
          f"value={(body.get('actions') or [{}])[0].get('value')}",
          flush=True)
    print(f"[trace] INCIDENT_STORE keys: {list(INCIDENT_STORE.keys())}", flush=True)
    next()


def _fire_in_background(alerts: list[str]) -> None:
    time.sleep(1)
    for aid in alerts:
        print(f"[burst] firing {aid}", flush=True)
        try:
            r = bot.trigger_alert(aid)
            print(f"[burst]   ok iterations={r.get('iterations')} incident_id={r.get('incident_id')}", flush=True)
        except Exception as e:
            print(f"[burst]   error: {e!r}", flush=True)
        time.sleep(3)
    print("[burst] all alerts fired — Socket Mode remains active for button clicks", flush=True)


def main() -> None:
    alerts = sys.argv[1:] or ["ALERT-001", "ALERT-002", "ALERT-003", "ALERT-001", "ALERT-002"]
    start_metrics_server()
    threading.Thread(target=_fire_in_background, args=(alerts,), daemon=True).start()

    print("[burst] starting Socket Mode listener (blocks)", flush=True)
    SocketModeHandler(bot.app, os.environ["SLACK_APP_TOKEN"]).start()


if __name__ == "__main__":
    main()
