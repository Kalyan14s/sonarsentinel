# SonarSentinel — Outreach Message Drafts

| | |
|---|---|
| **Version** | v1.0 · 2026-09-13 |
| **Owner** | PM / Integration & Edge Lead (R6); R1 for dataset messages |
| **Status** | Drafts, ready to personalise and send. **Nothing here has been sent.** |

**Related:** [TODO Phase 1](../../TODO.md#phase-1--sprint-0--project-setup) · [PRD §16 open questions](../PRD.md#16-open-questions) · [Licences & Compliance](../legal/LICENSES_AND_COMPLIANCE.md)

> **How to use:** replace every `<placeholder>`. Use official contact details from the organisation's own website or your SPOC; this file intentionally contains **no email addresses**. Log each message in the tracker (§7) with the date sent and the follow-up date.

---

## 1. College SPOC — confirm SIH 2026 deadline and nomination (send today)

**To:** `<college SIH SPOC name>` (via the channel your college uses)
**Subject:** SIH 2026: confirm idea-submission deadline and nomination for PS 26057

> Dear `<SPOC name>`,
>
> Our team is preparing an idea for **Smart India Hackathon 2026, Problem Statement 26057** — *AI-Powered Automated Underwater Marine Debris and Anomaly Detection System using Side-Scan Sonar Imagery* (MoES / NIOT, Software, Disaster Management).
>
> Could you please confirm:
> 1. The **idea submission and team nomination deadline**. The current SIH 2026 Guidelines and problem-statement page show **30 September 2026**, but an older guideline PDF on sih.gov.in mentions **15 September 2026**.
> 2. The **date and format of our college's internal hackathon**, and when nominated teams will be entered on the portal.
> 3. The documents you need from us (team details, nomination letter, idea PDF).
>
> Our team: `<team name>` · 6 members (including at least one female member), all from `<college>`. Team leader: `<name>`.
>
> Thank you,
> `<name>`, `<role>`, `<team name>`

**Follow-up:** next working day if no reply.

---

## 2. NIOT — sample data and domain questions (PRD Q1, Q2, Q4, Q6, Q7)

**To:** `<NIOT contact>` (via the SIH problem-statement contact, mentor, or official NIOT channels)
**Subject:** SIH 2026 PS 26057: request for sample side-scan sonar data and technical guidance

> Dear `<name>`,
>
> We are a Smart India Hackathon 2026 team working on **PS 26057** (AI-based marine debris and ghost-net detection in side-scan sonar imagery). Our prototype, *SonarSentinel*, reads raw sonar logs, detects man-made objects with calibrated confidence, and reports their GPS positions. It runs offline and on edge hardware.
>
> To align the prototype with NIOT's operations, we would be grateful for help with:
> 1. **Sample data:** a small set of side-scan sonar logs from Indian waters (`.xtf` or `.jsf`), ideally including known targets. We will use them only for this project, keep them on-premise, and delete them afterwards if required.
> 2. **Sonar equipment:** the side-scan sonar models, frequencies and range settings typically used.
> 3. **Edge hardware:** the on-board or AUV computer you would expect such software to run on.
> 4. **Ground truth:** any known locations of ghost nets or debris usable for validation.
> 5. **Reporting:** the datum/CRS and report formats preferred for hazard reports (e.g. WGS84, CSV/KML, S-57/S-100).
>
> Our project summary is attached. Any guidance, even partial, would help greatly.
>
> Regards,
> `<name>`, `<team name>`, `<college>`

**Attach:** `PROJECT_IDEA.md` exported to PDF. **Follow-up:** 5 working days.

---

## 3. WWF Germany / GhostNetZero — ghost-net sample access (PRD Q6)

**To:** GhostNetZero project team (use the contact route on the official project site, ghostnetzero.ai, or the Microsoft AI for Good Lab / WWF Germany pages)
**Subject:** Student research request: side-scan sonar ghost-net samples for validation

> Dear GhostNetZero team,
>
> We are an Indian student team in the Smart India Hackathon 2026, working on automated ghost-net detection in side-scan sonar for the National Institute of Ocean Technology problem statement. Your GhostNetZero work (Miao et al., 2025) is a key reference for us.
>
> Public labelled side-scan sonar data of ghost nets doesn't exist, so our prototype currently relies on synthetic nets and anomaly detection. Would it be possible to access a **small number of labelled ghost-net sonar examples** for **validation only** (not redistribution)? We will follow any terms you set, credit your project, and share our evaluation results with you.
>
> If data sharing isn't possible, any advice on how ghost nets typically appear in side-scan imagery (frequency, range, typical signatures) would also be very valuable.
>
> Kind regards,
> `<name>`, `<team name>`, `<college>`, India

**Follow-up:** 10 working days.

---

## 4. S3Simulator authors — dataset permission (optional)

**To:** paper authors (contact details from the ICPR 2024 paper or the repository `NambiarAthira/S3Simulator`)
**Subject:** Permission to use the S3Simulator dataset in an open-source student project

> Dear Dr. Nambiar and `<co-author>`,
>
> We are building an open-source (AGPL-3.0) student prototype for side-scan sonar debris detection (Smart India Hackathon 2026). We would like to use the **S3Simulator dataset** as additional synthetic training data, but couldn't find a licence in the repository.
>
> Could you let us know whether we may use it for training and evaluation, and under which terms (e.g. CC BY 4.0)? We will cite your ICPR 2024 paper and won't redistribute the data without permission.
>
> Thank you,
> `<name>`, `<team name>`

**Follow-up:** 10 working days. **Until a written reply:** dataset stays excluded.

---

## 5. AI4Shipwrecks — licence clarification (only if the Deep Blue record shows no licence)

**To:** University of Michigan Field Robotics Group (contact via the AI4Shipwrecks project site)
**Subject:** Licence terms for the AI4Shipwrecks dataset

> Dear AI4Shipwrecks team,
>
> We plan to use the AI4Shipwrecks dataset (Sethuraman et al., IJRR 2025) for training and evaluation in an open-source student prototype (AGPL-3.0) for side-scan sonar debris detection. Could you confirm the licence that applies to the dataset (e.g. CC BY 4.0), including whether trained model weights may be shared? We will cite the dataset and paper.
>
> Many thanks,
> `<name>`, `<team name>`

---

## 6. Mentor — Phase 0 review and IP question

**To:** `<mentor name>`
**Subject:** SonarSentinel: documentation baseline review + AGPL / SIH IP question

> Dear `<mentor name>`,
>
> Our documentation baseline (requirements, architecture, plan) is ready for review; the checklist is in `docs/planning/PHASE0_REVIEW_SIGNOFF.md`. We would value your comments this week.
>
> One question: we licensed the project under **AGPL-3.0** (required by the YOLO detector we use). SIH 2026 guidelines say a winning idea's IP is shared with the problem-statement organisation. Do you see any conflict, and should we raise it with the SPOC or NIOT?
>
> Thank you,
> `<name>`

---

## 7. Outreach tracker

| # | Recipient | Purpose | Sent (date) | Follow-up due | Reply / outcome | Owner |
|---|---|---|---|---|---|---|
| 1 | College SPOC | Deadline + nomination | | | | R6 |
| 2 | NIOT | Data + domain questions | | | | R6 |
| 3 | GhostNetZero / WWF | Ghost-net samples | | | | R6 |
| 4 | S3Simulator authors | Dataset permission (optional) | | | | R1 |
| 5 | AI4Shipwrecks team | Licence (if needed) | | | | R1 |
| 6 | Mentor | Baseline review + IP question | | | | R6 |
