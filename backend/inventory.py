"""Inventory: stock on hand, sizes, vendors, and restock ETAs."""

from models import SpecialistReport
from team import build_agent

inventory_agent = build_agent("inventory", SpecialistReport)
