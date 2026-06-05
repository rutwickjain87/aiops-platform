"""
kubectl tools for the Incident Commander.
Wraps kubectl as subprocess calls — no Python kubernetes SDK to avoid auth complexity.
All mutating commands (patch, rollout restart, scale) require REQUIRE_HUMAN_APPROVAL=false
or explicit human confirmation before execution.
"""
import os
import subprocess
import logging
from crewai.tools import tool
from rich.console import Console

log = logging.getLogger(__name__)
_console = Console()

_REQUIRE_APPROVAL = os.environ.get("REQUIRE_HUMAN_APPROVAL", "true").lower() != "false"
_KUBE_CONTEXT = os.environ.get("KUBE_CONTEXT", "")
_KUBECONFIG   = os.path.expanduser(os.environ.get("KUBECONFIG", ""))  # expands ~ → /Users/...


def _kubectl(args: list[str], timeout: int = 30) -> str:
    """Run kubectl with the given args, return combined stdout+stderr."""
    cmd = ["kubectl"]
    if _KUBE_CONTEXT:
        cmd += ["--context", _KUBE_CONTEXT]
    if _KUBECONFIG:
        cmd += ["--kubeconfig", _KUBECONFIG]
    cmd += args
    log.debug("kubectl %s", " ".join(args))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        output = result.stdout + result.stderr
        return output.strip() or "(no output)"
    except FileNotFoundError:
        return "ERROR: kubectl not found. Install kubectl and ensure it's in PATH."
    except subprocess.TimeoutExpired:
        return f"ERROR: kubectl command timed out after {timeout}s"
    except Exception as exc:
        return f"ERROR: {exc}"


# ---------------------------------------------------------------------------
# Read-only tools (always safe)
# ---------------------------------------------------------------------------

@tool("get_pod_logs")
def get_pod_logs(namespace_and_pod: str) -> str:
    """
    Fetch the last 100 lines of logs from a pod.
    Input format: "<namespace>/<pod-name>" or "<namespace>/<pod-name>/<container>".
    """
    parts = namespace_and_pod.strip().split("/")
    if len(parts) == 2:
        ns, pod = parts
        args = ["logs", "-n", ns, pod, "--tail=100"]
    elif len(parts) == 3:
        ns, pod, container = parts
        args = ["logs", "-n", ns, pod, "-c", container, "--tail=100"]
    else:
        return "ERROR: expected 'namespace/pod' or 'namespace/pod/container'"
    return _kubectl(args)


@tool("describe_pod")
def describe_pod(namespace_and_pod: str) -> str:
    """
    Run kubectl describe pod to get events, conditions, and resource usage.
    Input format: "<namespace>/<pod-name>".
    """
    parts = namespace_and_pod.strip().split("/")
    if len(parts) != 2:
        return "ERROR: expected 'namespace/pod'"
    ns, pod = parts
    return _kubectl(["describe", "pod", "-n", ns, pod])


@tool("get_pods_in_namespace")
def get_pods_in_namespace(namespace: str) -> str:
    """
    List all pods in a namespace with their status and restart counts.
    Input: namespace name.
    """
    return _kubectl(["get", "pods", "-n", namespace.strip(), "-o", "wide"])


@tool("get_events")
def get_events(namespace: str) -> str:
    """
    Get recent Kubernetes events for a namespace, sorted by time.
    Input: namespace name.
    """
    return _kubectl(["get", "events", "-n", namespace.strip(), "--sort-by=.lastTimestamp"])


@tool("get_node_status")
def get_node_status(node_name: str) -> str:
    """
    Get status and conditions of a Kubernetes node.
    Input: node name (or 'all' for all nodes).
    """
    if node_name.strip().lower() == "all":
        return _kubectl(["get", "nodes", "-o", "wide"])
    return _kubectl(["describe", "node", node_name.strip()])


@tool("get_deployment_status")
def get_deployment_status(namespace_and_deployment: str) -> str:
    """
    Get the status, replica count, and conditions of a deployment.
    Input format: "<namespace>/<deployment-name>" or just "<namespace>" to list all.
    """
    parts = namespace_and_deployment.strip().split("/")
    if len(parts) == 1:
        return _kubectl(["get", "deployments", "-n", parts[0]])
    ns, deploy = parts
    return _kubectl(["describe", "deployment", "-n", ns, deploy])


# ---------------------------------------------------------------------------
# Mutating tools (gated behind human approval)
# ---------------------------------------------------------------------------

def _approval_gate(action: str) -> bool:
    """Prompt the human operator for approval. Returns True if approved."""
    if not _REQUIRE_APPROVAL:
        _console.print(f"[yellow]⚠️  Human approval bypassed (REQUIRE_HUMAN_APPROVAL=false)[/yellow]")
        log.warning("Human approval bypassed (REQUIRE_HUMAN_APPROVAL=false)")
        return True
    _console.print(f"\n[bold red]⚠️  APPROVAL REQUIRED[/bold red]")
    _console.print(f"[bold]Action:[/bold] {action}")
    _console.print("[bold]Approve? \\[yes/no]:[/bold] ", end="")
    try:
        answer = input().strip().lower()
    except EOFError:
        _console.print("[red]EOFError reading stdin — rejecting action for safety[/red]")
        return False
    approved = answer in ("yes", "y")
    if approved:
        _console.print("[green]✅ Approved — executing action[/green]")
    else:
        _console.print("[red]❌ Rejected — action aborted[/red]")
    return approved


@tool("restart_deployment")
def restart_deployment(namespace_and_deployment: str) -> str:
    """
    Perform a rolling restart of a deployment (kubectl rollout restart).
    REQUIRES human approval before execution.
    Input format: "<namespace>/<deployment-name>".
    """
    _console.print(f"\n[bold cyan]🔧 MUTATING TOOL CALLED: restart_deployment({namespace_and_deployment})[/bold cyan]")
    parts = namespace_and_deployment.strip().split("/")
    if len(parts) != 2:
        return "ERROR: expected 'namespace/deployment'"
    ns, deploy = parts
    action = f"kubectl rollout restart deployment/{deploy} -n {ns}"
    if not _approval_gate(action):
        return "ACTION REJECTED by operator. Deployment restart aborted."
    return _kubectl(["rollout", "restart", f"deployment/{deploy}", "-n", ns])


@tool("scale_deployment")
def scale_deployment(namespace_deployment_replicas: str) -> str:
    """
    Scale a deployment to a given number of replicas.
    REQUIRES human approval before execution.
    Input format: "<namespace>/<deployment-name>/<replica-count>".
    """
    _console.print(f"\n[bold cyan]🔧 MUTATING TOOL CALLED: scale_deployment({namespace_deployment_replicas})[/bold cyan]")
    parts = namespace_deployment_replicas.strip().split("/")
    if len(parts) != 3:
        return "ERROR: expected 'namespace/deployment/replicas'"
    ns, deploy, replicas = parts
    action = f"kubectl scale deployment/{deploy} --replicas={replicas} -n {ns}"
    if not _approval_gate(action):
        return "ACTION REJECTED by operator. Scale operation aborted."
    return _kubectl(["scale", f"deployment/{deploy}", f"--replicas={replicas}", "-n", ns])


@tool("patch_resource_limits")
def patch_resource_limits(namespace_pod_limits: str) -> str:
    """
    Patch memory/CPU limits on a deployment to address OOMKilled issues.
    REQUIRES human approval before execution.
    Input format: "<namespace>/<deployment-name>/<memory-limit>" (e.g. payments/payments-api/1Gi).
    """
    _console.print(f"\n[bold cyan]🔧 MUTATING TOOL CALLED: patch_resource_limits({namespace_pod_limits})[/bold cyan]")
    parts = namespace_pod_limits.strip().split("/")
    if len(parts) != 3:
        return "ERROR: expected 'namespace/deployment/memory-limit'"
    ns, deploy, mem_limit = parts
    patch = f'{{"spec":{{"template":{{"spec":{{"containers":[{{"name":"{deploy}","resources":{{"limits":{{"memory":"{mem_limit}"}}}}}}]}}}}}}}}'
    action = f"kubectl patch deployment {deploy} -n {ns} with memory limit {mem_limit}"
    if not _approval_gate(action):
        return "ACTION REJECTED by operator. Patch aborted."
    return _kubectl(["patch", "deployment", deploy, "-n", ns, "--patch", patch])
