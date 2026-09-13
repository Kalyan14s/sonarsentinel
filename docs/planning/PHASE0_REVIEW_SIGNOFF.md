# Phase 0 — Documentation Review & Sign-off

| | |
|---|---|
| **Version** | v1.0 · 2026-09-13 |
| **Owner** | PM / Integration & Edge Lead (R6) |
| **Status** | ✅ **Phase 0 closed 2026-09-13**: approved by the team lead (R6). Roles R1–R5 confirm in Sprint 0 ([TODO Phase 1](../../TODO.md#phase-1--sprint-0--project-setup)) |
| **Baseline under review** | Documentation baseline `0.1.0` ([CHANGELOG](../../CHANGELOG.md)); verification passed ([report](../reports/DOCUMENTATION_VERIFICATION_REPORT.md)) |

**Related:** [TODO Phase 0](../../TODO.md#phase-0--documentation--design) · [Documentation index](../README.md) · [PRD](../PRD.md) · [Architecture](../architecture/README.md)

---

## 1. Purpose

Before Sprint 0 starts, every role confirms that the PRD and architecture are **correct, feasible and understood**. Sign-off freezes the documentation baseline. Later changes go through the change-control process ([Project Plan §12](PROJECT_PLAN.md#12-change-control)).

## 2. Decisions already taken in Phase 0

| Decision | Outcome | Record |
|---|---|---|
| Project licence | **AGPL-3.0** (option A) | [ADR-013](../architecture/08-architecture-decisions.md#adr-013--project-licence-agpl-30), [LICENSE](../../LICENSE) |
| Team name / ID / member names | **Deferred**: placeholders kept; to be filled in Sprint 0 | [TODO Phase 1](../../TODO.md#phase-1--sprint-0--project-setup) |
| Sign-off method | Team reviews via pull request; each role signs below | This document |
| Phase 0 closure | Closed 2026-09-13 on **team lead (R6) approval**, so Sprint 0 isn't delayed. R1–R5 confirm during Sprint 0; any *Changes required* from them goes through change control ([Plan §12](PROJECT_PLAN.md#12-change-control)) | §7 below |

Reviewers may challenge these decisions in their review comments.

## 3. How to review (≈ 60–90 minutes per person)

1. The PM opens a pull request titled **`docs: Phase 0 review and sign-off`** containing the documentation baseline.
2. Each reviewer reads the documents for their role (§4) and answers the checklist questions (§5).
3. Leave **inline PR comments** for specific problems. Record anything that blocks approval in the issue log (§6).
4. When satisfied, fill in your row in §7 with one of: **Approve** · **Approve with comments** (non-blocking) · **Changes required** (blocking).
5. The PM resolves blocking issues, re-runs `scripts/docs/verify_docs.ps1`, and asks affected reviewers to re-check.
6. Phase 0 is **complete** when all six roles are *Approve* or *Approve with comments* and no blocking issues remain open.
   **Amended 2026-09-13:** Phase 0 was closed on the team lead's approval. R1–R5 still review and sign in Sprint 0, and their findings are handled as change requests.

**Timebox:** complete within the first two days of Sprint 0, so Sprint 1 isn't delayed.

## 4. What each role reviews

| Role | Must review | Skim |
|---|---|---|
| **R1 · ML Lead** | PRD §8, §11; 03-ml-models; Datasets; Annotation Guidelines; Data Management Plan; Literature Review | 02-data-pipeline; Test Plan §6.1 |
| **R2 · Sonar & Signal** | 02-data-pipeline; Annotation Guidelines; Datasets §5; Test Cases (ING, PRE) | 04-geotagging; 03-ml-models §4 |
| **R3 · Geospatial** | 04-geotagging-engine; 06-data-models; Test Cases (GEO); Datasets D6–D9 | 02-data-pipeline S2, S10 |
| **R4 · Backend** | 01-system-architecture; 05-api-specification; 06-data-models; 02-data-pipeline §4–6 | 07-deployment; Test Cases (API, WS) |
| **R5 · Frontend** | Wireframes README + 01–08; 05-api-specification §3; User Manual | PRD FR-UI; Test Cases (UI) |
| **R6 · PM / Edge** | PRD (all); Project Plan; Product Backlog; TODO; 07-deployment; Licences & Compliance; Test Plan | Everything else |

## 5. Review checklist

### 5.1 Everyone
- [ ] The problem, goals and non-goals (PRD §1–2) match my understanding of SIH 26057
- [ ] P0 scope (PRD §5.1) is achievable in the 6-sprint plan
- [ ] My stories in the [Product Backlog](PRODUCT_BACKLOG.md) have clear acceptance criteria and realistic estimates
- [ ] I understand my responsibilities in the [RACI](PROJECT_PLAN.md#6-team-roles-and-responsibilities)
- [ ] I found no contradictions between the documents I read (otherwise listed in §6)

### 5.2 PRD
- [ ] Requirements are testable and correctly prioritised (P0/P1/P2)
- [ ] Success metrics (§11) are ambitious but measurable with our data
- [ ] Acceptance criteria AC-01…AC-10 cover the demo we want to give
- [ ] Risks (§14) are complete; nothing major is missing

### 5.3 Architecture
- [ ] Stage boundaries and data contracts (02 §2) are implementable
- [ ] Model choices and fallbacks (03, ADR-002…006) are sensible for our compute
- [ ] Geotagging maths (04) and uncertainty budget are correct
- [ ] API contract (05) and report schema (06) are complete enough to freeze in Sprint 1 (Gate G1)
- [ ] Deployment (07) fits our available hardware
- [ ] The AGPL-3.0 decision (ADR-013) is acceptable to the team and mentor

### 5.4 Design & quality
- [ ] Wireframes cover the full flow: upload → live map → detail → download
- [ ] The test plan's data (TD-01…TD-14) can be produced or obtained
- [ ] Data ethics rules (DMP §7) are acceptable and understood

## 6. Issue log

| # | Raised by (role) | Document / section | Issue | Blocking? | Resolution | Status |
|---|---|---|---|---|---|---|
| 1 | | | | Yes / No | | Open |
| 2 | | | | | | |
| 3 | | | | | | |

## 7. Sign-off

| Role | Name | Date | Decision | Comments / PR link |
|---|---|---|---|---|
| R1 · ML Lead | | | ☐ Approve ☐ Approve with comments ☐ Changes required | |
| R2 · Sonar & Signal Engineer | | | ☐ Approve ☐ Approve with comments ☐ Changes required | |
| R3 · Geospatial Engineer | | | ☐ Approve ☐ Approve with comments ☐ Changes required | |
| R4 · Backend Engineer | | | ☐ Approve ☐ Approve with comments ☐ Changes required | |
| R5 · Frontend Engineer | | | ☐ Approve ☐ Approve with comments ☐ Changes required | |
| R6 · PM / Integration & Edge (team lead) | *(role recorded; name to be added)* | 2026-09-13 | ☑ Approve | Approved the documentation baseline to close Phase 0; R1–R5 to confirm in Sprint 0 |
| Mentor (optional) | | | ☐ Approve ☐ Approve with comments ☐ Changes required | |

> Record names here **only** (no phone numbers or email addresses). Contact details stay in the team's private contact sheet.

## 8. After sign-off

- [x] Tick "Team review and sign-off" in [TODO Phase 0](../../TODO.md#phase-0--documentation--design)
- [x] Update this document's status to ✅ **Signed off** with the date
- [ ] Tag the repository `docs-baseline-1.0` *(pending: no git repository exists yet; apply after the repository is created in Sprint 0)*
- [x] Add a CHANGELOG entry: "Phase 0 documentation baseline signed off" (release 0.2.0)
