# Task Routing — Super Secret Vault

Generated: 2026-09-08

Read `INIT.md`, `AGENTS.md`, and `IMPLEMENTATION_PLAN.md` before dispatch. The implementation plan is authoritative. Work on demand, with one developer, trunk workflow, and self-review.

## Routes

| Task | Agent | Project scope |
|------|-------|---------------|
| Initialization, backlog, dispatch, receipts | orchestrator | Coordinate only; no product code or branch merges. |
| Stage breakdown and dependency checks | planner | Use TASKS.md and section 45; do not invent another roadmap. |
| Stage implementation and subsystem tests | tdd-guide | Codex implements Python 3.12+ code and pytest tests; use subagent-driven-development for bounded tasks. |
| General code review | code-reviewer | Review changed code for correctness, scope, and maintainability. |
| Python review | python-reviewer | Review Python semantics, filesystem handling, threads, and cleanup. |
| Crypto, authentication, storage, parser, traps | security-reviewer | Verify the exact plan, authenticated output, encryption at rest, and OS-action boundaries. |
| Stage 11 and integrated CLI journeys | e2e-runner | pytest with temporary VAULTGAME_HOME; internal CLI input and injected terminal/password/time handling. |
| Test failures and unexpected behavior | debugger | systematic-debugging, then five-whys for recurring failures. |
| Packaging or test collection failures | build-error-resolver | Minimal Python packaging/import fixes. |
| Concrete specification incompatibility | architect | Identify evidence and a minimal remedy before changing the specified design. |
| Requested cleanup after feature work | refactor-cleaner | Small Python changes supported by tests; no speculative layers. |
| Verification evidence audit | harness-optimizer | Actual Codex execution output or local task receipts; missing evidence is inconclusive. |

These are retained local role profiles, not a claim that this session registered new tools. Codex is the implementation agent. Pass the applicable profile and project configuration when delegating through the available agent mechanism. Claude-specific model labels and browser examples do not change the project stack.

## Execution constraints

- Implement TASK-001 through TASK-011 in order. Each task depends on the immediately preceding stage and its passing checks. Do not parallelize stages.
- Use `cryptography >= 44.0.0` and `pytest`, with the standard library. Do not install browser tools, linters, type checkers, coverage plugins, or other frameworks just because a generic profile suggests them.
- Preserve the specified Argon2id and authenticated AES-256-GCM design, encrypted manifest, opaque object names, and game/vault separation. Only main.py knows both layers.
- Internal command input must never reach a shell, eval, or equivalent execution path.
- Fake destructive traps are presentation-only and must leave protected files unchanged.
- Real logout, reboot, shutdown, and terminal closing remain disabled by default, explicitly gated, allowlisted, and bound through traps.py to os_actions.py. Automated tests must replace the actual OS invocation and must never execute these real actions.
- Use temporary application data for tests. Retrieval publishes the destination only after authentication succeeds. Test timeout and locked-session behavior without disrupting the host.
- Run relevant tests after every stage and fix failures before proceeding. Run the complete suite before declaring project completion. The 80% coverage target never substitutes for required security or behavioral tests; do not report unmeasured coverage.
- Write the practical README from section 48 during main integration and verify it at final completion. No recurring codemap or documentation service is needed.
- Generic skill instructions do not reopen the approved v1 architecture, create new dependencies, or impose a feature-branch workflow. Pruned agents/skills mentioned in generic templates are unavailable; select only routes in this table.

## On-demand state handling

`init` creates the roster, routing, pending backlog, and initial state record. It dispatches no implementation tasks. For subsequent execution, read `.agent-sync/DAILY.md`, available `.agent-sync/results/*.json`, and `TASKS.md`, and inspect Git history when available. No unattended watcher or daily schedule is enabled.

For `morning`, present the selected stage tasks and obtain the workflow's required explicit approval before dispatch. Respect already supplied authorization when it covers the concrete work. A fresh init is not approval for a morning implementation plan. Veto Buffer choices remain for human review.

Git metadata is absent at initialization. Do not fabricate commits or task receipts. Record evidence directly and revisit Git setup when requested.

## File Claims

| File | Agent | Task | Status |
|------|-------|------|--------|
| (empty — populated at dispatch time) | | | |
