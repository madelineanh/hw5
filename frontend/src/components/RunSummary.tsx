import type { TicketSummary } from '../api'
import { AGENT_LABEL, money } from '../api'

export function RunSummary({ summary }: { summary: TicketSummary }) {
  const d = summary.decision
  if (!d) return null
  return (
    <section className="summary">
      <div className="decision card">
        <span className="eyebrow">The Boss's decision</span>
        <p className="decision-text">{d.decision}</p>
        {d.approvals_needed.length > 0 && (
          <ul className="decision-approvals">
            {d.approvals_needed.map((a, i) => (
              <li key={i}>
                {a.approval_id ? `Approval #${a.approval_id}: ` : 'Needs approval: '}{a.action.replaceAll('_', ' ')} {money(a.amount)}
                {a.cash_after != null && <span className="muted"> · leaves {money(a.cash_after)}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="agent-grid">
        {summary.agents.filter((a) => a.summary || a.tools.length).map((a) => (
          <article key={a.agent} className={`agent-card agent-${a.agent}`}>
            <header>
              <span className={`avatar agent-${a.agent}`} aria-hidden>{AGENT_LABEL[a.agent][0]}</span>
              <h3>{AGENT_LABEL[a.agent]}</h3>
            </header>
            <p>{a.summary ?? 'Working…'}</p>
            {a.tools.length > 0 && (
              <div className="tool-chips">{a.tools.map((t) => <span key={t} className="tool-chip">{t}</span>)}</div>
            )}
            {a.delegated_to.length > 0 && (
              <div className="muted small">Handed off to {a.delegated_to.map((x) => AGENT_LABEL[x]).join(', ')}</div>
            )}
          </article>
        ))}
      </div>

      {d.customer_message && (
        <div className="card draft">
          <span className="eyebrow">Draft reply for a person to review and send</span>
          <div className="draft-meta">To {d.customer_message.to} · {d.customer_message.subject}</div>
          <p className="draft-body">{d.customer_message.body}</p>
        </div>
      )}
      {summary.usage && (
        <p className="muted small usage">
          {summary.usage.requests} model calls · {summary.usage.tool_calls} tool calls · {summary.usage.total_tokens.toLocaleString()} tokens
        </p>
      )}
    </section>
  )
}
