# demos/log-triage.tape
# VHS tape — records the Log Triage Agent demo gif.
#
# Prerequisites:
#   brew install vhs
#   cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/log-intelligence
#   uv venv && source .venv/bin/activate
#   uv pip install -r requirements_anthropic.txt
#   export ANTHROPIC_API_KEY="sk-ant-..."
#
# Record:
#   vhs ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/demos/log-triage.tape
#
# Output: demos/log-triage.gif  (embed in agents/log-intelligence/README.md)

Output demos/log-triage.gif

Set Shell "bash"
Set FontSize 14
Set Width 1200
Set Height 700
Set Theme "Catppuccin Mocha"
Set Framerate 24
Set PlaybackSpeed 1.0

# ── Navigate to agent ────────────────────────────────────────────────────────
Type "cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/log-intelligence"
Enter
Sleep 500ms

Type "source .venv/bin/activate"
Enter
Sleep 500ms

# ── Show the eval set briefly ────────────────────────────────────────────────
Type "echo '── Eval cases (5 labeled HDFS cases) ───────────────────'"
Enter
Type "jq -r '[.id, .expected_severity] | @tsv' evals/cases.jsonl"
Enter
Sleep 2s

# ── Show what the HDFS log looks like ───────────────────────────────────────
Type "echo '── Log sample (first 5 lines) ──────────────────────────'"
Enter
Sleep 200ms
Type "head -5 ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/services/ingestion/loghub-samples/HDFS/HDFS_2k.log"
Enter
Sleep 2s

# ── Run the triage agent ─────────────────────────────────────────────────────
Type "echo '── Running Log Triage Agent (Anthropic backend) ────────'"
Enter
Sleep 500ms

Type "LOG=~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/services/ingestion/loghub-samples/HDFS/HDFS_2k.log"
Enter
Sleep 200ms

Type "python triage.py $LOG --backend anthropic"
Enter

# Give the agent time to run (tool calls + LLM reasoning)
Sleep 30s

# ── Run evals ────────────────────────────────────────────────────────────────
Type "echo '── Eval suite ──────────────────────────────────────────'"
Enter
Sleep 300ms
Type "python triage.py --eval --backend anthropic"
Enter
Sleep 45s

# ── Final pause so viewers can read the result ───────────────────────────────
Sleep 5s
