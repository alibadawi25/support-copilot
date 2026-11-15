import { CATEGORIES, PRIORITIES, STATUSES, type TicketFilter, type TicketSummary } from "../api";
import type { Load } from "../useLoad";
import { ErrorNote } from "./ErrorNote";
import { Select } from "./Select";

interface Props {
  filter: TicketFilter;
  onFilter: (filter: TicketFilter) => void;
  tickets: Load<TicketSummary[]>;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onRetry: () => void;
}

export function TicketQueue({ filter, onFilter, tickets, selectedId, onSelect, onRetry }: Props) {
  const set = (key: keyof TicketFilter) => (value: string) => onFilter({ ...filter, [key]: value });

  return (
    <section className="panel queue" aria-label="Ticket queue">
      <h2>Tickets</h2>
      <div className="filters">
        <Select label="Status" value={filter.status ?? ""} options={STATUSES} onChange={set("status")} />
        <Select label="Priority" value={filter.priority ?? ""} options={PRIORITIES} onChange={set("priority")} />
        <Select label="Category" value={filter.category ?? ""} options={CATEGORIES} onChange={set("category")} />
      </div>

      {tickets.status === "loading" && <p className="muted">Loading tickets…</p>}
      {tickets.status === "error" && <ErrorNote error={tickets.error} onRetry={onRetry} />}
      {tickets.status === "ready" && tickets.data.length === 0 && (
        <p className="muted">No tickets match these filters.</p>
      )}
      {tickets.status === "ready" && (
        <ul className="ticket-list">
          {tickets.data.map((t) => (
            <li key={t.id}>
              <button
                type="button"
                className="ticket-row"
                aria-current={t.id === selectedId}
                onClick={() => onSelect(t.id)}
              >
                <span className="row-top">
                  <span className="mono">{t.id}</span>
                  <span className={`badge priority-${t.priority}`}>{t.priority}</span>
                  <span className={`badge status-${t.status}`}>{t.status}</span>
                  {t.reviewed_at && <span className="badge reviewed">✓ reviewed</span>}
                </span>
                <span className="row-title">{t.title}</span>
                <span className="muted small">{t.category.replace(/_/g, " ")}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
