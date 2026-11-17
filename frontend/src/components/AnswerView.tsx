import { useRef, useState } from "react";
import type { AssistantResponse, Citation, RetrievalInfo } from "../api";
import { splitMarkers } from "../markers";
import { DraftEditor } from "./DraftEditor";
import { Icon } from "./Icon";

interface Props {
  response: AssistantResponse;
  onSelectTicket: (id: string) => void;
}

const score = (value: number | null) => (value === null ? "—" : value.toFixed(3));
const keyOf = (c: Citation) => c.chunk_id ?? c.source_id;

export function AnswerView({ response, onSelectTicket }: Props) {
  const { answer, retrieval, tool_trace, limitations } = response;
  const insufficient = answer.state === "insufficient_evidence";
  const [active, setActive] = useState<number | null>(null);
  const cards = useRef<(HTMLLIElement | null)[]>([]);

  function showCitation(index: number) {
    setActive(index);
    cards.current[index]?.scrollIntoView({ block: "nearest" });
  }

  // Score bars are relative to the best citation in this answer: scores of different kinds
  // (sentence cosine, BM25) are not comparable with each other or across answers.
  const maxScore = Math.max(0, ...answer.citations.map((c) => c.score ?? 0));

  return (
    <div className="answer">
      {insufficient ? (
        <div className="callout callout-warn" role="status">
          <Icon name="alert" />
          <div>
            <strong>Insufficient evidence</strong>
            <p>{answer.reason ?? answer.text}</p>
            <p className="small">
              Nothing was answered or drafted. Rephrase with the customer's own words, pick a category, or escalate.
            </p>
          </div>
        </div>
      ) : answer.is_draft ? (
        <DraftEditor initialText={answer.text} />
      ) : answer.count !== null ? (
        <div className="count-card">
          <span className="count-num">{answer.count}</span>
          <p>{answer.text}</p>
        </div>
      ) : (
        <div className="answer-text">
          {splitMarkers(answer.text, answer.citations).map((part, i) =>
            typeof part === "string" ? (
              part
            ) : (
              <button
                key={i}
                type="button"
                className="cite-chip"
                title={`${part.label}: ${answer.citations[part.index].quote}`}
                aria-label={`Source ${part.index + 1}: ${part.label}`}
                onClick={() => showCitation(part.index)}
              >
                {part.index + 1}
              </button>
            ),
          )}
        </div>
      )}

      {answer.ticket_ids.length > 0 && (
        <p className="row-tags">
          <span className="small muted">Tickets</span>
          {answer.ticket_ids.map((id) => (
            <button key={id} type="button" className="ticket-chip mono" onClick={() => onSelectTicket(id)}>
              <Icon name="ticket" size={12} />
              {id}
            </button>
          ))}
        </p>
      )}

      {/* A count is read straight from the database: it has no sources to cite. */}
      {answer.count === null && (
        <div className="section-head">
          <h3>Citations ({answer.citations.length})</h3>
        </div>
      )}
      {retrieval && <RetrievalMeter retrieval={retrieval} />}
      {answer.count !== null ? null : answer.citations.length === 0 ? (
        <p className="muted small">No sources cited.</p>
      ) : (
        <ul className="citations">
          {answer.citations.map((c, i) => (
            <CitationCard
              key={i}
              ref={(el) => {
                cards.current[i] = el;
              }}
              number={i + 1}
              citation={c}
              active={active === i}
              barWidth={c.score !== null && maxScore > 0 ? c.score / maxScore : null}
              onOpenTicket={c.source_type === "ticket" ? () => onSelectTicket(c.source_id) : undefined}
            />
          ))}
        </ul>
      )}

      <details className="how">
        <summary>
          How this was answered · {tool_trace.length} tool {tool_trace.length === 1 ? "call" : "calls"}
        </summary>
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
        <ul className="limitations small muted">
          {limitations.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <p className="small muted mono">run {response.run_id}</p>
      </details>
    </div>
  );
}

/** Best passage score against the acceptance threshold: shows why it answered or refused. */
function RetrievalMeter({ retrieval: r }: { retrieval: RetrievalInfo }) {
  const method = `${r.method.replace(/_/g, " ")} · top ${r.top_k}`;
  if (r.threshold === null) return <p className="small muted">Retrieval: {method}</p>;
  const best = r.top_score ?? 0;
  const scale = Math.max(best, r.threshold) * 1.25 || 1;
  const passed = best >= r.threshold;
  return (
    <div className="meter-wrap small">
      <div className="meter-label">
        <span className="muted">Retrieval: {method}</span>
        <span className={passed ? "ok" : "fail"}>
          best {score(r.top_score)} {passed ? "≥" : "<"} threshold {r.threshold}
        </span>
      </div>
      <div className="meter" aria-hidden="true">
        <span className={`meter-fill ${passed ? "is-pass" : "is-fail"}`} style={{ width: `${(best / scale) * 100}%` }} />
        <span className="meter-tick" style={{ left: `${(r.threshold / scale) * 100}%` }} />
      </div>
    </div>
  );
}

interface CardProps {
  ref: (el: HTMLLIElement | null) => void;
  number: number;
  citation: Citation;
  active: boolean;
  barWidth: number | null;
  onOpenTicket?: () => void;
}

function CitationCard({ ref, number, citation: c, active, barWidth, onOpenTicket }: CardProps) {
  return (
    <li ref={ref} className={`citation ${active ? "is-active" : ""}`} data-testid="citation">
      <div className="citation-head">
        <span className="cite-num">{number}</span>
        <Icon name={c.source_type === "article" ? "book" : "ticket"} size={14} />
        <span className="mono">{keyOf(c)}</span>
        <span className="tag">{c.source_type}</span>
        {onOpenTicket && (
          <button type="button" className="btn btn-xs btn-ghost" onClick={onOpenTicket}>
            Open
          </button>
        )}
      </div>
      <div className="citation-title">{c.title}</div>
      <blockquote>{c.quote}</blockquote>
      {/* Article quotes carry a per-sentence cosine score, which can sit below the passage threshold. */}
      {c.score !== null && (
        <div className="score-row">
          <span className="muted small">
            {c.source_type === "article" ? "best sentence score" : "bm25 score"} {score(c.score)}
          </span>
          {barWidth !== null && (
            <span className="score-bar" aria-hidden="true">
              <span style={{ width: `${barWidth * 100}%` }} />
            </span>
          )}
        </div>
      )}
      {c.excerpt && c.excerpt !== c.quote && (
        <details>
          <summary>Show passage</summary>
          <p className="prose small">{c.excerpt}</p>
        </details>
      )}
    </li>
  );
}
