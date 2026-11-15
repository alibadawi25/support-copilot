// Types mirror backend/support_copilot/api/contracts.py and schemas.py.

export const STATUSES = ["open", "resolved"] as const;
export const PRIORITIES = ["low", "medium", "high"] as const;
export const CATEGORIES = [
  "checkout",
  "account_access",
  "billing",
  "exports",
  "notifications",
  "integrations",
  "security",
] as const;
export const ACTIONS = [
  "search_knowledge",
  "summarize_ticket",
  "similar_tickets",
  "draft_reply",
  "count_tickets",
] as const;

export type Action = (typeof ACTIONS)[number];

export interface TicketFilter {
  status?: string;
  priority?: string;
  category?: string;
}

export interface TicketSummary {
  id: string;
  title: string;
  category: string;
  priority: string;
  status: string;
  updated_at: string;
  reviewed_at: string | null;
}

export interface TicketMessage {
  at: string;
  author: string;
  text: string;
}

export interface TicketDetail extends TicketSummary {
  description: string;
  product_area: string;
  created_at: string;
  resolution_summary: string | null;
  messages: TicketMessage[];
}

export interface Citation {
  source_type: "article" | "ticket";
  source_id: string;
  chunk_id: string | null;
  title: string;
  quote: string;
  score: number | null;
  excerpt: string | null;
}

export interface Answer {
  action: Action;
  state: "answered" | "insufficient_evidence";
  text: string;
  reason: string | null;
  citations: Citation[];
  ticket_ids: string[];
  count: number | null;
  is_draft: boolean;
}

export interface ToolCall {
  tool: string;
  arguments: Record<string, unknown>;
  ok: boolean;
  duration_ms: number;
}

export interface RetrievalInfo {
  method: string;
  top_k: number;
  threshold: number | null;
  top_score: number | null;
}

export interface AssistantResponse {
  run_id: string;
  answer: Answer;
  retrieval: RetrievalInfo | null;
  tool_trace: ToolCall[];
  limitations: string[];
}

export interface AssistantRequest {
  action: Action;
  ticket_id?: string;
  query?: string;
  category?: string;
  filters?: TicketFilter;
}

export type ErrorKind = "validation" | "not_found" | "unavailable" | "network" | "server";

export class ApiError extends Error {
  constructor(
    public kind: ErrorKind,
    message: string,
  ) {
    super(message);
  }
}

const KINDS: Record<number, ErrorKind> = { 404: "not_found", 422: "validation", 503: "unavailable" };

// FastAPI sends `detail` as a string (our handlers) or a list of field errors (422).
function detailMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((e: { msg?: string }) => (e.msg ?? "Invalid input").replace(/^Value error, /, ""))
      .join("; ");
  }
  return "Request failed.";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError("network", "Cannot reach the API. Is the backend running?");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const message = body ? detailMessage(body.detail) : `The server returned ${res.status}.`;
    throw new ApiError(KINDS[res.status] ?? "server", message);
  }
  return res.json();
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export function listTickets(filter: TicketFilter): Promise<TicketSummary[]> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filter)) if (value) params.set(key, value);
  const qs = params.toString();
  return request(`/api/tickets${qs ? `?${qs}` : ""}`);
}

export function getTicket(id: string): Promise<TicketDetail> {
  return request(`/api/tickets/${encodeURIComponent(id)}`);
}

export function setReviewed(id: string, reviewed: boolean): Promise<TicketDetail> {
  return request(`/api/tickets/${encodeURIComponent(id)}/reviewed`, json("PATCH", { reviewed }));
}

export function runAssistant(body: AssistantRequest): Promise<AssistantResponse> {
  return request("/api/assistant/run", json("POST", body));
}
