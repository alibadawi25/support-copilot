import { type KeyboardEvent, useRef, useState } from "react";
import { CATEGORIES, PRIORITIES, STATUSES, type TicketFilter, type TicketSummary } from "../api";
import type { Load } from "../useLoad";
import { EmptyState, PriorityPill, Skeleton, StatusPill, When } from "./Bits";
import { ErrorNote } from "./ErrorNote";
import { Icon } from "./Icon";
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
  // Text search is client-side: the queue is small and the API filters only by field.
  const [search, setSearch] = useState("");
  const list = useRef<HTMLUListElement>(null);
  const set = (key: keyof TicketFilter) => (value: string) => onFilter({ ...filter, [key]: value });

  const all = tickets.status === "ready" ? tickets.data : [];
  const needle = search.trim().toLowerCase();
  const visible = all.filter((t) => `${t.id} ${t.title}`.toLowerCase().includes(needle));
  const narrowed = Boolean(needle || filter.status || filter.priority || filter.category);

  function clear() {
    setSearch("");
    onFilter({});
  }

  // Up/Down moves the selection through the visible rows, from the search box or the list.
  function onArrow(event: KeyboardEvent) {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    const at = visible.findIndex((t) => t.id === selectedId);
    const step = event.key === "ArrowDown" ? 1 : -1;
    const next = visible[Math.min(Math.max(at + step, 0), visible.length - 1)];
    if (!next) return;
    onSelect(next.id);
    list.current?.querySelector<HTMLButtonElement>(`[data-id="${next.id}"]`)?.focus();
  }

  return (
    <section className="panel queue" aria-label="Ticket queue">
      <div className="panel-head">
        <h2>Tickets</h2>
        {tickets.status === "ready" && (
          <span className="count-pill" aria-live="polite">
            {narrowed ? `${visible.length} of ${all.length}` : all.length}
          </span>
        )}
      </div>

      <div className="panel-body">
        <label className="search">
          <Icon name="search" />
          <input
            type="search"
            aria-label="Search tickets"
            placeholder="Search ID or title"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={onArrow}
          />
        </label>
        <div className="filters">
          <Select label="Status" value={filter.status ?? ""} options={STATUSES} onChange={set("status")} />
          <Select label="Priority" value={filter.priority ?? ""} options={PRIORITIES} onChange={set("priority")} />
          <Select label="Category" value={filter.category ?? ""} options={CATEGORIES} onChange={set("category")} />
        </div>

        {tickets.status === "loading" && (
          <>
            <p className="sr-only" role="status">
              Loading tickets…
            </p>
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="ticket-row is-placeholder">
                <Skeleton lines={2} />
              </div>
            ))}
          </>
        )}
        {tickets.status === "error" && <ErrorNote error={tickets.error} onRetry={onRetry} />}
        {tickets.status === "ready" && visible.length === 0 && (
          <EmptyState icon="inbox" title="No tickets match these filters.">
            {narrowed && (
              <button type="button" className="btn btn-sm" onClick={clear}>
                Clear filters
              </button>
            )}
          </EmptyState>
        )}
        {visible.length > 0 && (
          <ul className="ticket-list" ref={list} onKeyDown={onArrow}>
            {visible.map((t) => (
              <li key={t.id}>
                <button
                  type="button"
                  className="ticket-row"
                  data-id={t.id}
                  aria-current={t.id === selectedId}
                  onClick={() => onSelect(t.id)}
                >
                  <span className="row-top">
                    <span className="mono id">{t.id}</span>
                    <span className="row-time">
                      <When iso={t.updated_at} />
                    </span>
                  </span>
                  <span className="row-title">{t.title}</span>
                  <span className="row-tags">
                    <PriorityPill priority={t.priority} />
                    <StatusPill status={t.status} />
                    {t.reviewed_at && (
                      <span className="pill pill-ok">
                        <Icon name="check" size={12} />
                        reviewed
                      </span>
                    )}
                    <span className="tag">{t.category.replace(/_/g, " ")}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <p className="panel-foot small muted">
        <kbd>↑</kbd> <kbd>↓</kbd> to move through tickets
      </p>
    </section>
  );
}
