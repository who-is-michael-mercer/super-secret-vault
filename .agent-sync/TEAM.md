# Active Team — Super Secret Vault

Generated: 2026-09-08

Configuration: `INIT.md`. Specification: `IMPLEMENTATION_PLAN.md`.

## Active Agents

- architect: Default core agent; check compliance with the fixed plan and investigate concrete incompatibilities only.
- build-error-resolver: Default core agent; resolve Python packaging, installation, and test collection failures with minimal changes.
- code-reviewer: Default core agent; review correctness and scope after code changes.
- debugger: Default core agent; investigate failing tests and unexpected CLI behavior.
- e2e-runner: E2E tests are explicitly required; use pytest for CLI journeys, with isolated application data and mocked OS invocation.
- harness-optimizer: Always retained by the init workflow; verify actual test and review evidence on demand.
- orchestrator: Manage on-demand routing and ordered stage dependencies; never write product code.
- planner: Default core agent; derive bounded tasks from the authoritative implementation stages.
- python-reviewer: Python is the sole declared implementation language.
- refactor-cleaner: Default core agent; targeted Python cleanup only when requested, without new abstractions.
- security-reviewer: Local password authentication and encrypted personal files require crypto, storage, parser, locking, and trap-isolation review.
- tdd-guide: Default core agent; implement and test the ordered stages using pytest.

## Pruned Agents

- ai-reviewer: No LLM API calls or AI-native application features.
- chief-of-staff: No communication or collaboration tools are in use.
- compliance-reviewer: Compliance scope is explicitly None.
- database-reviewer: No database or PostgreSQL.
- doc-updater: No recurring documentation or codemaps; the implementation owner writes the practical README.
- flutter-reviewer: Dart and Flutter are not selected.
- go-reviewer: Go is not selected.
- infra-reviewer: No Terraform, Docker, Kubernetes, or CI/CD.
- kotlin-reviewer: Kotlin and Java/Android are not selected.
- loop-operator: No unattended autonomous loops.
- performance-profiler: No performance targets, SLAs, or profiling scope.
- rust-reviewer: Rust is not selected.
- swift-reviewer: Swift and iOS/macOS application development are not selected.
- typescript-reviewer: TypeScript/JavaScript is not selected and there is no frontend; INIT.md explicitly prunes unlisted language agents.

## Active Skills

- brainstorming: Greenfield matches the explicit keep rule; the existing implementation plan already fixes v1 design, so this does not reopen architecture or require another design interview.
- five-whys: Root-cause analysis supports targeted debugging of recurring failures.
- subagent-driven-development: Cryptography, authenticated streaming storage, and watchdog locking require complex implementation work; dispatch bounded tasks within sequential stages.
- systematic-debugging: Development and stage-test failure investigation are in scope.
- test-driven-development: All implementation stages require working functionality and relevant pytest checks.
- using-a-team: Retain the team entry workflow; TEAM.md and ROUTING.md restrict its generic triggers to this project.
- verification-before-completion: Require fresh evidence before stage or project completion claims.

## Pruned Skills

- api-contract-first: No API endpoints or inter-service interfaces; internal Python functions do not introduce a service contract.
- architecture-audit: Greenfield project with a fixed architecture; no inherited system, scaling milestone, or periodic architecture audit.
- data-migration: No database.
- dispatching-parallel-agents: The initial backlog is strictly sequential; no independent parallel problem batch is declared.
- executing-plans: The init keep rule requires status active-development; INIT.md currently declares greenfield. Ordered implementation remains routed through subagent-driven-development and tdd-guide.
- finishing-a-development-branch: Trunk workflow and self-review; no feature-branch or gitflow completion process.
- incident-response: No production environment.
- performance-audit: No performance targets or profiling work; implement the specified streaming and KDF behavior without an extra performance program.
- skill-duplication-audit: No ongoing skill-library maintenance or expansion is declared.
- smart-init: INIT.md already exists; the requested standard init path explicitly skips configuration extraction and interviews.
- using-git-worktrees: Single-developer trunk workflow with sequential stages; no feature-branch isolation workflow is declared.
- writing-plans: The init keep rule requires status active-development; this project is greenfield and already has its authoritative implementation plan.
- writing-skills: No new skill creation or skill development is in scope.

## Scope decisions

Evaluated all 26 local agent profiles and all 20 local skills. Retained 12 agents and 7 skills; pruned 14 agents and 13 skill directories. Only workspace files in `.claude/agents/` and `skills/` are subject to pruning; installed global skills are outside this inventory.

Explicit INIT.md language selection takes precedence over the orchestrator table's generic “all others” default for typescript-reviewer. The active-development-only skill rules are evaluated against the declared greenfield status. Skills without an explicit table rule were evaluated by their stated purpose and the declared scope. Re-evaluate the roster if the project configuration changes.

Generic retained profiles contain web, tool-installation, architecture, and branch examples. Those examples do not authorize extra dependencies, browser testing, redesign, worktrees, CI, or services. Apply the project-specific routing and the implementation plan.

## Initialization state

No existing TEAM.md, ROUTING.md, DAILY.md, TASKS.md, application package, or application test suite was found. Git status/history are unavailable: this directory is not a Git repository. The configured GitHub URL is informational; init does not create a repository or contact the remote.

The initial backlog is exactly the 11 stages in section 45. All stages remain pending. This initialization does not establish application completion.

## Deletion log

- Deleted `.claude/agents/ai-reviewer.md`: No LLM API calls or AI-native application features.
- Deleted `.claude/agents/chief-of-staff.md`: No communication or collaboration tools are in use.
- Deleted `.claude/agents/compliance-reviewer.md`: Compliance scope is explicitly None.
- Deleted `.claude/agents/database-reviewer.md`: No database or PostgreSQL.
- Deleted `.claude/agents/doc-updater.md`: No recurring documentation or codemaps; the implementation owner writes the practical README.
- Deleted `.claude/agents/flutter-reviewer.md`: Dart and Flutter are not selected.
- Deleted `.claude/agents/go-reviewer.md`: Go is not selected.
- Deleted `.claude/agents/infra-reviewer.md`: No Terraform, Docker, Kubernetes, or CI/CD.
- Deleted `.claude/agents/kotlin-reviewer.md`: Kotlin and Java/Android are not selected.
- Deleted `.claude/agents/loop-operator.md`: No unattended autonomous loops.
- Deleted `.claude/agents/performance-profiler.md`: No performance targets, SLAs, or profiling scope.
- Deleted `.claude/agents/rust-reviewer.md`: Rust is not selected.
- Deleted `.claude/agents/swift-reviewer.md`: Swift and iOS/macOS application development are not selected.
- Deleted `.claude/agents/typescript-reviewer.md`: TypeScript/JavaScript is not selected and there is no frontend; INIT.md explicitly prunes unlisted language agents.
- Deleted `skills/api-contract-first/` (containing only `SKILL.md`): No API endpoints or inter-service interfaces; internal Python functions do not introduce a service contract.
- Deleted `skills/architecture-audit/` (containing only `SKILL.md`): Greenfield project with a fixed architecture; no inherited system, scaling milestone, or periodic architecture audit.
- Deleted `skills/data-migration/` (containing only `SKILL.md`): No database.
- Deleted `skills/dispatching-parallel-agents/` (containing only `SKILL.md`): The initial backlog is strictly sequential; no independent parallel problem batch is declared.
- Deleted `skills/executing-plans/` (containing only `SKILL.md`): The init keep rule requires status active-development; INIT.md currently declares greenfield. Ordered implementation remains routed through subagent-driven-development and tdd-guide.
- Deleted `skills/finishing-a-development-branch/` (containing only `SKILL.md`): Trunk workflow and self-review; no feature-branch or gitflow completion process.
- Deleted `skills/incident-response/` (containing only `SKILL.md`): No production environment.
- Deleted `skills/performance-audit/` (containing only `SKILL.md`): No performance targets or profiling work; implement the specified streaming and KDF behavior without an extra performance program.
- Deleted `skills/skill-duplication-audit/` (containing only `SKILL.md`): No ongoing skill-library maintenance or expansion is declared.
- Deleted `skills/smart-init/` (containing only `SKILL.md`): INIT.md already exists; the requested standard init path explicitly skips configuration extraction and interviews.
- Deleted `skills/using-git-worktrees/` (containing only `SKILL.md`): Single-developer trunk workflow with sequential stages; no feature-branch isolation workflow is declared.
- Deleted `skills/writing-plans/` (containing only `SKILL.md`): The init keep rule requires status active-development; this project is greenfield and already has its authoritative implementation plan.
- Deleted `skills/writing-skills/` (containing only `SKILL.md`): No new skill creation or skill development is in scope.
