import { useState } from "react";
import { type TicketDetail, type TicketFilter, getTicket, listTickets } from "./api";
import { AssistantPanel } from "./components/AssistantPanel";
import { TicketDetailView } from "./components/TicketDetailView";
import { TicketQueue } from "./components/TicketQueue";
import { useLoad } from "./useLoad";

export function App() {
  const [filter, setFilter] = useState<TicketFilter>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0); // bumped by Retry to refetch
  const retry = () => setAttempt((n) => n + 1);

  const [tickets, setTickets] = useLoad(`${JSON.stringify(filter)}#${attempt}`, () => listTickets(filter));
  const [ticket, setTicket] = useLoad(selectedId && `${selectedId}#${attempt}`, () => getTicket(selectedId!));

  // After "mark reviewed": update the open ticket and its row in the queue.
  function onTicketChange(updated: TicketDetail) {
    setTicket({ status: "ready", data: updated });
    if (tickets.status === "ready") {
      const data = tickets.data.map((t) => (t.id === updated.id ? { ...t, reviewed_at: updated.reviewed_at } : t));
      setTickets({ status: "ready", data });
    }
  }

  return (
    <div className="app">
      <header className="app-head">
        <h1>
          Support <em>Copilot</em>
        </h1>
        <ul className="app-badges" aria-label="Guarantees">
          <li>Offline</li>
          <li>Evidence-only answers</li>
          <li>Drafts are never sent</li>
        </ul>
      </header>
      <main className="layout">
        <TicketQueue
          filter={filter}
          onFilter={setFilter}
          tickets={tickets}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onRetry={retry}
        />
        <TicketDetailView ticket={selectedId ? ticket : null} onChange={onTicketChange} onRetry={retry} />
        <AssistantPanel ticketId={selectedId} onSelectTicket={setSelectedId} />
      </main>
    </div>
  );
}
