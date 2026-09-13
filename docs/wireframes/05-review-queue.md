# S-05 · Review Queue

[← Wireframes index](README.md) · **Priority:** P1 · **Requirements:** FR-UI-10, FR-OPS-04, US-10

## Purpose
Help an analyst quickly verify uncertain detections (the `review` and `anomaly` tiers, plus optionally `hazard`) with minimal clicks. Every decision improves the report and becomes training data.

## Desktop wireframe

```text
+--------------------------------------------------------------------------------------------------+
| (~) SonarSentinel     Upload     Live Map    [Review (5)]  Reports    History     Settings  (?)  |
+--------------------------------------------------------------------------------------------------+
| REVIEW QUEUE - Chennai-Port-Line07        Show: [x] Review [x] Anomaly [ ] Hazard  3 of 8 done   |
| [###########..............................]  37%                                                 |
+------------------------------------+-------------------------------------------------------------+
| PENDING (5)         Sort [Conf v]  | D4  == PIPE                       62%   [ REVIEW ]          |
+------------------------------------+                                                             |
| > == Pipe  D4        62%  REVIEW   | +------------------+   +---------------------------------+  |
|   21 x 0.6 m - starboard           | | .:.:.:.:.:.:.:.: |   | MAP                             |  |
+------------------------------------+ | .:.:.:.:.:.:.:.: |   |                                 |  |
|   ?? Anomaly  D7     41%  ANOMALY  | | ================ |   |    S..................>         |  |
|   2.1 x 1.4 m - port               | | .:.:.:.:.:.:.:.: |   |            ==D4                 |  |
+------------------------------------+ | .:.:.:.:.:.:.:.: |   |                                 |  |
|   <> Ghost net  D2   58%  REVIEW   | +------------------+   +---------------------------------+  |
|   3.4 x 2.0 m - port               | Overlay: (o) Mask ( ) Shadow ( ) Anomaly                    |
+------------------------------------+                                                             |
|   () Cylinder  D5    55%  REVIEW   | 13.083590, 80.310200 - depth 17.9 m - +/- 4.0 m             |
|   1.6 x 0.7 m - starboard          | Why 62%: detector 0.58 - shadow 0.71 - FP filter 0.66       |
+------------------------------------+          straight edges detected; shadow consistent         |
|   [] Other debris  D652%  REVIEW   |                                                             |
|   1.2 x 1.1 m - starboard          +-------------------------------------------------------------+
+------------------------------------+ IS THIS A REAL MAN-MADE OBJECT?                             |
|                                    |                                                             |
| DONE (3)                           |  [ CONFIRM (C) ]   [ REJECT (R) ]      [ RECLASSIFY (K) v ] |
|   <> D3  confirmed                 |                                                             |
|   /\ D1  confirmed                 | Reason: ( ) Rock ( ) Shadow ( ) Ripples ( ) Noise ( ) Other |
|   ?? D8  rejected - rock           | Note [                                                  ]   |
|                                    |                                                             |
|                                    | [x] Auto-advance [ Skip S ]  [ < Prev P ]  [ Next N > ]     |
+------------------------------------+-------------------------------------------------------------+
| Keys: C confirm - R reject - K reclassify - S skip - N/P next/prev - 1-6 class - Z undo          |
+--------------------------------------------------------------------------------------------------+
```

## Completed state

```text
+--------------------------------------------------------------+
|                                                              |
|                   [ok] Review complete                       |
|     8 reviewed: 5 confirmed, 2 rejected, 1 reclassified      |
|                                                              |
|       [ Download updated report ]   [ Back to map ]          |
|                                                              |
+--------------------------------------------------------------+
```

## Components

| # | Component | Behaviour | Data source |
|---|---|---|---|
| 1 | Queue header | Tier filters, progress (done / total), survey name | `GET /surveys/{id}/detections?review_status=pending&tier=…` |
| 2 | Pending list | Class icon, ID, confidence, tier, size, side; current item marked `>` | Same |
| 3 | Evidence panel | Large chip with overlay switch; mini map centred on the object; coordinates; plain-language "why" summary generated from the score breakdown | Detection, chip |
| 4 | Decision bar | Confirm / Reject (with reason) / Reclassify (class list) + note | `PATCH /detections/{id}` |
| 5 | Done list | Reviewed items with verdict; click to reopen and change | Detections with `review_status ≠ pending` |
| 6 | Shortcut bar | Always visible key hints | — |

## Interactions
1. The queue opens on the lowest-confidence pending item by default. Sorting by confidence descending is available for "quick wins".
2. **C / R / K** apply the decision and save immediately (optimistic UI). With auto-advance on, the next item loads.
3. **Reject** needs a reason (one key press: 1–5 in reject mode). The reason is stored for hard-negative mining.
4. **Z** undoes the last decision within 10 s.
5. Reviewing items from S-03 and here stays in sync (same endpoint).

## States
- **Empty queue:** "Nothing to review — all detections are high-confidence or already reviewed" + [Back to map].
- **Offline save failure:** item marked "Not saved" with retry; the queue keeps going; retries automatically when reconnected.

## Acceptance notes
- An analyst can review 20 items in ≤ 3 minutes using only the keyboard.
- Every decision creates a label record (chip, mask, class, verdict, reason) in the label store.
