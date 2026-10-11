import { useEffect, useRef } from 'react'
import type { ActivityEvent } from '../api'
import { AGENT_LABEL } from '../api'

const HIDDEN = new Set(['prompt', 'db_write_attempt', 'delegation_returned'])

function argText(args: Record<string, unknown>) {
  return Object.entries(args)
    .filter(([k]) => k !== 'reason' && k !== 'note')
    .map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
    .join(', ')
}

function preview(v: unknown, n = 160) {
  const s = typeof v === 'string' ? v : JSON.stringify(v)
  return s.length > n ? s.slice(0, n) + '…' : s
}

function Body({ e }: { e: ActivityEvent }) {
  switch (e.event) {
    case 'run_started':
      return <span className="muted">Run started. The Boss picks up the ticket.</span>
    case 'agent_started':
      return <span className="muted">{e.depth === 0 ? 'Reading the ticket' : 'Picks up the task'}</span>
    case 'model_response': {
      const calls = (e.tool_calls ?? []).filter((c) => c.tool !== 'delegate')
      return (
        <>
          {e.said && <p className="said">“{e.said}”</p>}
          {calls.map((c) => (
            <div key={c.tool_call_id} className="tool-use">
              <span className="tool-chip">{c.tool}</span>
              <span className="tool-args">{argText(c.args)}</span>
            </div>
          ))}
        </>
      )
    }
    case 'tool_result':
      if (e.tool === 'delegate') return null
      return (
        <details className="tool-result">
          <summary>↳ {e.tool} returned <span className="muted">{preview(e.result, 90)}</span></summary>
          <pre>{JSON.stringify(e.result, null, 2)}</pre>
        </details>
      )
    case 'delegation_sent':
      return (
        <div className="handoff">
          <span className="handoff-arrow">→ hands off to <strong>{AGENT_LABEL[e.to ?? '']}</strong></span>
          <p>{e.task}</p>
        </div>
      )
    case 'agent_finished':
      return (
        <div className="report">
          <span className="eyebrow">Report</span>
          <p>{e.said}</p>
        </div>
      )
    case 'guardrail_block':
    case 'delegation_refused':
      return <div className="guard">Guardrail: {e.reason}</div>
    case 'delegation_failed':
      return <div className="guard">{e.to ? `${e.to} could not finish: ` : ''}{e.error}</div>
    case 'tool_retry':
      return <div className="guard soft">Retrying {e.tool}</div>
    case 'harness_status_sync':
      return <span className="muted">Ticket marked <strong>{e.new_status}</strong></span>
    case 'run_finished':
      return e.stop_reason === 'completed'
        ? <span className="done">✓ Run complete. Ticket {e.new_status}.</span>
        : <div className="guard">Run stopped: {e.error}</div>
    case 'agent_error':
      return <div className="guard">Error: {e.error}</div>
    default:
      return <span className="muted">{e.event}</span>
  }
}

export function ActivityFeed({ events, live }: { events: ActivityEvent[]; live: boolean }) {
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (live) end.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [events.length, live])

  const shown = events.filter(
    (e) => !HIDDEN.has(e.event) && !(e.event === 'tool_result' && e.tool === 'delegate') &&
      !(e.event === 'model_response' && !e.said && !(e.tool_calls ?? []).some((c) => c.tool !== 'delegate')),
  )
  if (!shown.length) return <p className="muted empty">No activity yet. Run the agent team to watch them work.</p>

  return (
    <ol className="feed">
      {shown.map((e) => (
        <li key={`${e.run_id}-${e.seq}`} className={`feed-item agent-${e.agent} ev-${e.event}`} style={{ marginLeft: `${e.depth * 22}px` }}>
          <span className={`avatar agent-${e.agent}`} aria-hidden>{(AGENT_LABEL[e.agent] ?? '?')[0]}</span>
          <div className="feed-body">
            <div className="feed-head">
              <strong>{AGENT_LABEL[e.agent] ?? e.agent}</strong>
              {e.depth > 0 && <span className="chain">{e.chain.split(' > ').map((a) => AGENT_LABEL[a] ?? a).join(' › ')}</span>}
              <time>{new Date(e.timestamp).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' })}</time>
            </div>
            <Body e={e} />
          </div>
        </li>
      ))}
      {live && <li className="feed-item typing"><span className="dot" /><span className="dot" /><span className="dot" /></li>}
      <div ref={end} />
    </ol>
  )
}
