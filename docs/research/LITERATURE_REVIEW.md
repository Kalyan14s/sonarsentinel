# SonarSentinel — Literature & Technology Review

| | |
|---|---|
| **Version** | v1.0 · 2026-09-13 |
| **Owner** | ML Lead (R1) with Sonar Engineer (R2) |
| **Purpose** | Background for design decisions, the SIH presentation and the final report |

> **Reference verification (2026-09-13):** the 11 project-specific references ([1]–[3], [8], [11], [19]–[24]) were checked against Crossref, publisher, arXiv, BMVC, FAO and Microsoft Research records. Authors, venues, pages and DOIs are corrected below, and no unverified (†) entries remain. The other references are standard, widely cited method papers and books; spot-check their page numbers before final submission.

**Related:** [Project Idea](../PROJECT_IDEA.md) · [ML Models](../architecture/03-ml-models.md) · [Datasets](../data/DATASETS.md) · [Architecture Decisions](../architecture/08-architecture-decisions.md)

---

## 1. Scope and method

**Questions this review answers**
1. What makes debris and ghost-net detection in side-scan sonar (SSS) hard?
2. Which classical and deep-learning methods have been used for SSS object detection?
3. What public datasets exist, and what are their gaps?
4. How can unknown objects (ghost nets) be detected with little labelled data?
5. How can SSS detections be georeferenced accurately?
6. How can confidence be made trustworthy, and models run at the edge?

**Sources:** peer-reviewed papers, dataset papers, technical reports, and documentation of open-source tools. Searched: IEEE Xplore, arXiv, Google Scholar, dataset portals (NOAA NCEI, Figshare, Deep Blue Data), GitHub curated lists.

## 2. Problem background: abandoned fishing gear

- Abandoned, lost or otherwise discarded fishing gear (ALDFG), commonly called "ghost gear", keeps catching marine life, damages habitats and creates navigation and economic hazards. A FAO/UNEP report gave an early global overview [1].
- A global meta-analysis estimated that about **5.7% of fishing nets, 8.6% of traps and 29% of lines** are lost each year [2]. The problem is systemic, not occasional.
- Recovery programmes (e.g. in the Baltic Sea) rely on sonar surveys to locate nets before divers retrieve them. Manual image review is the bottleneck, which is what GhostNetZero set out to automate [3].

**Implication for SonarSentinel:** automation must emphasise **recall** (missed nets keep killing), **localisation accuracy** (divers need exact positions) and **human verification** (false alarms waste dive time).

## 3. Side-scan sonar fundamentals

Standard references: Blondel's *Handbook of Sidescan Sonar* [4] and Lurton's *Introduction to Underwater Acoustics* [5].

| Property | Effect on detection | Our handling |
|---|---|---|
| **Slant-range geometry**: the sonar measures distance along the acoustic path, not horizontal distance | Distortion near nadir; object size depends on range | Slant-to-ground correction (FR-PRE-02) |
| **Acoustic shadows**: regions behind objects receive no sound | Shadow shape reveals height and man-made geometry; also a source of false positives | Shadow-consistency score, height estimate (FR-CONF-01/07) |
| **Speckle**: coherent imaging creates multiplicative granular noise | Hides fine structures like mesh | Lee filtering [6] + raw channel + texture channel |
| **Gain / beam pattern / range attenuation** | Brightness varies with range and between sides | Across/along-track and per-side normalisation |
| **Vehicle motion** (heave, pitch, roll, yaw) | Wavy nadir, stretched/compressed imagery, side imbalance | Bottom tracking, motion flags, GPS-distance resampling |
| **Dropouts** | Missing pings / corrupted lines | Detection, inpainting, masks, confidence penalties |
| **Frequency / resolution trade-off** | Higher frequency = finer detail, shorter range | Fixed-resolution resampling; survey recommendations for ghost nets |
| **Layback / positioning** | Towed-sonar position differs from ship GNSS | Layback correction, uncertainty budget |

## 4. Classical approaches

| Approach | Idea | Strengths | Weaknesses |
|---|---|---|---|
| **Despeckling filters**: Lee [6], Frost [7] | Adaptive local-statistics filtering of multiplicative noise | Simple, fast, well understood | Oversmoothing removes fine texture |
| **Highlight–shadow segmentation** (e.g. mine-like object detection) [8] | Segment bright echo and dark shadow, analyse their geometry | Physically grounded; interpretable | Sensitive to parameters and seabed type |
| **Handcrafted texture features**: GLCM [9], Gabor, FFT | Characterise texture differences (rock vs. sand vs. man-made) | Low data needs; interpretable | Limited expressiveness; needs tuning |
| **Classical classifiers** (SVM, boosted trees) on features | Learn decision boundaries on features | Works with small data | Upper bound set by feature quality |

**Takeaway:** classical physics and texture cues remain valuable as **complementary evidence** for scoring and false-positive filtering. SonarSentinel reuses them in the scoring stage (shadow, GLCM, FFT → LightGBM [10]).

## 5. Deep learning for sonar imagery

### 5.1 Overview
Surveys of deep learning for sonar imagery [11] describe a shift from handcrafted features to CNN-based classification, detection and segmentation. They also note recurring issues: **small datasets**, **domain shift between sonars**, and **limited public benchmarks**.

### 5.2 Methods relevant to SonarSentinel

| Method | Reference | Relevance |
|---|---|---|
| YOLO family (one-stage real-time detection) | Redmon et al. [12]; Ultralytics YOLO11 [13] | Primary detector; fast, edge-exportable, supports segmentation |
| Faster R-CNN / Mask R-CNN (two-stage) | Ren et al. [14]; He et al. [15] | Accurate alternatives; heavier for edge (ADR-002) |
| U-Net (encoder–decoder segmentation) | Ronneberger et al. [16] | Mask refinement for thin nets and pipes |
| Segment Anything (promptable segmentation) | Kirillov et al. [17] | Faster annotation of masks (human-corrected) |
| Slicing Aided Hyper Inference (SAHI) | Akyon et al. [18] | Small objects in large images without downscaling |
| Transfer learning + semi-synthetic training data for SSS classification | Huo et al. [19] | Shows pretrained CNNs + semi-synthetic data help with scarce SSS data |
| Shipwreck segmentation benchmark in SSS | Sethuraman et al. [20] | Real SSS segmentation data and baselines |
| Zero-shot sim-to-real shipwreck segmentation (STARS) | [21] | Evidence that simulation can transfer to real sonar |
| Simulated SSS benchmark dataset (S3Simulator) | [22] | Relevant simulation approach; dataset has no published licence, so it's used only with the authors' permission |

### 5.3 Lessons applied
1. **Pretrained backbones + small real datasets** work if augmentation and synthetic data are handled carefully [19].
2. **Simulation helps** but must be validated on real data [21, 22]. We keep the test set real and report synthetic results separately.
3. **Physically invalid augmentations** (arbitrary rotations) break shadow geometry, so we disable them (see [ML Models §3.2](../architecture/03-ml-models.md#32-augmentation-policy)).
4. **Resolution consistency** matters more in sonar than in natural images, so we resample to a fixed metres-per-pixel scale.

## 6. Public datasets

| Dataset | Sensor | Content | Labels | Gap for our problem |
|---|---|---|---|---|
| AI4Shipwrecks [20] | SSS (EdgeTech 2205 on Iver3 AUV) | 286 images, 28 wrecks | Pixel masks | Wrecks only; freshwater site |
| Mine-detection SSS [23] | SSS (Marine Sonic on Gavia AUV) | 1,170 images | MILCO/NOMBO annotations | Mine-like objects only |
| SeabedObjects-KLSG [19] | SSS (several vendors) | Ships, planes, mines, victims, seafloor | Image-level classes | Classification crops; no masks; no nets |
| Marine Debris FLS dataset [24] | **Forward-looking** sonar (ARIS) | Small debris objects in a tank | Semantic segmentation | Different sensor geometry; not SSS |
| S3Simulator [22] | Simulated SSS | Synthetic scenes | Simulated labels | Synthetic; no published data licence |
| NOAA NCEI hydrographic surveys | SSS (various) | Real survey data with navigation | None | Unlabelled |

**Key gap:** **no public, labelled side-scan dataset of ghost nets** was found. GhostNetZero [3] reports results on Baltic Sea and Puget Sound data that isn't publicly released as a benchmark. This gap drives our use of synthetic nets, anomaly detection and a human-in-the-loop label store.

## 7. Ghost-net detection with sonar

- **GhostNetZero** (WWF Germany + Microsoft) [3] applies computer vision to SSS-derived imagery and reports ~90% ghost-net detection on its data. It uses a **human-in-the-loop web platform** where experts validate AI suggestions.
- **Physical challenge:** nylon and polyethylene nets have acoustic impedance close to water, so returns are weak. Detection often relies on **structure** (mesh texture, ropes, floats, lead lines, entangled debris) and on **high-frequency, short-range** surveys [4, 5].
- **Forward-looking sonar work** on marine debris [24] shows debris can be segmented at close range, but FLS geometry differs from SSS.

**Positioning of SonarSentinel:** combines (a) SSS-specific preprocessing, (b) supervised detection with synthetic nets, (c) anomaly detection for unseen objects, (d) physics-aware calibrated confidence, and (e) **per-detection geotagging and edge deployment**. We haven't found these combined in one openly documented pipeline.

## 8. Anomaly detection for unknown objects

| Method | Reference | Notes |
|---|---|---|
| PatchCore | Roth et al. [25] | Memory bank of normal patch features; strong accuracy with no anomalous training data; heatmaps |
| EfficientAD | Batzner et al. [26] | Very low latency; attractive for edge |
| anomalib library | Akcay et al. [27] | Implementations, benchmarking and export tools |

**Considerations for sonar:** "normal" seabed is highly variable (sand, mud, rock, vegetation), so the normal pool must cover these types. Contaminated normal data (hidden debris) reduces sensitivity. Thresholds should be set on normal validation data and tuned for recall. We use anomaly scores both as a detection source (`unknown_anomaly`) and as a feature in confidence fusion.

## 9. Small-object detection

Ghost-net components (floats, ropes) and small debris span only a few pixels. Relevant techniques: tiled/sliced inference [18], higher input resolution, detection heads for high-resolution feature maps (P2), and copy-paste augmentation. We evaluate these through ablations (ST-052, ST-055).

## 10. Confidence calibration and false-positive reduction

- Modern neural networks are often **miscalibrated** [28]. Post-hoc calibration such as temperature scaling or **isotonic regression** [29, 30] maps scores to reliable probabilities.
- Calibration is measured with **Expected Calibration Error** and reliability diagrams [28].
- Gradient-boosted trees (LightGBM [10]) over physics and texture features are a data-efficient second-stage false-positive filter. **SHAP** [31] explains feature contributions.
- Density-based clustering (**DBSCAN** [32]) merges repeated sightings across overlapping survey lines, raising confidence through persistence.

## 11. Georeferencing side-scan imagery

- Georeferencing SSS pixels requires the sonar position, heading, altitude and slant range per ping, plus layback for towed systems [4]. Heading errors grow with range; layback errors dominate for long tow cables.
- The **eXtended Triton Format (XTF)** stores sonar data with per-ping navigation and is widely used in hydrographic survey software. Open-source Python readers exist (`pyxtf`) [33].
- Open-source tools such as **PINGMapper** [34] georeference and mosaic recreational-grade SSS, which shows automated georectification is practical.
- **Validation practice:** compare with known targets (charted wrecks) and use reciprocal survey lines to expose layback and timing errors.

## 12. Edge deployment

- Real-time on-vehicle processing enables adaptive missions (re-surveying contacts) and reduces post-survey workload.
- Standard toolchains: **ONNX** export and hardware runtimes (**TensorRT** on NVIDIA Jetson, **OpenVINO** on Intel), with FP16/INT8 quantisation. INT8 needs representative calibration data and accuracy checks.
- Model size and latency favour compact one-stage detectors (YOLO small variants) over two-stage detectors for embedded use.

## 13. Gap analysis → SonarSentinel design

| Gap in current practice / literature | SonarSentinel response | Where |
|---|---|---|
| No public labelled SSS ghost-net data | Synthetic nets + anomaly detection + review-driven label store | 03-ml-models §4–5, §10 |
| Small, heterogeneous SSS datasets | Transfer learning, fixed resolution, physics-valid augmentation, grouped splits | 03-ml-models §3 |
| Uncalibrated scores, many false alarms on rocks/shadows | Shadow physics + LightGBM + isotonic calibration + tiers | 03-ml-models §6–7 |
| Detection results without actionable positions | Per-pixel geotagging with uncertainty; GeoJSON/KML | 04-geotagging-engine |
| Robustness to dropouts and motion rarely addressed end-to-end | Quality masks, flags and penalties | 02-data-pipeline §3 S6 |
| Cloud-dependent or desktop-only tools | Offline, Docker, edge-exportable runtime | 07-deployment |
| Opaque decisions | Score breakdown, model cards, ADRs | PRD FR-CONF-06; docs/ml |

## 14. Open research questions for the project

1. How well do synthetic ghost nets transfer to real SSS nets in Indian coastal waters? (Needs real samples.)
2. Which sonar frequency and range settings give the best ghost-net detectability per km² surveyed?
3. Can anomaly detection stay precise across very diverse seabeds (coral, rock, mud)?
4. How much does cross-line persistence improve precision in practice?
5. What is the real geolocation error budget for NIOT's survey setups?

---

## References

[1] G. Macfadyen, T. Huntington, and R. Cappell, *Abandoned, Lost or Otherwise Discarded Fishing Gear*, UNEP Regional Seas Reports and Studies No. 185; FAO Fisheries and Aquaculture Technical Paper No. 523. Rome, Italy: UNEP/FAO, 2009, ISBN 978-92-5-106196-1.

[2] K. Richardson, B. D. Hardesty, and C. Wilcox, "Estimates of fishing gear loss rates at a global scale: A literature review and meta-analysis," *Fish and Fisheries*, vol. 20, no. 6, pp. 1218–1231, 2019, doi: 10.1111/faf.12407.

[3] Z. Miao, G. Dederer, M. Lee, E. Birsin, C. Fenn, K. Krutzke, T. Stougiannis, R. Dodhia, and J. Lavista Ferres, "GhostNetZero: AI for detecting marine ghost nets," Microsoft AI for Good Lab, Sep. 2025. [Online]. Available: https://www.microsoft.com/en-us/research/publication/ghostnetzero-ai-for-detecting-marine-ghost-nets/ — Preprint version (11 authors, not peer-reviewed): *EcoEvoRxiv*, 2025, doi: 10.32942/X2S061.

[4] P. Blondel, *The Handbook of Sidescan Sonar*, Springer / Praxis, 2009.

[5] X. Lurton, *An Introduction to Underwater Acoustics: Principles and Applications*, 2nd ed., Springer, 2010.

[6] J.-S. Lee, "Digital image enhancement and noise filtering by use of local statistics," *IEEE Transactions on Pattern Analysis and Machine Intelligence*, 2(2), 1980.

[7] V. S. Frost, J. A. Stiles, K. S. Shanmugan, J. C. Holtzman, "A model for radar images and its application to adaptive digital filtering of multiplicative noise," *IEEE Transactions on Pattern Analysis and Machine Intelligence*, 4(2), 1982.

[8] S. Reed, Y. Petillot, and J. Bell, "An automatic approach to the detection and extraction of mine features in sidescan sonar," *IEEE Journal of Oceanic Engineering*, vol. 28, no. 1, pp. 90–105, Jan. 2003, doi: 10.1109/JOE.2002.808199.

[9] R. M. Haralick, K. Shanmugam, I. Dinstein, "Textural features for image classification," *IEEE Transactions on Systems, Man, and Cybernetics*, SMC-3(6), 1973.

[10] G. Ke et al., "LightGBM: A highly efficient gradient boosting decision tree," *Advances in Neural Information Processing Systems (NeurIPS)*, 2017.

[11] Y. Steiniger, D. Kraus, and T. Meisen, "Survey on deep learning based computer vision for sonar imagery," *Engineering Applications of Artificial Intelligence*, vol. 114, Art. no. 105157, Sep. 2022, doi: 10.1016/j.engappai.2022.105157.

[12] J. Redmon, S. Divvala, R. Girshick, A. Farhadi, "You Only Look Once: Unified, real-time object detection," *IEEE/CVF CVPR*, 2016.

[13] Ultralytics, *YOLO11 documentation and software*, https://docs.ultralytics.com

[14] S. Ren, K. He, R. Girshick, J. Sun, "Faster R-CNN: Towards real-time object detection with region proposal networks," *NeurIPS*, 2015.

[15] K. He, G. Gkioxari, P. Dollár, R. Girshick, "Mask R-CNN," *IEEE ICCV*, 2017.

[16] O. Ronneberger, P. Fischer, T. Brox, "U-Net: Convolutional networks for biomedical image segmentation," *MICCAI*, 2015.

[17] A. Kirillov et al., "Segment Anything," *IEEE/CVF ICCV*, 2023.

[18] F. C. Akyon, S. O. Altinuc, A. Temizel, "Slicing aided hyper inference and fine-tuning for small object detection," *IEEE ICIP*, 2022.

[19] G. Huo, Z. Wu, and J. Li, "Underwater object classification in sidescan sonar images using deep transfer learning and semisynthetic training data," *IEEE Access*, vol. 8, pp. 47407–47418, 2020, doi: 10.1109/ACCESS.2020.2978880.

[20] A. V. Sethuraman, A. Sheppard, O. Bagoren, C. Pinnow, J. Anderson, T. C. Havens, and K. A. Skinner, "Machine learning for shipwreck segmentation from side scan sonar imagery: Dataset and benchmark," *The International Journal of Robotics Research*, vol. 44, no. 3, pp. 341–354, Mar. 2025 (online Jul. 2024), doi: 10.1177/02783649241266853. arXiv:2401.14546.

[21] A. V. Sethuraman and K. A. Skinner, "STARS: Zero-shot sim-to-real transfer for segmentation of shipwrecks in sonar imagery," in *Proc. 34th British Machine Vision Conference (BMVC)*, Aberdeen, UK, Nov. 2023, paper 0606. arXiv:2310.01667.

[22] S. Kamal Basha and A. Nambiar, "S3Simulator: A benchmarking side scan sonar simulator dataset for underwater image analysis," in *Pattern Recognition (ICPR 2024)*, Lecture Notes in Computer Science, vol. 15316. Cham, Switzerland: Springer, 2025, pp. 219–235, doi: 10.1007/978-3-031-78444-6_15. arXiv:2408.12833.

[23] N. Pessanha Santos, R. Moura, G. Sampaio Torgal, V. Lobo, and M. de Castro Neto, "Side-scan sonar imaging data of underwater vehicles for mine detection," *Data in Brief*, vol. 53, Art. no. 110132, 2024, doi: 10.1016/j.dib.2024.110132. Dataset: https://dx.doi.org/10.6084/m9.figshare.24574879

[24] D. Singh and M. Valdenegro-Toro, "The marine debris dataset for forward-looking sonar semantic segmentation," in *Proc. IEEE/CVF International Conference on Computer Vision Workshops (ICCVW)*, 2021, pp. 3734–3742, doi: 10.1109/ICCVW54120.2021.00417. arXiv:2108.06800.

[25] K. Roth, L. Pemula, J. Zepeda, B. Schölkopf, T. Brox, P. Gehler, "Towards total recall in industrial anomaly detection," *IEEE/CVF CVPR*, 2022.

[26] K. Batzner, L. Heckler, R. König, "EfficientAD: Accurate visual anomaly detection at millisecond-level latencies," *IEEE/CVF WACV*, 2024.

[27] S. Akcay, D. Ameln, A. Vaidya, B. Lakshmanan, N. Ahuja, U. Genc, "Anomalib: A deep learning library for anomaly detection," *IEEE ICIP*, 2022.

[28] C. Guo, G. Pleiss, Y. Sun, K. Q. Weinberger, "On calibration of modern neural networks," *ICML*, 2017.

[29] B. Zadrozny, C. Elkan, "Transforming classifier scores into accurate multiclass probability estimates," *ACM SIGKDD*, 2002.

[30] A. Niculescu-Mizil, R. Caruana, "Predicting good probabilities with supervised learning," *ICML*, 2005.

[31] S. M. Lundberg, S.-I. Lee, "A unified approach to interpreting model predictions," *NeurIPS*, 2017.

[32] M. Ester, H.-P. Kriegel, J. Sander, X. Xu, "A density-based algorithm for discovering clusters in large spatial databases with noise," *KDD*, 1996.

[33] pyxtf — Python library for reading and writing XTF files, https://github.com/oysstu/pyxtf

[34] PINGMapper — open-source software for georeferencing and mapping recreational-grade side-scan sonar, https://github.com/CameronBodine/PINGMapper
