import { expect, test } from "vitest";
import type { Citation } from "./api";
import { splitMarkers } from "./markers";
import { relativeTime } from "./time";

const NOW = Date.parse("2026-11-17T12:00:00Z");

test("relativeTime picks the largest whole unit", () => {
  expect(relativeTime("2026-11-17T11:59:40Z", NOW)).toBe("just now");
  expect(relativeTime("2026-11-17T09:00:00Z", NOW)).toBe("3 hours ago");
  expect(relativeTime("2026-11-16T12:00:00Z", NOW)).toBe("yesterday");
  expect(relativeTime("2026-09-15T09:00:00Z", NOW)).toBe("2 months ago");
  expect(relativeTime("not a date", NOW)).toBe("not a date");
});

function cite(chunk_id: string, quote: string): Citation {
  return { source_type: "article", source_id: "KB-01", chunk_id, title: "t", quote, score: null, context: false, excerpt: null };
}

test("markers resolve to the citation quoted on the same line", () => {
  const citations = [cite("KB-01#chunk-0", "First."), cite("KB-01#chunk-0", "Second.")];
  const parts = splitMarkers("- First. [KB-01#chunk-0]\n- Second. [KB-01#chunk-0]", citations);
  expect(parts).toEqual([
    "- First. ",
    { index: 0, label: "KB-01#chunk-0" },
    "\n",
    "- Second. ",
    { index: 1, label: "KB-01#chunk-0" },
  ]);
});

test("a bracket that names no citation stays plain text", () => {
  expect(splitMarkers("Order [ABC-9] failed", [cite("KB-01#chunk-0", "x")])).toEqual(["Order [ABC-9] failed"]);
});
