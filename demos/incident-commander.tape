# demos/incident-commander.tape
# VHS tape — records the Multi-Agent Incident Commander demo gif.
#
# Prerequisites:
#   brew install vhs
#   # kind cluster running: kind create cluster --name doctor-lab
#   # OOM demo deployment running: kubectl apply -f agents/k8s-doctor/fixtures/oom.yaml -n doctor-lab
#   cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/incident-commander
#   uv venv && source .venv/bin/activate
#   uv pip install -r requirements.txt
#   export ANTHROPIC_API_KEY="sk-ant-..."
#   # .env already has REQUIRE_HUMAN_APPROVAL=true
#
# Record:
#   vhs ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/demos/incident-commander.tape
#
# Note: The demo uses --demo oom mode so no Alert Correlator is needed.
#       The approval gate will pause for input — type "yes" when prompted.
#
# Output: demos/incident-commander.gif  (embed in agents/incident-commander/README.md)

Output demos/incident-commander.gif

Set Shell "bash"
Set FontSize 13
Set Width 1200
Set Height 800
Set Theme "Catppuccin Mocha"
Set Framerate 24
Set PlaybackSpeed 1.0

# ── Setup ────────────────────────────────────────────────────────────────────
Type "cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/incident-commander"
Enter
Sleep 500ms

Type "source .venv/bin/activate"
Enter
Sleep 500ms

# ── Show cluster state — OOM pod ─────────────────────────────────────────────
Type "echo '── OOM workload in kind-doctor-lab ─────────────────────'"
Enter
Sleep 200ms
Type "kubectl --context kind-doctor-lab get pods -n doctor-lab"
Enter
Sleep 2s

# ── Launch Incident Commander in demo mode ───────────────────────────────────
Type "echo '── Incident Commander — 4-agent CrewAI crew ────────────'"
Enter
Sleep 300ms
Type "echo '   Phase 1 (parallel): Triage + Investigator'"
Enter
Type "echo '   Phase 2: Mitigator (waits for both)'"
Enter
Type "echo '   Phase 3: Communicator (waits for all)'"
Enter
Sleep 1500ms

Type "python respond.py --demo oom"
Enter

# Phase 1: Triage + Investigator run in parallel (~30s each)
Sleep 60s

# Phase 2: Mitigator — approval gate fires here
# The tape pauses and types "yes" to approve the kubectl patch
Sleep 5s
Type "yes"
Enter
Sleep 20s

# Phase 3: Communicator posts the Slack card (dev mode → stdout)
Sleep 20s

# ── Final — show the posted Slack card ───────────────────────────────────────
Sleep 5s
