import type { Citation } from "./api";

/** Plain text, or a source marker resolved to an index into `citations`. */
export type Segment = string | { index: number; label: string };

const MARKER = /\[([^\]\s]+)\]/g;

/**
 * Split answer text on the composer's `[KB-01#chunk-0]` / `[T-101]` markers so they can be
 * rendered as links to their citation cards. Display only: the text itself is not changed,
 * and a bracket that names no citation stays plain text.
 */
export function splitMarkers(text: string, citations: Citation[]): Segment[] {
  const out: Segment[] = [];
  text.split("\n").forEach((line, n) => {
    if (n > 0) out.push("\n");
    let last = 0;
    for (const match of line.matchAll(MARKER)) {
      const index = citationFor(match[1], line, citations);
      if (index < 0) continue;
      out.push(line.slice(last, match.index));
      out.push({ index, label: match[1] });
      last = match.index + match[0].length;
    }
    out.push(line.slice(last));
  });
  return out.filter((segment) => segment !== "");
}

// Several sentences can come from one chunk, so prefer the citation quoted on this line.
function citationFor(key: string, line: string, citations: Citation[]): number {
  const matches = citations.flatMap((c, i) => ((c.chunk_id ?? c.source_id) === key ? [i] : []));
  return matches.find((i) => line.includes(citations[i].quote)) ?? matches[0] ?? -1;
}
