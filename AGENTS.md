# Project instructions

`IMPLEMENTATION_PLAN.md` is the authoritative V3 specification. The historical
plan in `docs/history/` is reference only; do not continue its stages.

Follow it rather than redesigning the architecture.

Keep the implementation small and direct. Do not introduce additional frameworks, architectural layers, dependencies, databases, services, abstractions, or future-facing extensibility unless the implementation plan explicitly requires them.

Implement real working functionality. Do not substitute TODOs, placeholders, mocks, pseudocode, or incomplete stubs for required functionality.

Work through the implementation stages in the order specified in `IMPLEMENTATION_PLAN.md`.

Run the relevant tests after each stage and fix failures before proceeding.

Real logout, reboot, shutdown, and terminal-closing actions must remain disabled during automated testing and must never be triggered by tests.

Do not weaken or replace the cryptographic design specified in the implementation plan without identifying a concrete implementation incompatibility first.

The project is finished only when the Definition of Completion in `IMPLEMENTATION_PLAN.md` is satisfied and the full test suite passes.
