import { useState } from "react";

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
        <span className="badge draft-label">Draft — not sent</span>
        <button type="button" onClick={copy}>
          Copy
        </button>
        <span className="small muted" role="status">
          {copied === "yes" && "Copied"}
          {copied === "failed" && "Copy failed — select the text and copy manually"}
        </span>
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
    </div>
  );
}
