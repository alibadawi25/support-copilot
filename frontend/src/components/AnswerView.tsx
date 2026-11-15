import type { AssistantResponse, Citation } from "../api";
import { DraftEditor } from "./DraftEditor";

interface Props {
  response: AssistantResponse;
  onSelectTicket: (id: string) => void;
}

const score = (value: number | null) => (value === null ? "—" : value.toFixed(3));

export function AnswerView({ response, onSelectTicket }: Props) {
  const { answer, retrieval, tool_trace, limitations } = response;
  const insufficient = answer.state === "insufficient_evidence";

  return (
    <div className="answer">
      {insufficient ? (
        <div className="note note-warn" role="status">
          <strong>Insufficient evidence</strong>
          <p>{answer.reason ?? answer.text}</p>
          <p className="small">Nothing was answered or drafted. Escalate or rephrase the question.</p>
        </div>
      ) : answer.is_draft ? (
        // key: a new run must replace the agent's edits to the previous draft
        <DraftEditor key={response.run_id} initialText={answer.text} />
      ) : (
        <pre className="answer-text">{answer.text}</pre>
      )}

      {answer.ticket_ids.length > 0 && (
        <p className="small">
          Tickets:{" "}
          {answer.ticket_ids.map((id) => (
            <button key={id} type="button" className="link mono" onClick={() => onSelectTicket(id)}>
              {id}
            </button>
          ))}
        </p>
      )}

      <h3>Citations ({answer.citations.length})</h3>
      {answer.citations.length === 0 ? (
        <p className="muted small">No sources cited.</p>
      ) : (
        <ul className="citations">
          {answer.citations.map((c, i) => (
            <CitationCard key={i} citation={c} />
          ))}
        </ul>
      )}

      {retrieval && (
        <p className="small muted">
          Retrieval: {retrieval.method} · top {retrieval.top_k}
          {retrieval.threshold !== null && ` · threshold ${retrieval.threshold}`}
          {retrieval.threshold !== null && ` · best score ${score(retrieval.top_score)}`}
        </p>
      )}

      <details>
        <summary>Tool trace ({tool_trace.length})</summary>
        <ol className="trace">
          {tool_trace.map((call, i) => (
            <li key={i}>
              <span className="mono">{call.tool}</span>{" "}
              <span className={call.ok ? "ok" : "fail"}>{call.ok ? "ok" : "failed"}</span>{" "}
              <span className="muted">{call.duration_ms.toFixed(0)} ms</span>
              <pre>{JSON.stringify(call.arguments, null, 1)}</pre>
            </li>
          ))}
        </ol>
      </details>

      <ul className="limitations small muted">
        {limitations.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <p className="small muted mono">run {response.run_id}</p>
    </div>
  );
}

function CitationCard({ citation: c }: { citation: Citation }) {
  return (
    <li className="citation" data-testid="citation">
      <div className="row-top">
        <span className="mono">{c.chunk_id ?? c.source_id}</span>
        <span className="badge">{c.source_type}</span>
        {/* Article quotes carry a per-sentence cosine score, which can sit below the passage threshold. */}
        {c.score !== null && (
          <span className="muted small">
            {c.source_type === "article" ? "sentence score" : "bm25 score"} {score(c.score)}
          </span>
        )}
      </div>
      <div className="small">{c.title}</div>
      <blockquote>{c.quote}</blockquote>
      {c.excerpt && c.excerpt !== c.quote && (
        <details>
          <summary>Show passage</summary>
          <p className="prose small">{c.excerpt}</p>
        </details>
      )}
    </li>
  );
}
