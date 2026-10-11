import { useState } from 'react'
import type { Approval } from '../api'
import { AGENT_LABEL, money } from '../api'

interface Props {
  approvals: Approval[]
  approver: string
  onApprove: (a: Approval) => Promise<void>
  onReject: (a: Approval) => Promise<void>
}

const KIND_LABEL = { invoice: 'Vendor invoice', rent: 'Rent', purchase: 'Restock purchase' }

export function ApprovalQueue({ approvals, approver, onApprove, onReject }: Props) {
  const [busy, setBusy] = useState<number | null>(null)
  const act = async (a: Approval, fn: (a: Approval) => Promise<void>) => {
    setBusy(a.id)
    try { await fn(a) } finally { setBusy(null) }
  }
  return (
    <section className={`card approvals ${approvals.length ? 'has-items' : ''}`} aria-label="Approvals">
      <div className="rail-head">
        <h2>Needs your approval</h2>
        {approvals.length > 0 && <span className="count-badge">{approvals.length}</span>}
      </div>
      {approvals.length === 0 && <p className="muted small">Nothing waiting. Agents prepare payments here; only you can approve them.</p>}
      {!approver && approvals.length > 0 && (
        <p className="warn small">Enter your name in “Approving as” (top right) to approve.</p>
      )}
      {approvals.map((a) => (
        <article key={a.id} className="approval">
          <div className="approval-top">
            <span className="eyebrow">{KIND_LABEL[a.kind]} · #{a.id}</span>
            {a.ticket_id && <span className="muted small">Ticket {a.ticket_id}</span>}
          </div>
          <div className="approval-amount">{money(a.amount)}</div>
          <div className="approval-payee">
            to {a.payee}
            {a.kind === 'purchase' && ` · ${a.qty} × ${a.sku} ${a.size}`}
          </div>
          <p className="approval-reason">{a.reason}</p>
          <div className="muted small">Prepared by {AGENT_LABEL[a.requested_by] ?? a.requested_by}</div>
          <div className="approval-actions">
            <button className="btn btn-primary" disabled={!approver || busy === a.id} onClick={() => act(a, onApprove)}>
              {busy === a.id ? 'Working…' : 'Approve'}
            </button>
            <button className="btn btn-ghost" disabled={!approver || busy === a.id} onClick={() => act(a, onReject)}>
              Decline
            </button>
          </div>
        </article>
      ))}
    </section>
  )
}
