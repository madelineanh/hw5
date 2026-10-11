"""Accounting: cash, invoices, payments (human-approved only), pricing and discounts."""

from models import SpecialistReport
from team import build_agent

accounting_agent = build_agent("accounting", SpecialistReport)
