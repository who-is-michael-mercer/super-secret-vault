# Project Init Document

## Project Identity

**Name:** Super Secret Vault

**Type:** cli-tool

**Status:** greenfield

**Project root:** `~/Projects/local-repo/super-secret-vault`

https://github.com/who-is-michael-mercer/super-secret-vault.git



## Primary Programming Languages

List every language used in this project. Agents for unlisted languages will be pruned.

* [ ] TypeScript / JavaScript
* [x] Python
* [ ] Go
* [ ] Rust
* [ ] Kotlin / Java (Android)
* [ ] Swift (iOS / macOS)
* [ ] Dart (Flutter)
* [ ] Other

## Tech Stack

**Frontend:** none

**Backend:** none

**Database:** none

**Runtime:** Python 3.12+

**CI/CD:** none

### Core runtime dependency

* `cryptography >= 44.0.0`

### Development dependency

* `pytest`

Do not introduce additional frameworks or dependencies unless they are genuinely required by the implementation blueprint.

## Communication & Collaboration Tools

List tools in active use. Agents for unlisted tools will be pruned.

* [ ] Gmail / email
* [ ] Slack
* [ ] GitHub Issues / PRs
* [ ] Linear
* [ ] Notion
* [x] None — this is a pure engineering project

## Scope Boundaries

**Will this project have E2E tests?** yes

**Will this project use a PostgreSQL database?** no

**Will this project handle authentication or user data?** yes

Authentication here means local password-based unlocking of an encrypted personal vault. There are no user accounts, remote identities, or authentication servers.

The project stores encrypted personal files locally.

**Is there a multi-channel communication workflow?** no

**Are there autonomous agent loops running unattended?** no

**Will there be regular documentation / codemaps?** no

A practical README and implementation documentation are sufficient. Do not create an ongoing documentation-management system.

**Does this project make LLM API calls?** no

**Does this project use Terraform / Docker / Kubernetes?** no

**Does this project have a production environment?** no

**Are there performance targets or SLAs?** no

## Compliance Scope

Which regulations apply? The `compliance-reviewer` agent only activates for declared scopes.

* [ ] GDPR / RGPD
* [ ] COPPA
* [ ] PCI-DSS
* [ ] SOC2
* [ ] HIPAA
* [x] None

This is a local personal project and is not currently intended to operate as a service or collect data from other users.

## Team & Workflow

**Number of developers:** 1

**Branching model:** trunk

**Review process:** self-review

## Quality Standards

**Minimum test coverage:** 80%

**Linting enforced:** no

**Type checking enforced:** no

Correctness of the cryptographic, storage, locking, trap-isolation, and end-to-end behavior is more important than pursuing coverage percentage for its own sake.

All tests specified by the implementation blueprint must pass regardless of the overall coverage percentage.

## Special Constraints

The following constraints apply across all agents working on this project:

* `IMPLEMENTATION_PLAN.md` is the authoritative implementation specification. Do not redesign the architecture unless a genuine technical incompatibility is discovered.

* Keep the project small, local, single-process, and terminal-first. Do not introduce servers, databases, networking, cloud services, account systems, plugin frameworks, microservices, or unnecessary architectural layers.

* Do not invent custom cryptography. Use established primitives and the approved `cryptography` library.

* The game layer and encrypted vault layer must remain separated as defined in `IMPLEMENTATION_PLAN.md`.

* User-entered terminal commands are internal application commands and must never be passed directly to a system shell, `eval`, `os.system`, shell-enabled subprocess execution, or equivalent mechanisms.

* Fake destructive traps must remain presentation-only and must never modify encrypted vault contents.

* Real OS-level actions such as logout, reboot, shutdown, or terminal closing must remain isolated from normal command handling, explicitly gated, disabled by default, and never executed by automated tests.

* Automated tests must never reboot, shut down, log out of, or terminate the developer's actual machine or terminal.

* Stored plaintext filenames must not appear as vault object filenames on disk.

* Protected file contents must remain encrypted at rest.

* Decrypted retrieval output must not become the requested destination file until authentication succeeds.

* Do not claim guaranteed secure deletion or guaranteed erasure of cryptographic material from RAM.

* Do not persist normal game progression. A fresh launch begins the infiltration sequence again.

* Do not add features outside the version-1 scope simply because they may be useful later.

* Implement real functionality rather than TODOs, placeholder methods, mock implementations, speculative abstractions, or pseudocode.

* Work through the implementation stages in `IMPLEMENTATION_PLAN.md` in order and run the relevant tests after each stage.

* The project is complete only when the Definition of Completion in `IMPLEMENTATION_PLAN.md` is satisfied and the complete test suite passes.

## CLI Environment

Which AI coding CLI(s) will be active in this project?

* [ ] Claude Code
* [x] Codex CLI
* [ ] Cursor
* [ ] OpenCode
* [ ] Multiple CLIs simultaneously

Codex is the primary implementation agent for this project.

## Daily Workflow Mode

How will the orchestrator be invoked?

* [ ] Daily standup mode
* [x] On-demand dispatch
* [ ] CI/CD triggered

The orchestrator should be used for implementation stages, debugging, testing, security review, and targeted project tasks rather than running a continuous autonomous workflow.

## Existing TASKS.md

Does this project already have a `TASKS.md` backlog the orchestrator should consume?

**no — orchestrator will create one**

The initial backlog should be derived from the ordered implementation stages in `IMPLEMENTATION_PLAN.md` rather than inventing a separate roadmap.




