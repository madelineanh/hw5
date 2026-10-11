// Thin client for the FastAPI backend (Problem 7).
export const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export type AgentName = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  sku: string | null
  size: string | null
  qty: number | null
  lease_id: number | null
  invoice_id: number | null
  status: string
  notes: string | null
  created_at: string
  is_resolved: boolean
  state: 'open' | 'resolved'
  running: boolean
  pending_approvals: number
}

export interface Run {
  run_id: string
  ticket_id: number
  status: 'running' | 'completed' | 'error'
  started_at: string
  finished_at?: string
  error?: string
  result?: BossDecision
}

export interface ToolCall { tool: string; tool_call_id: string; args: Record<string, unknown> }

export interface ActivityEvent {
  timestamp: string
  run_id: string
  seq: number
  ticket_id: number | null
  agent: AgentName | 'human'
  chain: string
  depth: number
  event: string
  said: string | null
  tools: string[]
  to?: AgentName
  task?: string
  tool?: string
  tool_calls?: ToolCall[]
  result?: unknown
  reason?: string
  output?: Record<string, unknown>
  stop_reason?: string
  new_status?: string
  error?: string
}

export interface ApprovalRequest {
  action: string
  approval_id: number | null
  ref_id: number | null
  amount: number | null
  reason: string
  cash_after: number | null
}

export interface BossDecision {
  ticket_id: number
  ticket_type: string
  decision: string
  agents_consulted: AgentName[]
  approvals_needed: ApprovalRequest[]
  customer_message: { to: string; subject: string; body: string; commitments: string[] } | null
  new_status: string
  follow_ups: string[]
}

export interface AgentSummary {
  agent: AgentName
  summary: string | null
  tools: string[]
  delegated_to: AgentName[]
}

export interface TicketSummary {
  ticket_id: number
  run_id: string | null
  started_at?: string
  status?: string
  decision: BossDecision | null
  agents: AgentSummary[]
  usage?: { requests: number; tool_calls: number; total_tokens: number } | null
}

export interface Approval {
  id: number
  kind: 'invoice' | 'rent' | 'purchase'
  ref_id: number | null
  vendor_id: number | null
  sku: string | null
  size: string | null
  qty: number | null
  amount: number
  payee: string | null
  reason: string
  ticket_id: number | null
  requested_by: string
  status: 'pending' | 'approved' | 'rejected'
  created_at: string
  decided_by: string | null
}

export interface Cash {
  name: string
  balance: number
  date: string
  pending_total: number
  balance_after_pending: number
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `HTTP ${res.status}`)
  return body as T
}

export const api = {
  tickets: () => request<{ tickets: Ticket[] }>('/tickets').then((d) => d.tickets),
  runTicket: (id: number) => request<Run>(`/tickets/${id}/run`, { method: 'POST' }),
  run: (runId: string) => request<Run>(`/runs/${runId}`),
  summary: (id: number) => request<TicketSummary>(`/tickets/${id}/summary`),
  activity: (runId: string) =>
    request<{ events: ActivityEvent[] }>(`/activity?run_id=${encodeURIComponent(runId)}&limit=1000`).then((d) =>
      [...d.events].reverse(),
    ),
  approvals: () => request<{ approvals: Approval[] }>('/approvals?status=pending').then((d) => d.approvals),
  approve: (id: number, approvedBy: string) =>
    request<{ balance_before: number; balance_after: number }>(`/approvals/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approved_by: approvedBy }),
    }),
  reject: (id: number, rejectedBy: string, reason: string) =>
    request(`/approvals/${id}/reject`, { method: 'POST', body: JSON.stringify({ rejected_by: rejectedBy, reason }) }),
  cash: () => request<Cash>('/cash'),
  reset: () => request<{ ok: boolean }>('/reset', { method: 'POST' }),
}

export const AGENT_LABEL: Record<string, string> = {
  boss: 'Boss',
  inventory: 'Inventory',
  accounting: 'Accounting',
  facilities: 'Facilities',
  customer_service: 'Customer Service',
  human: 'You',
}

export const money = (n: number | null | undefined) =>
  n == null ? '—' : n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

export const typeLabel = (t: string) =>
  ({ customer_order: 'Customer order', rent_notice: 'Rent notice', price_override: 'Price request' })[t] ?? t
