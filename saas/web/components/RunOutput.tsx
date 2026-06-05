"use client";

import type { RunEvent } from "@/lib/api";

/**
 * RunOutput — live SSE event feed + generated file viewer.
 */

interface RunOutputProps {
  events: RunEvent[];
  running: boolean;
  runId: string | null;
}

const NODE_LABELS: Record<string, string> = {
  clarify: "🔍 Clarifying requirements",
  plan: "📋 Planning resource dependencies",
  generate: "⚙️  Generating Terraform HCL",
  validate: "✅ Validating with terraform validate",
  output: "📦 Writing files",
};

export default function RunOutput({ events, running, runId }: RunOutputProps) {
  const fileEvents = events.filter((e): e is Extract<RunEvent, { type: "file" }> => e.type === "file");
  const nodeEvents = events.filter((e): e is Extract<RunEvent, { type: "node" }> => e.type === "node");
  const doneEvent = events.find((e): e is Extract<RunEvent, { type: "done" }> => e.type === "done");

  return (
    <div className="space-y-4">
      {/* ── Pipeline progress ──────────────────────────────────────────────── */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
          Pipeline
          {running && <span className="ml-2 inline-block w-2 h-2 rounded-full bg-indigo-500 animate-pulse" />}
          {doneEvent && <span className="ml-2 text-green-400">Done</span>}
          {runId && <span className="ml-auto float-right font-mono text-gray-600">{runId.slice(0, 8)}</span>}
        </h2>
        <div className="space-y-1">
          {(["clarify", "plan", "generate", "validate", "output"] as const).map((node) => {
            const evt = nodeEvents.find((e) => e.node === node);
            const done = !!doneEvent || (evt && nodeEvents.indexOf(evt) < nodeEvents.length - 1);
            return (
              <div key={node} className={`flex items-center gap-2 text-sm ${evt ? "text-gray-100" : "text-gray-600"}`}>
                <span className={`w-3 h-3 rounded-full flex-shrink-0 ${done ? "bg-green-500" : evt ? "bg-indigo-500 animate-pulse" : "bg-gray-700"}`} />
                <span>{NODE_LABELS[node]}</span>
                {evt && <span className="text-gray-500 text-xs ml-auto">{evt.message}</span>}
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Generated files ────────────────────────────────────────────────── */}
      {fileEvents.length > 0 && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
            Generated files ({fileEvents.length})
          </h2>
          <div className="space-y-3">
            {fileEvents.map((evt) => (
              <div key={evt.filename}>
                <div className="text-xs font-mono text-indigo-400 mb-1">{evt.filename}</div>
                <pre className="text-xs font-mono bg-gray-950 rounded p-3 overflow-x-auto text-gray-300 border border-gray-800 max-h-48">
                  {evt.content}
                </pre>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Error ──────────────────────────────────────────────────────────── */}
      {events.some((e) => e.type === "error") && (
        <div className="bg-red-950 border border-red-800 rounded-xl p-4 text-sm text-red-300">
          {(events.find((e) => e.type === "error") as { type: "error"; error: string })?.error}
        </div>
      )}
    </div>
  );
}
