import { type FormEvent, useEffect, useRef, useState } from "react";
import {
  ACTIONS,
  type Action,
  type ApiError,
  type AssistantRequest,
  type AssistantResponse,
  CATEGORIES,
  PRIORITIES,
  STATUSES,
  type TicketFilter,
  runAssistant,
} from "../api";
import { toApiError } from "../useLoad";
import { AnswerView } from "./AnswerView";
import { ErrorNote } from "./ErrorNote";
import { Select } from "./Select";

const ACTION_LABELS: Record<Action, string> = {
  search_knowledge: "Search knowledge base",
  summarize_ticket: "Summarize ticket",
  similar_tickets: "Find similar resolved tickets",
  draft_reply: "Draft reply",
  count_tickets: "Count tickets",
};

// Which inputs each action shows. The server decides what is *required* (422).
const USES_TICKET: Action[] = ["summarize_ticket", "draft_reply", "similar_tickets"];
const USES_QUERY: Action[] = ["search_knowledge", "similar_tickets", "draft_reply"];
const USES_CATEGORY: Action[] = ["search_knowledge", "similar_tickets"];

type Run =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "done"; response: AssistantResponse };

interface Props {
  ticketId: string | null;
  onSelectTicket: (id: string) => void;
}

export function AssistantPanel({ ticketId, onSelectTicket }: Props) {
  const [action, setAction] = useState<Action>("search_knowledge");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [filters, setFilters] = useState<TicketFilter>({});
  const [run, setRun] = useState<Run>({ status: "idle" });
  const latest = useRef(0); // only the newest request may update the panel

  // An answer about one ticket must not stay on screen next to another ticket.
  useEffect(() => {
    latest.current += 1;
    setRun({ status: "idle" });
  }, [ticketId, action]);

  function buildRequest(): AssistantRequest {
    const req: AssistantRequest = { action };
    if (USES_TICKET.includes(action) && ticketId) req.ticket_id = ticketId;
    if (USES_QUERY.includes(action) && query.trim()) req.query = query;
    if (USES_CATEGORY.includes(action) && category) req.category = category;
    if (action === "count_tickets") {
      req.filters = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
    }
    return req;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const id = ++latest.current;
    setRun({ status: "loading" });
    try {
      const response = await runAssistant(buildRequest());
      if (id === latest.current) setRun({ status: "done", response });
    } catch (err) {
      if (id === latest.current) setRun({ status: "error", error: toApiError(err) });
    }
  }

  const setFilter = (key: keyof TicketFilter) => (value: string) => setFilters({ ...filters, [key]: value });

  return (
    <section className="panel assistant" aria-label="Assistant">
      <h2>Assistant</h2>
      <form onSubmit={submit} className="assistant-form">
        <label className="field">
          <span>Action</span>
          <select value={action} onChange={(e) => setAction(e.target.value as Action)}>
            {ACTIONS.map((a) => (
              <option key={a} value={a}>
                {ACTION_LABELS[a]}
              </option>
            ))}
          </select>
        </label>

        {USES_TICKET.includes(action) && (
          <p className="small muted">
            Ticket: <span className="mono">{ticketId ?? "none selected"}</span>
          </p>
        )}

        {USES_QUERY.includes(action) && (
          <label className="field">
            <span>{action === "search_knowledge" ? "Question" : "Question (optional — defaults to the ticket text)"}</span>
            <textarea rows={3} value={query} onChange={(e) => setQuery(e.target.value)} />
          </label>
        )}

        {USES_CATEGORY.includes(action) && (
          <Select label="Category" value={category} options={CATEGORIES} onChange={setCategory} />
        )}

        {action === "count_tickets" && (
          <div className="filters">
            <Select label="Status" value={filters.status ?? ""} options={STATUSES} onChange={setFilter("status")} />
            <Select label="Priority" value={filters.priority ?? ""} options={PRIORITIES} onChange={setFilter("priority")} />
            <Select label="Category" value={filters.category ?? ""} options={CATEGORIES} onChange={setFilter("category")} />
          </div>
        )}

        <button type="submit" className="primary" disabled={run.status === "loading"}>
          {run.status === "loading" ? "Running…" : "Run"}
        </button>
      </form>

      {run.status === "idle" && <p className="muted">Pick an action and run it. Answers quote their sources.</p>}
      {run.status === "loading" && <p className="muted">Retrieving evidence…</p>}
      {run.status === "error" && <ErrorNote error={run.error} />}
      {run.status === "done" && <AnswerView response={run.response} onSelectTicket={onSelectTicket} />}
    </section>
  );
}
