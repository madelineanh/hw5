"""Facilities: the shop space, the lease, rent due dates, and the landlord."""

from models import SpecialistReport
from team import build_agent

facilities_agent = build_agent("facilities", SpecialistReport)
