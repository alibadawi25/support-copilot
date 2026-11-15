import type { ApiError, ErrorKind } from "../api";

const TITLES: Record<ErrorKind, string> = {
  validation: "Check the request",
  not_found: "Not found",
  unavailable: "Assistant data service unavailable",
  network: "API unreachable",
  server: "Something went wrong",
};

export function ErrorNote({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  return (
    <div className={`note note-${error.kind === "validation" ? "warn" : "error"}`} role="alert">
      <strong>{TITLES[error.kind]}</strong>
      <p>{error.message}</p>
      {onRetry && error.kind !== "validation" && (
        <button type="button" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}
