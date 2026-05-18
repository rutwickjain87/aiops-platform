"""
Synthetic alert generator — Prometheus AlertManager webhook format.
Generates realistic correlated alert batches for testing the correlator.
Run: python synthetic/generate_alerts.py [--scenario <name>] [--count <n>]
"""
import json
import hashlib
import random
import argparse
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Alert templates — real-world DevSecOps / Kubernetes alert patterns
# ---------------------------------------------------------------------------

SCENARIOS = {
    # OOMKilled cascade: memory alert → pod restart → latency → error rate
    "oom_cascade": [
        {
            "alertname": "KubernetesContainerOOMKilled",
            "severity": "critical",
            "namespace": "payments",
            "pod": "payments-api-{n}",
            "container": "api",
            "summary": "Container {container} in pod {pod} OOMKilled",
            "description": "Container has been OOMKilled {kills} times in the last 10 minutes. Memory limit: 512Mi.",
        },
        {
            "alertname": "KubernetesPodRestartingTooMuch",
            "severity": "warning",
            "namespace": "payments",
            "pod": "payments-api-{n}",
            "summary": "Pod {pod} is restarting frequently",
            "description": "Pod restart count exceeded threshold (>5 in 15m). CrashLoopBackOff imminent.",
        },
        {
            "alertname": "HighErrorRate",
            "severity": "critical",
            "namespace": "payments",
            "service": "payments-api",
            "summary": "Error rate above 5% for service {service}",
            "description": "HTTP 5xx error rate is {error_rate}% (threshold: 5%). SLO breach in progress.",
        },
        {
            "alertname": "HighLatencyP99",
            "severity": "warning",
            "namespace": "payments",
            "service": "payments-api",
            "summary": "P99 latency degraded for {service}",
            "description": "P99 request latency is {latency}ms (threshold: 500ms). Likely caused by pod restarts.",
        },
    ],

    # Node pressure cascade: disk → eviction → pod failures
    "node_pressure": [
        {
            "alertname": "NodeDiskPressure",
            "severity": "warning",
            "node": "ip-10-0-1-{n}.eu-west-1.compute.internal",
            "summary": "Node {node} disk pressure",
            "description": "Node disk usage is at {disk_pct}%. Kubelet may begin evicting pods.",
        },
        {
            "alertname": "NodeMemoryPressure",
            "severity": "warning",
            "node": "ip-10-0-1-{n}.eu-west-1.compute.internal",
            "summary": "Node {node} memory pressure",
            "description": "Available memory on node dropped below 10%. Pod eviction risk high.",
        },
        {
            "alertname": "KubernetesPodEvicted",
            "severity": "critical",
            "namespace": "monitoring",
            "node": "ip-10-0-1-{n}.eu-west-1.compute.internal",
            "pod": "prometheus-{n}",
            "summary": "Pod {pod} evicted from node {node}",
            "description": "Pod was evicted due to node pressure. Reason: DiskPressure.",
        },
        {
            "alertname": "PrometheusDown",
            "severity": "critical",
            "namespace": "monitoring",
            "job": "prometheus",
            "summary": "Prometheus instance is down",
            "description": "Prometheus job {job} has been down for >3 minutes. Metrics collection interrupted.",
        },
    ],

    # Security cascade: Semgrep finding → SAST alert → policy violation
    "security_incident": [
        {
            "alertname": "SASTCriticalFinding",
            "severity": "critical",
            "namespace": "ci",
            "repo": "payments-service",
            "rule": "python.flask.security.injection.tainted-sql-string",
            "summary": "Critical SAST finding in {repo}",
            "description": "Semgrep detected SQL injection risk in {repo}. Rule: {rule}. Commit blocked.",
        },
        {
            "alertname": "OPAPolicyViolation",
            "severity": "critical",
            "namespace": "payments",
            "policy": "require-non-root",
            "workload": "payments-api",
            "summary": "OPA policy violation: {policy} on {workload}",
            "description": "Deployment {workload} rejected by Gatekeeper. Policy: {policy}. Container running as root.",
        },
        {
            "alertname": "VaultSecretLeak",
            "severity": "critical",
            "namespace": "payments",
            "service": "payments-api",
            "summary": "Vault secret access anomaly in {service}",
            "description": "Unusual secret access pattern detected. Service {service} accessed 47 secrets in 2 minutes (baseline: 3).",
        },
    ],

    # Unrelated noise — should NOT be grouped together
    "noise": [
        {
            "alertname": "CertificateExpiringSoon",
            "severity": "warning",
            "namespace": "ingress",
            "domain": "api.example.com",
            "summary": "TLS certificate for {domain} expires in 14 days",
            "description": "Certificate will expire on {expiry}. Renew via cert-manager.",
        },
        {
            "alertname": "CronJobFailed",
            "severity": "warning",
            "namespace": "batch",
            "job": "nightly-report-{n}",
            "summary": "CronJob {job} failed",
            "description": "Last run of {job} exited with code 1. Check logs for details.",
        },
        {
            "alertname": "TargetDown",
            "severity": "warning",
            "namespace": "monitoring",
            "job": "blackbox-{n}",
            "summary": "Scrape target {job} is down",
            "description": "Prometheus cannot reach scrape target {job}. Endpoint may be unavailable.",
        },
    ],
}


def _render(template: str, **kwargs) -> str:
    """Simple {key} substitution with random fallbacks."""
    fills = {
        "n": str(random.randint(1, 9)),
        "kills": str(random.randint(5, 20)),
        "error_rate": f"{random.uniform(5, 30):.1f}",
        "latency": str(random.randint(500, 2000)),
        "disk_pct": str(random.randint(85, 99)),
        "expiry": (datetime.now(timezone.utc) + timedelta(days=14)).strftime("%Y-%m-%d"),
        **kwargs,
    }
    result = template
    for k, v in fills.items():
        result = result.replace(f"{{{k}}}", v)
    # resolve any remaining {container} etc that may be in labels
    for k in list(fills.keys()):
        result = result.replace(f"{{{k}}}", fills.get(k, k))
    return result


def _fingerprint(alertname: str, labels: dict) -> str:
    """Stable fingerprint like AlertManager uses."""
    key = json.dumps({"alertname": alertname, **labels}, sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def build_alert(template: dict, base_time: datetime, jitter_seconds: int = 60) -> dict:
    """Turn a template dict into an AlertManager-format alert payload."""
    n = str(random.randint(1, 9))
    labels = {}
    for k, v in template.items():
        if k not in ("summary", "description"):
            labels[k] = _render(str(v), n=n)

    summary = _render(template.get("summary", ""), **labels)
    description = _render(template.get("description", ""), **labels)

    jitter = timedelta(seconds=random.randint(0, jitter_seconds))
    started = base_time + jitter
    fp = _fingerprint(labels["alertname"], {k: v for k, v in labels.items() if k != "alertname"})

    return {
        "fingerprint": fp,
        "status": "firing",
        "labels": labels,
        "annotations": {
            "summary": summary,
            "description": description,
        },
        "startsAt": started.isoformat(),
        "endsAt": None,
    }


def generate_scenario(scenario_name: str, count: int = 1) -> list[dict]:
    """Generate `count` batches of the named scenario alerts."""
    templates = SCENARIOS[scenario_name]
    base_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    alerts = []
    for _ in range(count):
        for tmpl in templates:
            alerts.append(build_alert(tmpl, base_time))
    return alerts


def generate_mixed(noise_ratio: float = 0.3) -> list[dict]:
    """Generate a realistic mixed batch: correlated alerts + noise."""
    alerts = []
    # Pick one correlation scenario
    scenario = random.choice(["oom_cascade", "node_pressure", "security_incident"])
    alerts.extend(generate_scenario(scenario))
    # Add some noise
    noise_count = max(1, int(len(alerts) * noise_ratio))
    base_time = datetime.now(timezone.utc) - timedelta(minutes=random.randint(1, 10))
    for _ in range(noise_count):
        tmpl = random.choice(SCENARIOS["noise"])
        alerts.append(build_alert(tmpl, base_time))
    random.shuffle(alerts)
    return alerts


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic AlertManager alerts")
    parser.add_argument("--scenario", choices=list(SCENARIOS.keys()) + ["mixed"], default="mixed")
    parser.add_argument("--count", type=int, default=1, help="Number of scenario batches")
    parser.add_argument("--output", default="-", help="Output file path (- for stdout)")
    args = parser.parse_args()

    if args.scenario == "mixed":
        alerts = generate_mixed()
    else:
        alerts = generate_scenario(args.scenario, args.count)

    payload = json.dumps(alerts, indent=2, default=str)
    if args.output == "-":
        print(payload)
    else:
        with open(args.output, "w") as f:
            f.write(payload)
        print(f"Wrote {len(alerts)} alerts to {args.output}")


if __name__ == "__main__":
    main()
