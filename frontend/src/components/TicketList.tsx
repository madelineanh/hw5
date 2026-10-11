import type { Ticket } from '../api'
import { typeLabel } from '../api'

interface Props {
  tickets: Ticket[]
  selectedId: number | null
  runningIds: Set<number>
  onSelect: (id: number) => void
}

export function TicketList({ tickets, selectedId, runningIds, onSelect }: Props) {
  const open = tickets.filter((t) => !t.is_resolved).length
  return (
    <aside className="ticket-list" aria-label="Tickets">
      <div className="rail-head">
        <h2>Tickets</h2>
        <span className="muted">{open} open · {tickets.length - open} resolved</span>
      </div>
      {tickets.map((t) => {
        const running = runningIds.has(t.id) || t.running
        const state = running ? 'running' : t.is_resolved ? 'resolved' : 'open'
        return (
          <button
            key={t.id}
            className={`ticket-card ${state} ${t.id === selectedId ? 'selected' : ''}`}
            onClick={() => onSelect(t.id)}
            aria-pressed={t.id === selectedId}
          >
            <div className="ticket-card-top">
              <span className="ticket-num">#{t.id}</span>
              <span className={`pill pill-${state}`}>
                {state === 'running' ? <><span className="dot" /> Working</> : state === 'resolved' ? '✓ Resolved' : 'Open'}
              </span>
            </div>
            <div className="ticket-subject">{t.subject}</div>
            <div className="ticket-meta">{typeLabel(t.type)} · {t.requester}</div>
            {t.pending_approvals > 0 && (
              <div className="chip chip-approval">{t.pending_approvals} awaiting your approval</div>
            )}
          </button>
        )
      })}
    </aside>
  )
}
