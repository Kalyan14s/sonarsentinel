# S-04 · Waterfall Viewer

[← Wireframes index](README.md) · **Priority:** P1 · **Requirements:** FR-UI-09, US-09, US-16

## Purpose
Let analysts inspect the actual sonar imagery the way sonar experts are used to: a scrolling waterfall with port and starboard channels, detection boxes, and quality regions, synchronised with the map.

## Desktop wireframe

```text
+--------------------------------------------------------------------------------------------------+
| (~) SonarSentinel     Upload     [Live Map]  Review (5)    Reports    History     Settings  (?)  |
+--------------------------------------------------------------------------------------------------+
| [ Map ]  [ Waterfall ]  [ Split ]   line_07.xtf   Go to ping [ 10432 ]    [ < Back to map ]      |
+------+-----------------------------------------------------------------+-------------------------+
| PING | PORT  <- 50 m             nadir                50 m ->  STBD    | MINI MAP                |
|      |                              |                                  |                         |
| 10200| .:.::.:..:.:::.:..:.:.::.:   | ..:.:::.:.:.::..:.:.:.::.:       |     . - - .             |
| 10250| :.:..:.:::.:..:.:.::.:.::    | .:.:..:.:::.:.:..:.:.:::.:       | S......[]..........>    |
| 10300| .:.::.:..  +- D1 -----+ .    | :.:::.:..:.:.::.:..:.:.:.:       |     ' - - '             |
| 10350| :.:..:.:.  | /\ 91%   | :    | .:.:..:.:.:.::.:..:.:::.:.       | [] = viewport           |
| 10400| .:.::.:..  +----------+ .    | :.:.:.+- D3 --+ :.:.:.:.::.      |                         |
|>10432|..............................|..:.:.:| <> 87% |.................| CHANNEL                 |
| 10450| .:.::.:..:.:::.:..:.:.::.:   | .:.:.:+-------+ .:.:.::.:.:      | (o) Processed           |
| 10500|xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx|xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx | ( ) Raw                 |
| 10550|xx DROPOUT 10500-560 xx       |xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx | ( ) Despeckled          |
| 10600| .:.::.:..:.:::.:..:.:.::.:   | .:.:..:.:.:.::.:..:.:::.:.       | ( ) Texture             |
| 10650| :.:..:.:::.:..:.:.::.:.::    | :.:.:.:.::.:..:.:.:.:.:.:        |                         |
|      |                                                                 | DISPLAY                 |
|      | Scale: 0.10 m/px - ground-range corrected                       | Gain  [===o===]         |
|      |                                                                 | Contr [====o==]         |
|      |                                                                 | Palette [Gray v]        |
|      |                                                                 | [x] Boxes               |
|      |                                                                 | [x] Quality             |
+------+-----------------------------------------------------------------+-------------------------+
| TIMELINE  S-----/\------<>------------xxxx----------==------------??----------<>--------> END    |
|                         ^ you are here (ping 10,432 of 18,240)                                   |
+--------------------------------------------------------------------------------------------------+
```

## Split mode (map + waterfall)

```text
+------------------------------------------------+-------------------------------------------------+
| MAP                                            | WATERFALL                                       |
| S....[viewport]....>                           | port   |nadir|   stbd                           |
|                                                |  ...  +-D3-+  ...                               |
| Map viewport box follows waterfall scroll      | Scroll waterfall -> map box moves               |
+------------------------------------------------+-------------------------------------------------+
```

## Components

| # | Component | Behaviour | Data source |
|---|---|---|---|
| 1 | View switch | Map / Waterfall / Split; remembered per user | — |
| 2 | Ping axis | Ping numbers; current ping marker `>`; time on hover | Nav table |
| 3 | Waterfall canvas | Virtualised tile rendering (only visible rows loaded); port left, starboard right, nadir centre line; range scale labels | `GET /surveys/{id}/waterfall?ping_start&ping_end&channel` |
| 4 | Detection boxes | Class colour + shape icon + confidence; click → S-03 | Detections |
| 5 | Quality overlays | Dropout (red hatched), high-motion (amber band), water column (dim) | Quality events |
| 6 | Mini map | Track with viewport rectangle; click to jump | Track |
| 7 | Channel selector | Processed (default), Raw, Despeckled, Texture (local std) | Waterfall endpoint `channel` |
| 8 | Display controls | Gain, contrast, palette (Gray, Sepia, Copper, Inverted); display-only, doesn't change results | Client-side |
| 9 | Timeline scrubber | Entire survey with detection ticks and quality segments; drag to scroll | Detections + quality events |
| 10 | Go to ping | Jump to ping number or time | — |

## Interactions
- Mouse wheel scrolls along track; `Ctrl` + wheel zooms (0.5×–4×); drag to pan.
- Hovering a pixel shows ping, side, ground range, and lat/lon in the status bar.
- Shift + drag draws a box to **add a missed detection** (P2); it opens a form for class and note and goes to the label store.
- "Open in waterfall" from S-03 scrolls here and briefly highlights the detection box.

## States
- **Loading tiles:** grey placeholders with ping ranges; scrolling stays smooth.
- **GeoTIFF input:** waterfall unavailable (no ping structure); tab disabled with tooltip "Mosaic input has no ping data".

## Acceptance notes
- Scrolling a 20,000-ping survey stays smooth (virtualised tiles, ≤ 50 MB browser memory for imagery).
- Clicking any detection tick in the timeline centres it in view within 300 ms.
