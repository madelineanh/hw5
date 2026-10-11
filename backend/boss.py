"""Boss: owns every ticket, routes work to the specialists, makes the final call."""

from models import BossDecision
from team import build_agent

boss_agent = build_agent("boss", BossDecision)
