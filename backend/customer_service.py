"""Customer Service: drafts every outbound message (never sends)."""

from models import CustomerServiceReport
from team import build_agent

customer_service_agent = build_agent("customer_service", CustomerServiceReport)
