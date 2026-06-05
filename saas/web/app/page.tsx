"use client";

import { useState } from "react";
import RunForm from "@/components/RunForm";
import RunOutput from "@/components/RunOutput";
import type { RunEvent } from "@/lib/api";

/**
 * Home — IaC Generator landing page.
 *
 * Flow:
 *   1. User types a natural-language infrastructure prompt
 *   2. POST /runs → SSE stream opens
 *   3. Each event is rendered live (node progress, then file contents)
 *   4. On `event: done`, show download link for all generated files
 *
 * TODO — auth:
 *   Wrap with <AuthProvider> from Supabase when auth is implemented.
 *   Show login gate if user is not authenticated.
 *
 * TODO — billing:
 *   Show remaining credits in the header once Stripe is wired.
 */
export default function Home() {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);

  return (
    <main className="min-h-screen bg-gray-950 text-gray-100 flex flex-col items-center px-4 py-12">
      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <header className="mb-10 text-center">
        <h1 className="text-3xl font-bold tracking-tight text-white">
          AIOps Platform
        </h1>
        <p className="mt-2 text-gray-400 text-sm max-w-xl">
          Describe your infrastructure in plain English.
          We generate production-ready Terraform — validated before delivery.
        </p>
        {/* TODO — show auth state + remaining credits here */}
      </header>

      {/* ── Main content ─────────────────────────────────────────────────── */}
      <div className="w-full max-w-2xl space-y-6">
        <RunForm
          disabled={running}
          onRun={async (prompt, provider) => {
            setEvents([]);
            setRunId(null);
            setRunning(true);
            try {
              const { runId: id, stream } = await import("@/lib/api").then((m) =>
                m.startRun(prompt, provider)
              );
              setRunId(id);
              for await (const event of stream) {
                setEvents((prev) => [...prev, event]);
                if (event.type === "done") break;
              }
            } finally {
              setRunning(false);
            }
          }}
        />

        {(events.length > 0 || running) && (
          <RunOutput events={events} running={running} runId={runId} />
        )}
      </div>
    </main>
  );
}
