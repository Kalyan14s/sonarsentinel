# SonarSentinel — Demo Script & Judge Q&A

| | |
|---|---|
| **Version** | v1.1 · 2026-09-14 (Sprint 6 values; see the note below §1) |
| **Owner** | PM (R6) presents; R5 drives the dashboard; R1 & R3 answer technical questions |
| **Length** | 3-minute core demo (extendable to 6 minutes) |

**Related:** [SIH Presentation](SIH_PRESENTATION.md) · [User Manual](../guides/USER_MANUAL.md) · [Operations Runbook](../guides/OPERATIONS_RUNBOOK.md) · [Project Plan §13](../planning/PROJECT_PLAN.md#13-hackathon-finale-readiness)

---

## 1. Demo assets

| Asset | Purpose | Location |
|---|---|---|
| **A1** NOAA/USGS `.xtf` survey line covering a **charted wreck** (trimmed to ~1–2 min processing) | Main flow with real GPS | `demo/line_wreck.xtf` |
| **A2** Same area charted wreck position + screenshot of chart | Proof of geolocation accuracy | `demo/ground_truth.json`, `demo/chart.png` |
| **A3** Waterfall PNG + navigation CSV containing a **synthetic ghost net** | Ghost-net story (clearly labelled synthetic) | `demo/harbour_synthetic.png`, `.csv` |
| **A4** Pre-processed survey already in History | Instant fallback if live processing is slow | Dashboard History |
| **A5** Exported `report.kml` / `report.csv` | Show in Google Earth / Excel | `demo/exports/` |
| **A6** Full screen recording of the demo (≤ 4 min, captioned) | Backup if the laptop fails | `demo/backup_demo.mp4` + USB + cloud |
| **A7** Test Summary Report numbers | Answering metric questions | `docs/testing/reports/TSR-M6.md` |

> **Status 2026-09-14:** only **A3** exists (`demo/`). A1/A2 need a NOAA line with a charted wreck, A4–A6 need a rehearsal on the final build. With the CPU baseline detector, the A3 ghost net (8 × 4 m, synthetic) is found only as a **hidden-tier `cylinder`** about 2.6 m from its true position: set the confidence filter to include *hidden* for this segment, or re-record after GPU training. Values marked *not measured yet* must not be spoken as results.

## 2. Setup checklist (T–30 minutes)

- [ ] Laptop on mains power; sleep and notifications disabled; display scaling 100–125%
- [ ] `docker compose up -d`; smoke test passed ([Runbook §4](../guides/OPERATIONS_RUNBOOK.md#4-smoke-test-after-install-upgrade-or-restart))
- [ ] Health shows the expected runtime (`onnxruntime` on the CPU laptop; `cuda` only on a GPU machine)
- [ ] **Offline basemap** active (don't depend on venue Wi-Fi)
- [ ] Browser: one window, zoom 110%, bookmarks bar hidden, tabs: Dashboard · Google Earth/QGIS with A5 · slide deck
- [ ] Clear old demo surveys except A4; set the confidence filter default to 30%
- [ ] Files A1 and A3 on the desktop for drag-and-drop
- [ ] Backup video A6 open in a paused player
- [ ] Second laptop with the same setup (or at least A4 + A6)
- [ ] Everyone knows their role and the hand-off cues

## 3. Core demo (3 minutes)

| Time | Presenter says | Driver does | Screen |
|---|---|---|---|
| 0:00 | "Here is a real side-scan sonar log from a NOAA survey, exactly as it comes off the sonar, with GPS in every ping." | Drag **A1** onto Upload | S-01: file row shows `[ok] GPS found`, pings, sonar model |
| 0:15 | "No manual setup. We just start the analysis." | Click **Start analysis** | Redirect to S-02 |
| 0:20 | "As the sonar data is cleaned and scanned, the survey track draws itself, and detections appear live." | Let it run; point at progress stage | Track grows; progress bar |
| 0:45 | "Here's a detection. It's the charted wreck." | Click the **shipwreck** marker | S-03 detail drawer |
| 0:55 | "The system shows the sonar evidence, the object outline and its acoustic shadow. That shadow is how we tell a real object from a dark patch." | Toggle overlay **Mask → Shadow** | Chip overlays |
| 1:10 | "Confidence is 9x%, and here's *why*: the detector, the shadow check, the false-positive filter. Nothing is a black box." | Point at score bars | Why-confidence section |
| 1:25 | "Its coordinates come from the sonar's navigation. The official chart puts this wreck *[median error from `scripts/validate_charted_wreck.py`, not measured yet]* metres away." | Show lat/lon; switch to chart screenshot A2 | Location + chart |
| 1:45 | "Now ghost nets. No public dataset exists, so we trained on simulated nets. This image contains one, and it's labelled as synthetic." | Upload **A3** with CSV (or open from History) | S-02 with ghost-net marker |
| 2:10 | "Here it is, with its GPS position. The object is 8 × 4 metres." (CPU baseline: shows as a hidden-tier cylinder, so say "our early model flags it for review"; after GPU training say the class and confidence shown) | Click the ghost-net marker | Detail drawer |
| 2:25 | "Data problems are never hidden. This red segment is missing sonar data, and detections there get lower confidence." | Click warning in status bar | Track warning segment |
| 2:40 | "One click gives the recovery team a report they can open in Google Earth or a spreadsheet." | Click **KML**; switch to Google Earth tab with A5 | Placemarks on map |
| 2:55 | "And the same model runs offline on an underwater drone's computer." | Return to slides (edge/performance slide) | Slide 11 |

## 4. Extended segments (if time allows, +3 minutes)

| Segment | Talking point | Actions |
|---|---|---|
| **Review queue** (1 min) | "Experts confirm or reject in seconds, and every decision becomes training data." | Open Review; press `C`, `R` (reason: Rock) |
| **Filters** (30 s) | "Focus on what matters: hazards only." | Drag confidence slider to 80; untick classes |
| **CLI / edge** (30 s) | "Same engine, headless, for batch or on-board." | Terminal: `sonarsentinel detect demo/harbour_synthetic.png --nav demo/harbour_synthetic.csv --out out/`; mention `sonarsentinel watch` for on-board folders |

## 5. Failure recovery

| Problem | Immediate action | Line to say |
|---|---|---|
| Live processing slow | Open pre-processed **A4** from History | "To save time, here's the same survey processed a moment ago." |
| Upload/validation error | Use A4 | Same as above |
| Backend down | `docker compose restart backend` (driver) while presenter continues with slides; else play **A6** | "While that restarts, let me show you the recorded run." |
| Map tiles missing | Continue; markers and track still show | "The map background is offline here; the positions are unaffected." |
| Laptop failure | Switch to second laptop or play A6 from USB | "Switching to our backup machine." |
| Unexpected false detection appears | Use it: open detail, show low confidence / reject in review | "Good example: low confidence, flagged for review, one key to reject." |

**Rule:** don't debug in front of the judges for more than 20 seconds. Switch to the fallback.

## 6. Role hand-offs

| Cue | From → To |
|---|---|
| "Let me show you live." | Presenter (R6) → Driver (R5) |
| Technical deep-dive question on models | Presenter → R1 |
| Question on coordinates/accuracy | Presenter → R3 |
| Question on sonar data handling | Presenter → R2 |
| Question on deployment/cost/edge | Presenter answers (R6) |
| Wrap-up | Anyone → Presenter |

## 7. Judge Q&A preparation

Keep answers ≤ 30 seconds. Values below are from the CPU baseline (2026-09-14); update them from TSR-M6 after GPU training.

### Problem & scope
1. **Why side-scan sonar and not cameras?**
   Underwater visibility is often near zero, and cameras see only a few metres. SSS images wide swaths (tens to hundreds of metres per side) regardless of light or turbidity. That's why survey agencies use it.
2. **How is this different from GhostNetZero?**
   Same motivation, and we cite it. Our focus: an open end-to-end pipeline from raw files to GPS reports, explicit handling of dropouts and motion, calibrated explainable confidence, anomaly detection for unknown objects, and offline edge deployment for Indian survey operations.
3. **What exactly counts as debris in your system?**
   Five trained classes (ghost net, shipwreck, pipe, cylinder, other debris) plus "unknown anomaly" for unusual objects outside those classes.

### Data & ghost nets
4. **You have no real ghost-net data. Why should we believe it works?**
   We don't claim proven field performance. Three layers: synthetic nets rendered with sonar physics (our CPU baseline was trained before the net generator existed, so its synthetic-holdout recall is 0.00; retraining with synthetic nets is the next step), an anomaly model that flags anything unlike normal seabed, and a review loop that turns confirmed real nets into training data. Real NIOT or partner samples are our top validation request.
5. **Won't the model just learn your simulator?**
   Synthetic data is capped at 40% of positives, backgrounds are real seabed, generator parameters are varied, and the test set is real-only. Synthetic results are reported separately.
6. **Where does GPS come from if images don't have it?**
   From the sonar file itself: every ping in an XTF file stores position, heading, altitude and range. We compute each pixel's position geometrically. For plain images we accept a navigation CSV; without it we clearly mark results as not geotagged.

### Accuracy & reliability
7. **How accurate are the coordinates?**
   Charted-wreck validation on NOAA data is prepared but not measured yet. Every detection carries an uncertainty estimate from GNSS, heading, layback and timing errors. Towed sonars are typically metre-to-ten-metre class depending on positioning.
8. **How do you reduce false positives from rocks and shadows?**
   A shadow-geometry check (real objects produce a highlight followed by a consistent shadow), shape and texture features in a LightGBM filter, hard-negative training, and calibrated tiers. On validation data the false-positive filter separates true from false detections with AUROC 0.75; the reduction in false positives per km² is not measured yet (it needs contact-free survey lines).
9. **What does "87% confidence" mean?**
   It is calibrated on validation data: among detections scored around 87%, roughly 87% were correct. Our calibration error (ECE) is 0.048 on a held-out site; with today's early detector most scores are low, and that is what the calibration shows honestly. The panel shows which evidence contributed.
10. **What about heave, pitch, roll and dropouts?**
    Bottom tracking and GPS-based resampling correct geometry; motion and dropout segments are detected, shown on the map, and reduce confidence. Nothing is silently hidden.
11. **Different sonars have different resolutions. Does it generalise?**
    We resample everything to a fixed 10 cm per pixel and normalise brightness, and training uses data from several sonar models. For a new sonar, we recommend fine-tuning on a small labelled sample, which the review queue provides.

### Technology & deployment
12. **Why YOLO instead of Faster R-CNN or U-Net?**
    It provides boxes and masks, runs in real time, and exports cleanly to TensorRT/OpenVINO for edge. We add U-Net-style refinement for thin nets and SAHI for small objects (ADR-002/004).
13. **Can it really run on an underwater drone?**
    The detector is about 20 MB (39 MB as ONNX) and runs at about 150 ms per tile on a laptop CPU; Jetson and TensorRT are not measured yet. Heavier steps such as the anomaly model and mosaicing can run on shore.
14. **What if there is no internet on the ship?**
    Everything runs offline, including map tiles; there are no cloud dependencies.
15. **How long does it take to process a survey?**
    About 4 minutes (240 s) per 1 km of real survey line on a laptop CPU; GPU not measured yet (targets: 60 s on GPU, 5 min on CPU).
16. **Is the data secure?**
    On-premise by default, no telemetry, restricted-data handling rules, upload validation. Suitable for sensitive seabed data.

### Feasibility, cost & future
17. **What would it cost to deploy?**
    The software is open source. Hardware is a GPU workstation for shore processing and optionally a Jetson-class module per vessel/AUV. There are no licence fees apart from the choice of licence for the Ultralytics component (AGPL or commercial).
18. **What do you need from NIOT?**
    Sample survey logs from Indian waters, any known ghost-net/debris locations for validation, and the target sonar and edge hardware specifications.
19. **What's next after the hackathon?**
    Validation on NIOT data, AUV adaptive re-survey of anomalies, change detection between repeat surveys, and fusion with multibeam bathymetry.
20. **What was the hardest part?**
    Having no ghost-net ground truth, and making coordinates trustworthy. We addressed them with synthetic data plus anomaly detection, and with physics-based geotagging validated against charted wrecks.

## 8. Rehearsal log

| # | Date | Duration | Issues found | Fixes |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |

**Target:** 3 clean rehearsals, including one with a simulated failure (switch to A4/A6).
