/**
 * lib/api.ts — Client-side API helpers.
 *
 * startRun() opens an SSE stream to POST /runs and returns an async iterator
 * of typed RunEvent objects.
 *
 * TODO — auth:
 *   Add `Authorization: Bearer <supabase_access_token>` header once auth is wired.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

// ── Event types ───────────────────────────────────────────────────────────────

export type RunEvent =
  | { type: "status"; status: "queued" | "running" | "completed" | "failed" }
  | { type: "node"; node: string; message: string }
  | { type: "file"; filename: string; content: string }
  | { type: "error"; error: string }
  | { type: "done"; run_id: string; file_count: number };


// ── startRun — returns run_id + async iterator of SSE events ─────────────────

export async function startRun(
  prompt: string,
  provider: string = "aws"
): Promise<{ runId: string; stream: AsyncIterable<RunEvent> }> {
  const resp = await fetch(`${API_BASE}/runs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      // TODO: "Authorization": `Bearer ${supabaseSession.access_token}`,
    },
    body: JSON.stringify({ prompt, provider }),
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`POST /runs failed: ${resp.status} — ${text}`);
  }

  const runId = resp.headers.get("X-Run-Id") ?? "unknown";

  async function* parseSSE(): AsyncIterable<RunEvent> {
    const reader = resp.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";

      for (const frame of frames) {
        if (!frame.trim()) continue;
        const lines = frame.split("\n");
        let eventType = "message";
        let dataStr = "";

        for (const line of lines) {
          if (line.startsWith("event: ")) eventType = line.slice(7).trim();
          if (line.startsWith("data: ")) dataStr = line.slice(6).trim();
        }

        if (!dataStr) continue;

        try {
          const payload = JSON.parse(dataStr);
          yield { type: eventType, ...payload } as RunEvent;
        } catch {
          console.warn("Failed to parse SSE data:", dataStr);
        }
      }
    }
  }

  return { runId, stream: parseSSE() };
}


// ── getRun — poll a run by ID ─────────────────────────────────────────────────

export interface RunStatus {
  run_id: string;
  status: string;
  created_at: string;
  prompt: string;
  provider: string;
  result: { files: string[]; file_count: number; terraform_valid: boolean } | null;
  error: string | null;
}

export async function getRun(runId: string): Promise<RunStatus> {
  const resp = await fetch(`${API_BASE}/runs/${runId}`, {
    // TODO: headers: { "Authorization": `Bearer ${supabaseSession.access_token}` },
  });
  if (!resp.ok) throw new Error(`GET /runs/${runId} failed: ${resp.status}`);
  return resp.json();
}
