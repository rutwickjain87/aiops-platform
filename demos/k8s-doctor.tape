# demos/k8s-doctor.tape
# VHS tape — records the K8s Doctor LangGraph agent demo gif.
#
# Prerequisites:
#   brew install vhs
#   kind create cluster --name doctor-lab   (if not already running)
#   kubectl apply -f agents/k8s-doctor/fixtures/crashloop.yaml
#   kubectl apply -f agents/k8s-doctor/fixtures/oom.yaml
#   cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/k8s-doctor
#   uv venv && source .venv/bin/activate
#   uv pip install -r requirements.txt
#   export ANTHROPIC_API_KEY="sk-ant-..."
#
# Record:
#   vhs ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/demos/k8s-doctor.tape
#
# Output: demos/k8s-doctor.gif  (embed in agents/k8s-doctor/README.md)

Output demos/k8s-doctor.gif

Set Shell "bash"
Set FontSize 14
Set Width 1200
Set Height 750
Set Theme "Catppuccin Mocha"
Set Framerate 24
Set PlaybackSpeed 1.0

# ── Navigate and activate ────────────────────────────────────────────────────
Type "cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/k8s-doctor"
Enter
Sleep 500ms

Type "source .venv/bin/activate"
Enter
Sleep 500ms

# ── Show broken pods ─────────────────────────────────────────────────────────
Type "echo '── Broken workloads in kind-doctor-lab ─────────────────'"
Enter
Sleep 200ms
Type "kubectl --context kind-doctor-lab get pods -n doctor-lab"
Enter
Sleep 3s

# ── Diagnose CrashLoopBackOff ────────────────────────────────────────────────
Type "echo '── Diagnosing CrashLoopBackOff ─────────────────────────'"
Enter
Sleep 300ms
Type "python doctor.py --namespace doctor-lab --resource crashloop-demo --context kind-doctor-lab"
Enter

# observe → hypothesize → propose pipeline
Sleep 45s

# ── Diagnose OOMKilled ───────────────────────────────────────────────────────
Type "echo '── Diagnosing OOMKilled ─────────────────────────────────'"
Enter
Sleep 300ms
Type "python doctor.py --namespace doctor-lab --resource oom-demo --symptom OOMKilled --context kind-doctor-lab"
Enter
Sleep 45s

# ── Show model routing (Haiku for observe, Sonnet for reason) ─────────────────
Type "echo '── Model routing — Haiku (observe) + Sonnet (reason) ───'"
Enter
Sleep 200ms
Type "OBSERVE_MODEL=anthropic/claude-haiku-4-5 REASON_MODEL=anthropic/claude-sonnet-4-6 python doctor.py --namespace doctor-lab --resource crashloop-demo"
Enter
Sleep 40s

Sleep 5s
