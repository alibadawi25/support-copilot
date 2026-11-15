import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import type { Answer, AssistantResponse } from "../api";
import { AnswerView } from "./AnswerView";

function response(answer: Partial<Answer>): AssistantResponse {
  return {
    run_id: "run-1",
    answer: {
      action: "search_knowledge",
      state: "answered",
      text: "",
      reason: null,
      citations: [],
      ticket_ids: [],
      count: null,
      is_draft: false,
      ...answer,
    },
    retrieval: { method: "tfidf_cosine", top_k: 3, threshold: 0.15, top_score: 0.04 },
    tool_trace: [{ tool: "search_knowledge", arguments: { query: "sftp" }, ok: true, duration_ms: 3 }],
    limitations: ["No language model is involved."],
  };
}

test("no-evidence state shows the reason and zero citation cards", () => {
  render(
    <AnswerView
      onSelectTicket={() => {}}
      response={response({
        state: "insufficient_evidence",
        text: "Insufficient evidence: the available sources do not answer this.",
        reason: "No knowledge-base passage scored at or above the relevance threshold (0.15).",
      })}
    />,
  );

  expect(screen.getByRole("status")).toHaveTextContent("Insufficient evidence");
  expect(screen.getByRole("status")).toHaveTextContent("relevance threshold (0.15)");
  expect(screen.queryAllByTestId("citation")).toHaveLength(0);
  expect(screen.queryByLabelText("Reply draft")).not.toBeInTheDocument();
});

test("a draft is editable, labelled as not sent, and cites its sources", async () => {
  render(
    <AnswerView
      onSelectTicket={() => {}}
      response={response({
        action: "draft_reply",
        text: "DRAFT - review and edit before sending.",
        is_draft: true,
        citations: [
          {
            source_type: "article",
            source_id: "KB-01",
            chunk_id: "KB-01#chunk-0",
            title: "Payment failures",
            quote: "If the payment is pending, do not ask the customer to submit another payment.",
            score: 0.412,
            excerpt: null,
          },
        ],
      })}
    />,
  );

  expect(screen.getByText("Draft — not sent")).toBeInTheDocument();
  const editor = screen.getByLabelText("Reply draft");
  await userEvent.type(editor, " Edited.");
  expect(editor).toHaveValue("DRAFT - review and edit before sending. Edited.");
  expect(screen.getAllByTestId("citation")).toHaveLength(1);
  expect(screen.getByText("sentence score 0.412")).toBeInTheDocument();
});
