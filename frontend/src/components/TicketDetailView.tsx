import { type ReactNode, useState } from "react";
import { type ApiError, type TicketDetail, setReviewed } from "../api";
import { type Load, toApiError } from "../useLoad";
import { EmptyState, PriorityPill, Skeleton, StatusPill, When } from "./Bits";
import { ErrorNote } from "./ErrorNote";
import { Icon } from "./Icon";

interface Props {
  ticket: Load<TicketDetail> | null; // null = nothing selected
  onChange: (ticket: TicketDetail) => void;
  onRetry: () => void;
}

export function TicketDetailView({ ticket, onChange, onRetry }: Props) {
  return (
    <section className="panel detail" aria-label="Ticket detail">
      {ticket === null && (
        <EmptyState icon="ticket" title="Select a ticket to see its details.">
          <p className="small muted">Pick one from the queue, or use the arrow keys.</p>
        </EmptyState>
      )}
      {ticket?.status === "loading" && (
        <div className="panel-body">
          <p className="sr-only" role="status">
            Loading ticket…
          </p>
          <Skeleton lines={2} />
          <Skeleton lines={6} />
        </div>
      )}
      {ticket?.status === "error" && (
        <div className="panel-body">
          <ErrorNote error={ticket.error} onRetry={onRetry} />
        </div>
      )}
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
      <header className="panel-head detail-head">
        <div className="detail-title">
          <span className="row-tags">
            <span className="id-chip mono">{ticket.id}</span>
            <PriorityPill priority={ticket.priority} />
            <StatusPill status={ticket.status} />
          </span>
          <h2>{ticket.title}</h2>
        </div>
        {ticket.reviewed_at ? (
          <span className="reviewed-state">
            <span className="pill pill-ok">
              <Icon name="check" size={12} />
              reviewed <When iso={ticket.reviewed_at} />
            </span>
            <button type="button" className="btn btn-sm btn-ghost" onClick={toggleReviewed} disabled={saving}>
              Unmark reviewed
            </button>
          </span>
        ) : (
          <button type="button" className="btn" onClick={toggleReviewed} disabled={saving}>
            <Icon name="check" />
            Mark reviewed
          </button>
        )}
      </header>

      <div className="panel-body">
        {error && <ErrorNote error={error} />}

        <dl className="meta">
          <Meta label="Category">{ticket.category.replace(/_/g, " ")}</Meta>
          <Meta label="Product area">{ticket.product_area.replace(/_/g, " ")}</Meta>
          <Meta label="Created">
            <When iso={ticket.created_at} />
          </Meta>
          <Meta label="Updated">
            <When iso={ticket.updated_at} />
          </Meta>
        </dl>

        <h3>Description</h3>
        <p className="prose">{ticket.description}</p>

        <h3>Timeline</h3>
        {ticket.messages.length === 0 ? (
          <p className="muted">No messages.</p>
        ) : (
          <ol className="timeline">
            {ticket.messages.map((m, i) => (
              <li key={i} className={`msg msg-${m.author}`}>
                <span className="avatar" aria-hidden="true">
                  {m.author.charAt(0).toUpperCase()}
                </span>
                <div className="msg-body">
                  <div className="msg-head">
                    <strong>{m.author}</strong>
                    <span className="muted small">
                      <When iso={m.at} />
                    </span>
                  </div>
                  <p className="prose">{m.text}</p>
                </div>
              </li>
            ))}
          </ol>
        )}

        {ticket.resolution_summary && (
          <div className="callout callout-ok">
            <Icon name="shield" />
            <div>
              <strong>Resolution</strong>
              <p className="prose">{ticket.resolution_summary}</p>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

function Meta({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}
