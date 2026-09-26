"""Pharma Agent (slice s5): medication reconciliation for pharmacist review.

Rules are the primary checker; model phrasing is supplementary. The agent reads snapshots only
and never creates, edits, or removes orders. All fixtures are synthetic.
"""

from __future__ import annotations

from .mock_rules import register as _register_mock_tasks

_register_mock_tasks()

__all__ = ["reconcile"]


def __getattr__(name: str):
    if name == "reconcile":
        from .pipeline import reconcile

        return reconcile
    raise AttributeError(name)
