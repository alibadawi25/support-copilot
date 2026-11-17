import type { ReactNode } from "react";
import { fullDate, relativeTime } from "../time";
import { Icon, type IconName } from "./Icon";

// Small presentational pieces shared by the panels.

export function PriorityPill({ priority }: { priority: string }) {
  return (
    <span className={`pill prio-${priority}`}>
      <span className="dot" aria-hidden="true" />
      {priority}
    </span>
  );
}

export function StatusPill({ status }: { status: string }) {
  return <span className={`pill status-${status}`}>{status}</span>;
}

/** Relative time with the absolute time on hover. */
export function When({ iso }: { iso: string }) {
  return (
    <time dateTime={iso} title={fullDate(iso)}>
      {relativeTime(iso)}
    </time>
  );
}

export function EmptyState({ icon, title, children }: { icon: IconName; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Icon name={icon} size={22} />
      </span>
      <p className="empty-title">{title}</p>
      {children}
    </div>
  );
}

/** Placeholder lines while loading; the caller announces the loading text. */
export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="skeleton" aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <span key={i} className="skeleton-line" style={{ width: `${92 - (i % 3) * 18}%` }} />
      ))}
    </div>
  );
}
