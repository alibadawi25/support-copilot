import { useState } from "react";
import { Icon } from "./Icon";

/** Editable reply draft. There is deliberately no send action anywhere in the app. */
export function DraftEditor({ initialText }: { initialText: string }) {
  const [text, setText] = useState(initialText);
  const [copied, setCopied] = useState<"yes" | "failed" | null>(null);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied("yes");
    } catch {
      setCopied("failed"); // clipboard needs a secure context / permission
    }
  }

  return (
    <div className="draft">
      <div className="draft-head">
        <span className="pill draft-label">
          <Icon name="pen" size={12} />
          Draft — not sent
        </span>
        <span className="small muted" role="status">
          {copied === "yes" && "Copied"}
          {copied === "failed" && "Copy failed — select the text and copy manually"}
        </span>
        <button type="button" className="btn btn-sm" onClick={copy}>
          <Icon name="copy" size={14} />
          Copy
        </button>
      </div>
      <textarea
        aria-label="Reply draft"
        rows={14}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setCopied(null);
        }}
      />
      <p className="small muted">Edit freely. Copy it into your helpdesk to send — this app never sends anything.</p>
    </div>
  );
}
