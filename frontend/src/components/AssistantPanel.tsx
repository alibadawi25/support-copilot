import { type FormEvent, type KeyboardEvent, useEffect, useId, useRef, useState } from "react";
import {
  ACTIONS,
  MAX_KEYWORD_CHARS,
  MAX_QUERY_CHARS,
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
import { EmptyState, Skeleton } from "./Bits";
import { ErrorNote } from "./ErrorNote";
import { Icon, type IconName } from "./Icon";
import { Select } from "./Select";

const ACTION_INFO: Record<Action, { label: string; hint: string; icon: IconName }> = {
  search_knowledge: { label: "Search KB", icon: "book", hint: "Answer a question with quoted knowledge-base sentences." },
  summarize_ticket: { label: "Summarize", icon: "list", hint: "Condense the selected ticket and list the key facts still needed." },
  similar_tickets: { label: "Similar", icon: "layers", hint: "Find resolved tickets like this one and how they were fixed." },
  draft_reply: { label: "Draft reply", icon: "pen", hint: "Write an editable reply from documented guidance. Never sent." },
  count_tickets: { label: "Count", icon: "hash", hint: "Count tickets that match the filters and mention the given words." },
};

// Which inputs each action shows. The server decides what is *required* (422).
const USES_TICKET: Action[] = ["summarize_ticket", "draft_reply", "similar_tickets"];
const NEEDS_TICKET: Action[] = ["summarize_ticket", "draft_reply"];
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
  const queryId = useId();
  const keywordId = useId();

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
      req.filters = Object.fromEntries(Object.entries(filters).filter(([, v]) => v?.trim()));
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

  function submitOnCtrlEnter(event: KeyboardEvent<HTMLFormElement>) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      event.currentTarget.requestSubmit();
    }
  }

  const setFilter = (key: keyof TicketFilter) => (value: string) => setFilters({ ...filters, [key]: value });
  const loading = run.status === "loading";

  return (
    <section className="panel assistant" aria-label="Assistant">
      <div className="panel-head">
        <h2>Assistant</h2>
        <span className="small muted">evidence-only</span>
      </div>

      <div className="panel-body">
        <form onSubmit={submit} onKeyDown={submitOnCtrlEnter} className="assistant-form">
          <fieldset className="actions">
            <legend className="sr-only">Action</legend>
            {ACTIONS.map((a) => (
              <label key={a} className="action-option">
                <input
                  type="radio"
                  name="action"
                  value={a}
                  checked={action === a}
                  onChange={() => setAction(a)}
                />
                <Icon name={ACTION_INFO[a].icon} />
                {ACTION_INFO[a].label}
              </label>
            ))}
          </fieldset>
          <p className="small muted">{ACTION_INFO[action].hint}</p>

          {USES_TICKET.includes(action) &&
            (ticketId ? (
              <p className="context-chip">
                <Icon name="ticket" size={14} />
                Using <span className="mono">{ticketId}</span>
              </p>
            ) : (
              <p className={`context-chip ${NEEDS_TICKET.includes(action) ? "is-missing" : ""}`}>
                <Icon name="info" size={14} />
                {NEEDS_TICKET.includes(action)
                  ? "Select a ticket in the queue first."
                  : "No ticket selected: describe the problem below."}
              </p>
            ))}

          {USES_QUERY.includes(action) && (
            <div className="field">
              <label htmlFor={queryId}>
                {action === "search_knowledge" ? "Question" : "Extra detail (optional — added to the ticket text)"}
              </label>
              <textarea
                id={queryId}
                rows={3}
                value={query}
                maxLength={MAX_QUERY_CHARS}
                aria-describedby={`${queryId}-count`}
                placeholder="e.g. Customer was charged twice for one order"
                onChange={(e) => setQuery(e.target.value)}
              />
              <span id={`${queryId}-count`} className="char-count">
                {query.length} / {MAX_QUERY_CHARS}
              </span>
            </div>
          )}

          {USES_CATEGORY.includes(action) && (
            <Select label="Category" value={category} options={CATEGORIES} onChange={setCategory} />
          )}

          {action === "count_tickets" && (
            <div className="filters">
              <Select label="Status" value={filters.status ?? ""} options={STATUSES} onChange={setFilter("status")} />
              <Select label="Priority" value={filters.priority ?? ""} options={PRIORITIES} onChange={setFilter("priority")} />
              <Select label="Category" value={filters.category ?? ""} options={CATEGORIES} onChange={setFilter("category")} />
              <div className="field field-wide">
                <label htmlFor={keywordId}>Mentions (optional — every word must appear)</label>
                <input
                  id={keywordId}
                  type="text"
                  value={filters.keyword ?? ""}
                  maxLength={MAX_KEYWORD_CHARS}
                  placeholder="e.g. checkout"
                  onChange={(e) => setFilter("keyword")(e.target.value)}
                />
              </div>
            </div>
          )}

          <div className="run-row">
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? <span className="spinner" aria-hidden="true" /> : <Icon name="play" size={14} />}
              {loading ? "Running…" : "Run"}
            </button>
            <span className="small muted">
              <kbd>Ctrl</kbd> + <kbd>Enter</kbd>
            </span>
          </div>
        </form>

        {run.status === "idle" && (
          <EmptyState icon="book" title="Pick an action and run it.">
            <p className="small muted">Every answer quotes its sources, or says it has none.</p>
          </EmptyState>
        )}
        {run.status === "loading" && (
          <>
            <p className="muted small" role="status">
              Retrieving evidence…
            </p>
            <Skeleton lines={5} />
          </>
        )}
        {run.status === "error" && <ErrorNote error={run.error} />}
        {run.status === "done" && (
          // key: a new run starts with no citation highlighted and a fresh draft
          <AnswerView key={run.response.run_id} response={run.response} onSelectTicket={onSelectTicket} />
        )}
      </div>
    </section>
  );
}
