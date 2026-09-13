# Final Project Report — Template

> **Template.** Copy to `docs/reports/FINAL_PROJECT_REPORT.md` (or into your institution's Word/LaTeX format) and replace every *italic guidance* block. Most content already exists in the documents linked in each section, so **summarise and link rather than copy**. Target length: 40–60 pages including figures, excluding appendices.

---

## Front matter

### Title page
- **AI-Powered Automated Underwater Marine Debris and Anomaly Detection System using Side-Scan Sonar Imagery — SonarSentinel**
- Smart India Hackathon · Problem Statement 26057 · Ministry of Earth Sciences — National Institute of Ocean Technology
- Team name · Team ID · Institution · Mentor(s)
- Team members and roles
- Month, Year

### Declaration / certificate
*As required by your institution.*

### Abstract (250–300 words)
*Problem (ghost nets and debris, manual SSS review bottleneck) → objective → approach (preprocessing, YOLO11-seg + SAHI, PatchCore, shadow physics + calibration, geotagging, dashboard, edge) → data (public SSS datasets, NOAA surveys, synthetic nets) → key measured results (mAP, ghost-net holdout recall, FP reduction, ECE, geolocation error, speed) → significance and limitations.*

**Keywords:** side-scan sonar; marine debris; ghost nets; object detection; anomaly detection; georeferencing; edge AI; disaster management

### Acknowledgements
*Mentors, NIOT/MoES, dataset providers (AI4Shipwrecks, CINAV mine SSS dataset authors, SeabedObjects-KLSG authors, NOAA NCEI/OCS, USGS), open-source projects.*

### Table of contents · List of figures · List of tables · Abbreviations
*Abbreviations: see [PRD Glossary](../PRD.md#18-glossary).*

---

## Chapter 1 — Introduction (3–4 pages)
**Sources:** [Project Idea](../PROJECT_IDEA.md) §1–2, [PRD](../PRD.md) §1–2

1.1 Background: ALDFG/ghost nets, marine debris, disaster relevance
1.2 Side-scan sonar and why manual inspection is a bottleneck
1.3 Problem statement (SIH 26057, quoted and interpreted)
1.4 Objectives (G1–G6)
1.5 Scope and non-goals
1.6 Contributions of this work *(3–5 bullet points, e.g. physics-aware calibrated confidence; geotagging from ping headers; synthetic ghost-net generator + anomaly detection; open edge-ready pipeline)*
1.7 Report organisation

## Chapter 2 — Literature Review (5–7 pages)
**Sources:** [Literature Review](../research/LITERATURE_REVIEW.md)

2.1 Side-scan sonar principles and artefacts
2.2 Classical detection approaches
2.3 Deep learning for sonar imagery
2.4 Datasets and their gaps
2.5 Ghost-net detection efforts
2.6 Anomaly detection, small-object detection, calibration
2.7 Georeferencing and edge deployment
2.8 Research gap and how this project addresses it *(gap table)*

## Chapter 3 — Requirements Analysis (3–4 pages)
**Sources:** [PRD](../PRD.md) §3–7, §11–12

3.1 Stakeholders and personas
3.2 Use cases / user stories *(key ones, full list in appendix)*
3.3 Functional requirements summary *(by module)*
3.4 Non-functional requirements *(performance, offline, edge, security, usability)*
3.5 Success metrics and acceptance criteria
3.6 Traceability to the problem statement *(PRD §17 table)*

## Chapter 4 — System Design (6–8 pages)
**Sources:** [Architecture](../architecture/README.md), [Wireframes](../wireframes/README.md)

4.1 Architecture principles
4.2 System context and container architecture *(diagrams)*
4.3 Processing pipeline design *(stage diagram, data contracts)*
4.4 Data models and report schema
4.5 API and real-time streaming design
4.6 User interface design *(key wireframes → final screenshots)*
4.7 Deployment architecture (shore, edge)
4.8 Key design decisions *(summarise ADRs with rationale)*

## Chapter 5 — Data (4–5 pages)
**Sources:** [Datasets](../data/DATASETS.md), [Annotation Guidelines](../data/ANNOTATION_GUIDELINES.md), [Data Management Plan](../data/DATA_MANAGEMENT_PLAN.md)

5.1 Datasets used *(table with sizes actually used, licences)*
5.2 Class taxonomy and mapping
5.3 Annotation process and quality control *(measured agreement values)*
5.4 Synthetic data generation *(generator design, example figures, realism review results)*
5.5 Dataset splits and leakage prevention *(final manifest statistics)*
5.6 GPS-tagged survey data and ground truth for geolocation
5.7 Ethics and sensitive data handling

## Chapter 6 — Methodology (8–10 pages)
**Sources:** [02-data-pipeline](../architecture/02-data-pipeline.md), [03-ml-models](../architecture/03-ml-models.md), [04-geotagging-engine](../architecture/04-geotagging-engine.md)

6.1 Preprocessing
 - 6.1.1 Navigation cleaning and units
 - 6.1.2 Bottom tracking
 - 6.1.3 Radiometric correction
 - 6.1.4 Slant-range correction and resampling *(equations)*
 - 6.1.5 Quality masks: dropouts, motion
 - 6.1.6 Three-channel input and tiling
6.2 Detection and segmentation (YOLO11-seg, SAHI) *(training configuration, augmentation policy)*
6.3 Anomaly detection (PatchCore) *(normal pool, thresholding)*
6.4 Confidence scoring
 - 6.4.1 Shadow-consistency and height estimation *(equations, figure)*
 - 6.4.2 Feature-based false-positive filter
 - 6.4.3 Score fusion and isotonic calibration; alert tiers
6.5 Geotagging and measurement *(coordinate frames, pixel → lat/lon, layback, uncertainty budget)*
6.6 Merging across tiles, chunks and survey lines
6.7 Edge optimisation (ONNX, TensorRT, INT8)

## Chapter 7 — Implementation (4–6 pages)
**Sources:** repository, [Contributing](../../CONTRIBUTING.md), [Developer Setup](../guides/DEVELOPER_SETUP.md), [Project Plan](../planning/PROJECT_PLAN.md)

7.1 Technology stack and versions *(exact versions used)*
7.2 Repository structure and module overview
7.3 Backend and job pipeline implementation highlights
7.4 Dashboard implementation *(final screenshots of S-01…S-06)*
7.5 Edge deployment implementation
7.6 Development process *(sprints, CI, code review; planned vs. actual timeline)*
7.7 Challenges encountered and how they were solved

## Chapter 8 — Testing and Results (8–10 pages)
**Sources:** [Test Plan](../testing/TEST_PLAN.md), [Test Cases](../testing/TEST_CASES.md), Test Summary Reports, model cards

8.1 Test strategy and environments
8.2 Functional testing results *(pass/fail summary by area; acceptance criteria table)*
8.3 Detection performance *(overall and per-class metrics with 95% CIs; PR curves; confusion matrix)*
8.4 Ghost-net and anomaly detection results *(synthetic holdout; any real samples; example figures)*
8.5 False-positive reduction *(FP/km² before vs. after; ablation of shadow check / FP filter)*
8.6 Calibration results *(reliability diagram; ECE)*
8.7 Geolocation accuracy *(charted-wreck errors table; reciprocal-line analysis)*
8.8 Robustness results *(dropouts, noise, motion, corrupt files)*
8.9 Performance *(GPU/CPU/Jetson timings; memory; model sizes; INT8 impact)*
8.10 Usability evaluation *(task success, times, SUS score, key feedback)*
8.11 Comparison with targets *(PRD §11 table: target vs. achieved)*

**Ablation table (recommended)**
| Configuration | mAP@50 | Ghost-net recall | FP/km² | ECE |
|---|---|---|---|---|
| Detector only (real data) | | | | |
| + synthetic data | | | | |
| + SAHI | | | | |
| + shadow check | | | | |
| + FP filter | | | | |
| + calibration (full system) | | | | |

## Chapter 9 — Discussion (2–3 pages)
9.1 Interpretation of results
9.2 Limitations *(be specific: synthetic ghost-net validation, dataset domains, positioning assumptions, hardware not tested)*
9.3 Threats to validity *(dataset size, chart position accuracy, test set representativeness)*
9.4 Ethical, safety and environmental considerations
9.5 Lessons learned

## Chapter 10 — Conclusion and Future Work (1–2 pages)
10.1 Summary of achievements against objectives
10.2 Impact for MoES/NIOT and disaster management
10.3 Future work *(NIOT data validation, adaptive AUV missions, change detection, multibeam fusion, more formats, real ghost-net dataset)*

## References
*Use one citation style consistently (IEEE recommended). Start from [Literature Review references](../research/LITERATURE_REVIEW.md#references) and verify each entry.*

---

## Appendices

| Appendix | Content | Source |
|---|---|---|
| A | Full functional and non-functional requirements | [PRD](../PRD.md) §6–7 |
| B | API specification summary | [05-api-specification](../architecture/05-api-specification.md) |
| C | Report JSON schema and example report | [06-data-models](../architecture/06-data-models.md) |
| D | Test case list and traceability matrix | [TEST_CASES](../testing/TEST_CASES.md) |
| E | Model cards (final models) | `models/*/model_card.md` |
| F | Annotation guidelines | [ANNOTATION_GUIDELINES](../data/ANNOTATION_GUIDELINES.md) |
| G | User manual (condensed) | [USER_MANUAL](../guides/USER_MANUAL.md) |
| H | Dataset licences and third-party software licences | [LICENSES_AND_COMPLIANCE](../legal/LICENSES_AND_COMPLIANCE.md) |
| I | Team contributions *(who did what, by role and module)* | Project Plan RACI + git history |
| J | Glossary | [PRD §18](../PRD.md#18-glossary) |

---

## Report quality checklist
- [ ] Every number in the report comes from a recorded test run or reference (link or appendix)
- [ ] Synthetic vs. real results clearly separated
- [ ] Figures have captions, units, and sources; diagrams readable in print
- [ ] Limitations stated honestly
- [ ] No sensitive data (restricted survey locations, human remains) in figures
- [ ] References verified and consistently formatted
- [ ] Proofread by at least two team members
- [ ] Exported to PDF with embedded fonts
