"""Data types shared by the Campus Customs agent team."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
SpecialistName = Literal["inventory", "accounting", "facilities", "customer_service"]
TicketStatus = Literal["open", "in_progress", "waiting_on_approval", "waiting_on_vendor", "resolved"]


# ------------------------------------------------------------------ run state


@dataclass
class AuditLog:
    """Collects every agent-loop step for one top-level run; flushed to output/audit_trail.json."""

    run_id: str
    db_path: str
    events: list[dict] = field(default_factory=list)


@dataclass
class TeamDeps:
    """Passed to every agent run. A fresh copy is made for each delegation hop."""

    run_id: str
    agent: AgentName
    chain: list[AgentName]  # who called whom to get here, e.g. ["boss", "inventory"]
    audit: AuditLog
    ticket_id: int | None = None
    max_depth: int = 3
    delegations_used: int = 0  # shared counter lives on the root deps (see counter_owner)
    max_delegations: int = 8
    counter_owner: TeamDeps | None = None

    @property
    def depth(self) -> int:
        return len(self.chain) - 1

    @property
    def root(self) -> TeamDeps:
        return self.counter_owner or self


# --------------------------------------------------------------- agent outputs


class Fact(BaseModel):
    """One number or fact the agent relied on, with the MCP tool it came from."""

    source_tool: str = Field(description="MCP tool that returned this fact, e.g. check_inventory_stock")
    label: str = Field(description="What the fact is, e.g. 'CC-TEE-WHITE S qty'")
    value: str = Field(description="The exact value returned by the tool")


class ApprovalRequest(BaseModel):
    """Something only a human may sign off on."""

    action: Literal["pay_invoice", "pay_lease_rent", "purchase", "discount_over_limit", "other"]
    approval_id: int | None = Field(default=None, description="pending_approvals id from prepare_payment / prepare_purchase")
    ref_id: int | None = Field(default=None, description="invoice id, lease id, or ticket id")
    amount: float | None = Field(default=None, description="Dollar amount involved, from the database")
    reason: str
    cash_after: float | None = Field(default=None, description="Checking balance if this is approved")


class SpecialistReport(BaseModel):
    """What Inventory, Accounting, or Facilities hands back to whoever delegated to them."""

    agent: SpecialistName
    ticket_id: int | None = None
    summary: str = Field(description="2-4 sentences: what you found and what it means for the ticket")
    facts: list[Fact] = Field(default_factory=list)
    actions_taken: list[str] = Field(default_factory=list, description="Writes you actually made via MCP tools")
    blockers: list[str] = Field(default_factory=list)
    approvals_needed: list[ApprovalRequest] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)


class CustomerMessageDraft(BaseModel):
    """A message for a human to review and send. Agents never send it themselves."""

    to: str
    subject: str
    body: str
    commitments: list[str] = Field(
        default_factory=list, description="Every promise in the body (dates, prices, quantities) so a human can check them"
    )


class CustomerServiceReport(SpecialistReport):
    agent: Literal["customer_service"] = "customer_service"  # type: ignore[assignment]
    draft: CustomerMessageDraft | None = None


class BossDecision(BaseModel):
    """The Boss's final word on one ticket."""

    ticket_id: int
    ticket_type: str
    decision: str = Field(description="What the shop is doing about this ticket and why")
    agents_consulted: list[SpecialistName] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    actions_taken: list[str] = Field(default_factory=list)
    approvals_needed: list[ApprovalRequest] = Field(default_factory=list)
    customer_message: CustomerMessageDraft | None = None
    new_status: TicketStatus
    follow_ups: list[str] = Field(default_factory=list)
