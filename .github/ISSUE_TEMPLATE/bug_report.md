---
name: Bug report
about: Report something that doesn't work as expected
title: "[BUG] "
labels: ["type:bug"]
---

## Description
<!-- What happened? -->

## Expected behaviour
<!-- What should have happened? Link the requirement (FR-/NFR-) or test case (TC-) if known. -->

## Steps to reproduce
1.
2.
3.

## Severity (see Test Plan §10)
- [ ] S1 Critical: crash, data loss, **wrong coordinates**, blocks demo
- [ ] S2 Major: feature broken, no workaround
- [ ] S3 Minor: workaround exists
- [ ] S4 Trivial: cosmetic

## Environment
- Version / commit:
- Deployment: Docker / local dev / edge (Jetson model)
- OS, GPU, runtime (`/api/v1/health` output):
- Browser (UI bugs):

## Evidence
- Survey ID / Job ID:
- Relevant log lines (`data/results/<survey_id>/job.log.jsonl`):
- Screenshots / report excerpt:
- Input file (only if not restricted) or header dump:

## Area
- [ ] ingest  - [ ] preprocess  - [ ] detect  - [ ] scoring  - [ ] geo  - [ ] report
- [ ] api  - [ ] jobs  - [ ] ui  - [ ] cli  - [ ] edge  - [ ] docs
