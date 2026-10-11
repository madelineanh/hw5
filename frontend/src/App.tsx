import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ActivityEvent, Approval, Cash, Ticket, TicketSummary } from './api'
import { API_BASE, api, money, typeLabel } from './api'
import { ActivityFeed } from './components/ActivityFeed'
import { ApprovalQueue } from './components/ApprovalQueue'
import { CashCard } from './components/CashCard'
import { RunSummary } from './components/RunSummary'
import { TicketList } from './components/TicketList'

type Toast = { kind: 'ok' | 'err'; text: string }

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [cash, setCash] = useState<Cash | null>(null)
  // ?ticket=101 opens a specific ticket (handy for links and screenshots)
  const [selectedId, setSelectedId] = useState<number | null>(() => {
    const t = Number(new URLSearchParams(window.location.search).get('ticket'))
    return Number.isInteger(t) && t > 0 ? t : null
  })
  const [summary, setSummary] = useState<TicketSummary | null>(null)
  const [events, setEvents] = useState<ActivityEvent[]>([])
  const [activeRuns, setActiveRuns] = useState<Record<number, string>>({}) // ticket id -> run id
  const [approver, setApprover] = useState(() => localStorage.getItem('approver') ?? '')
  const [toast, setToast] = useState<Toast | null>(null)
  const [offline, setOffline] = useState(false)

  const notify = (t: Toast) => {
    setToast(t)
    setTimeout(() => setToast(null), 5000)
  }

  // Tickets, approvals, and cash: refreshed on a slow timer and after every action.
  const refreshDesk = useCallback(async () => {
    try {
      const [t, a, c] = await Promise.all([api.tickets(), api.approvals(), api.cash()])
      setTickets(t)
      setApprovals(a)
      setCash(c)
      setOffline(false)
      setSelectedId((id) => id ?? t.find((x) => !x.is_resolved)?.id ?? t[0]?.id ?? null)
    } catch {
      setOffline(true)
    }
  }, [])

  // The selected ticket's latest run: summary + every activity event.
  const refreshTicket = useCallback(async (id: number) => {
    try {
      const s = await api.summary(id)
      setSummary(s)
      setEvents(s.run_id ? await api.activity(s.run_id) : [])
    } catch {
      /* desk refresh reports offline */
    }
  }, [])

  useEffect(() => {
    refreshDesk()
    const t = setInterval(refreshDesk, 4000)
    return () => clearInterval(t)
  }, [refreshDesk])

  const selectedRunning = selectedId != null && (activeRuns[selectedId] != null || summary?.status === 'running')

  useEffect(() => {
    if (selectedId == null) return
    setSummary(null)
    setEvents([])
    refreshTicket(selectedId)
  }, [selectedId, refreshTicket])

  // Poll fast while the selected ticket is running.
  useEffect(() => {
    if (selectedId == null || !selectedRunning) return
    const t = setInterval(() => refreshTicket(selectedId), 1500)
    return () => clearInterval(t)
  }, [selectedId, selectedRunning, refreshTicket])

  // Watch every run this dashboard started; when one finishes, refresh everything.
  useEffect(() => {
    const entries = Object.entries(activeRuns)
    if (!entries.length) return
    const t = setInterval(async () => {
      for (const [ticketId, runId] of entries) {
        try {
          const run = await api.run(runId)
          if (run.status === 'running') continue
          setActiveRuns((r) => {
            const next = { ...r }
            delete next[Number(ticketId)]
            return next
          })
          if (run.status === 'completed') notify({ kind: 'ok', text: `Ticket ${ticketId} resolved by the agent team.` })
          else notify({ kind: 'err', text: `Ticket ${ticketId} stopped: ${run.error}` })
          await refreshDesk()
          if (Number(ticketId) === selectedId) await refreshTicket(Number(ticketId))
        } catch {
          /* keep polling */
        }
      }
    }, 2000)
    return () => clearInterval(t)
  }, [activeRuns, selectedId, refreshDesk, refreshTicket])

  const selected = useMemo(() => tickets.find((t) => t.id === selectedId) ?? null, [tickets, selectedId])
  const anyRunning = Object.keys(activeRuns).length > 0 || tickets.some((t) => t.running)

  const startRun = async () => {
    if (!selected) return
    try {
      const run = await api.runTicket(selected.id)
      setActiveRuns((r) => ({ ...r, [selected.id]: run.run_id }))
      setEvents([])
      setSummary({ ticket_id: selected.id, run_id: run.run_id, status: 'running', decision: null, agents: [] })
      refreshDesk()
    } catch (e) {
      notify({ kind: 'err', text: (e as Error).message })
    }
  }

  const approve = async (a: Approval) => {
    try {
      const r = await api.approve(a.id, approver)
      notify({ kind: 'ok', text: `Approved ${money(a.amount)} to ${a.payee}. Checking ${money(r.balance_before)} → ${money(r.balance_after)}.` })
    } catch (e) {
      notify({ kind: 'err', text: (e as Error).message })
    }
    await refreshDesk()
  }

  const reject = async (a: Approval) => {
    const reason = window.prompt(`Why decline ${money(a.amount)} to ${a.payee}?`)
    if (!reason) return
    try {
      await api.reject(a.id, approver, reason)
      notify({ kind: 'ok', text: `Declined approval #${a.id}. No money moved.` })
    } catch (e) {
      notify({ kind: 'err', text: (e as Error).message })
    }
    await refreshDesk()
  }

  const reset = async () => {
    if (!window.confirm('Reset the shop database to its original values? Ticket statuses, payments, and approvals will be restored. The audit trail is kept.')) return
    try {
      await api.reset()
      notify({ kind: 'ok', text: 'Database reset to its original values.' })
    } catch (e) {
      notify({ kind: 'err', text: (e as Error).message })
    }
    await refreshDesk()
    if (selectedId != null) refreshTicket(selectedId)
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="eyebrow">Campus Customs · Chapel Street</span>
          <h1>The Service Desk</h1>
        </div>
        <div className="topbar-right">
          {cash && <span className="shop-date">Shop date <strong>{cash.date}</strong></span>}
          <label className="approver">
            <span>Approving as</span>
            <input
              value={approver}
              placeholder="Your name"
              onChange={(e) => {
                setApprover(e.target.value)
                localStorage.setItem('approver', e.target.value)
              }}
            />
          </label>
          <button className="btn btn-ghost" onClick={reset} disabled={anyRunning}>Reset data</button>
        </div>
      </header>

      {offline && (
        <div className="banner">
          Can't reach the backend at {API_BASE}. Start it from <code>backend/</code> with <code>uvicorn main:app --reload --port 8000</code>.
        </div>
      )}

      <div className="layout">
        <TicketList
          tickets={tickets}
          selectedId={selectedId}
          runningIds={new Set(Object.keys(activeRuns).map(Number))}
          onSelect={setSelectedId}
        />

        <main className="workspace">
          {selected ? (
            <>
              <section className={`card ticket-hero ${selected.is_resolved ? 'resolved' : ''}`}>
                <div className="hero-top">
                  <div>
                    <span className="eyebrow">Ticket #{selected.id} · {typeLabel(selected.type)}</span>
                    <h2>{selected.subject}</h2>
                    <p className="muted">From {selected.requester}</p>
                  </div>
                  <div className="hero-actions">
                    {selected.is_resolved && !selectedRunning && <span className="resolved-stamp">✓ Resolved</span>}
                    <button className="btn btn-primary btn-lg" onClick={startRun} disabled={selectedRunning || anyRunning}>
                      {selectedRunning ? 'Agents working…' : selected.is_resolved ? 'Run again' : 'Run agent team'}
                    </button>
                  </div>
                </div>
                <dl className="ticket-facts">
                  {selected.sku && <div><dt>Item</dt><dd>{selected.sku} · size {selected.size} × {selected.qty}</dd></div>}
                  {selected.lease_id && <div><dt>Lease</dt><dd>#{selected.lease_id}</dd></div>}
                  {selected.invoice_id && <div><dt>Invoice</dt><dd>#{selected.invoice_id}</dd></div>}
                  <div><dt>Status</dt><dd>{selected.status.replaceAll('_', ' ')}</dd></div>
                </dl>
                {selected.notes && <p className="ticket-notes">{selected.notes.split('\n')[0]}</p>}
              </section>

              {summary?.decision && !selectedRunning && <RunSummary summary={summary} />}

              <section className="card activity">
                <div className="rail-head">
                  <h2>Agent activity</h2>
                  {selectedRunning
                    ? <span className="pill pill-running"><span className="dot" /> Live</span>
                    : summary?.started_at && <span className="muted small">Last run {new Date(summary.started_at).toLocaleString()}</span>}
                </div>
                <ActivityFeed events={events} live={selectedRunning} />
              </section>
            </>
          ) : (
            <p className="muted empty">Select a ticket.</p>
          )}
        </main>

        <aside className="rail">
          <CashCard cash={cash} />
          <ApprovalQueue approvals={approvals} approver={approver.trim()} onApprove={approve} onReject={reject} />
        </aside>
      </div>

      {toast && <div className={`toast toast-${toast.kind}`} role="status">{toast.text}</div>}
    </div>
  )
}
