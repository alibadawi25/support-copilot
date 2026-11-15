import { useState } from "react";
import { type ApiError, type TicketDetail, setReviewed } from "../api";
import { type Load, toApiError } from "../useLoad";
import { ErrorNote } from "./ErrorNote";

interface Props {
  ticket: Load<TicketDetail> | null; // null = nothing selected
  onChange: (ticket: TicketDetail) => void;
  onRetry: () => void;
}

export function TicketDetailView({ ticket, onChange, onRetry }: Props) {
  return (
    <section className="panel detail" aria-label="Ticket detail">
      {ticket === null && <p className="muted">Select a ticket to see its details.</p>}
      {ticket?.status === "loading" && <p className="muted">Loading ticket…</p>}
      {ticket?.status === "error" && <ErrorNote error={ticket.error} onRetry={onRetry} />}
      {ticket?.status === "ready" && <Detail ticket={ticket.data} onChange={onChange} />}
    </section>
  );
}

function Detail({ ticket, onChange }: { ticket: TicketDetail; onChange: (t: TicketDetail) => void }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function toggleReviewed() {
    setSaving(true);
    setError(null);
    try {
      onChange(await setReviewed(ticket.id, !ticket.reviewed_at));
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <header className="detail-head">
        <div>
          <span className="mono">{ticket.id}</span>
          <h2>{ticket.title}</h2>
        </div>
        <button type="button" onClick={toggleReviewed} disabled={saving}>
          {ticket.reviewed_at ? "Unmark reviewed" : "Mark reviewed"}
        </button>
      </header>
      {error && <ErrorNote error={error} />}

      <dl className="meta">
        <Meta label="Status" value={ticket.status} />
        <Meta label="Priority" value={ticket.priority} />
        <Meta label="Category" value={ticket.category.replace(/_/g, " ")} />
        <Meta label="Product area" value={ticket.product_area} />
        <Meta label="Created" value={ticket.created_at} />
        <Meta label="Updated" value={ticket.updated_at} />
        <Meta label="Reviewed" value={ticket.reviewed_at ?? "Not reviewed"} />
      </dl>

      <h3>Description</h3>
      <p className="prose">{ticket.description}</p>

      <h3>Timeline</h3>
      {ticket.messages.length === 0 ? (
        <p className="muted">No messages.</p>
      ) : (
        <ol className="timeline">
          {ticket.messages.map((m, i) => (
            <li key={i}>
              <span className="small">
                <strong>{m.author}</strong> <span className="muted">{m.at}</span>
              </span>
              <p className="prose">{m.text}</p>
            </li>
          ))}
        </ol>
      )}

      {ticket.resolution_summary && (
        <>
          <h3>Resolution</h3>
          <p className="prose">{ticket.resolution_summary}</p>
        </>
      )}
    </>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
