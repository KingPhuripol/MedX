---
name: worktree-isolation-blocks-sibling-worktrees
description: Harness blocks Write/git/cp/pytest targeting a sibling git worktree even when the orchestrator's brief names it; plan for own-worktree work and handoff
metadata:
  type: feedback
---

When launched with worktree isolation, the harness guard refuses Write/Edit and git commands that target any other worktree (e.g. a user-created `Full-Agent-opd` checked out on the feature branch), and the auto-mode classifier then also denied `cp`, `git switch -c`, and even `pytest` runs as "Modify Shared Resources" once the agent had touched the sibling tree.

**Why:** 2026-09-23 OPD Phase 1 task: brief said "work ONLY in Full-Agent-opd, commit on feat/opd-p1-journey"; early Bash edits there succeeded, then everything (including tests in own worktree) was denied, leaving work unverified and uncommitted.

**How to apply:** If a brief names a different worktree/branch than the isolated one, flag the conflict at the very start, do not touch the sibling tree via Bash, and do all edits in the isolated worktree; hand back a diff for the orchestrator to apply/fast-forward. Run tests early before any cross-tree action.
