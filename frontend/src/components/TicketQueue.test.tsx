import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { expect, test } from "vitest";
import type { TicketSummary } from "../api";
import { TicketQueue } from "./TicketQueue";

const row = (id: string, title: string): TicketSummary => ({
  id,
  title,
  category: "billing",
  priority: "high",
  status: "open",
  updated_at: "2026-11-01T00:00:00Z",
  reviewed_at: null,
});
const TICKETS = [row("T-101", "Card declined"), row("T-102", "Missing invoice"), row("T-103", "Invoice address")];

function Harness() {
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <TicketQueue
      filter={{}}
      onFilter={() => {}}
      tickets={{ status: "ready", data: TICKETS }}
      selectedId={selected}
      onSelect={setSelected}
      onRetry={() => {}}
    />
  );
}

const current = () => document.querySelector('[aria-current="true"]')?.getAttribute("data-id");

test("search narrows the queue and arrow keys move the selection", async () => {
  render(<Harness />);
  const search = screen.getByLabelText("Search tickets");

  await userEvent.type(search, "invoice");
  expect(screen.getByText("2 of 3")).toBeInTheDocument(); // case-insensitive title match

  await userEvent.keyboard("{ArrowDown}");
  expect(current()).toBe("T-102");
  await userEvent.keyboard("{ArrowDown}{ArrowDown}"); // stops at the last row
  expect(current()).toBe("T-103");
  await userEvent.keyboard("{ArrowUp}");
  expect(current()).toBe("T-102");
});

test("an empty result offers to clear the search", async () => {
  render(<Harness />);
  await userEvent.type(screen.getByLabelText("Search tickets"), "zzz");
  expect(screen.getByText("No tickets match these filters.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  expect(screen.getByText("3")).toBeInTheDocument();
});
