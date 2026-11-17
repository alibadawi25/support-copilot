import type { ApiError, ErrorKind } from "../api";
import { Icon } from "./Icon";

const TITLES: Record<ErrorKind, string> = {
  validation: "Check the request",
  not_found: "Not found",
  unavailable: "Assistant data service unavailable",
  network: "API unreachable",
  server: "Something went wrong",
};

export function ErrorNote({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  return (
    <div className={`callout callout-${error.kind === "validation" ? "warn" : "error"}`} role="alert">
      <Icon name="alert" />
      <div>
        <strong>{TITLES[error.kind]}</strong>
        <p>{error.message}</p>
        {onRetry && error.kind !== "validation" && (
          <button type="button" className="btn btn-sm" onClick={onRetry}>
            Retry
          </button>
        )}
      </div>
    </div>
  );
}
