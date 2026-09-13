---
name: Data / label issue
about: Report a problem with a dataset, labels, splits or synthetic data
title: "[DATA] "
labels: ["type:data"]
---

## Dataset and version
- Dataset / manifest: `sonar-seg@x.y.z` / D1…D10
- Split: train / val / calib / test

## Problem type
- [ ] Wrong or missing label
- [ ] Class mapping error
- [ ] Leakage between splits
- [ ] Corrupt or unreadable file
- [ ] Resolution / georeferencing metadata wrong
- [ ] Unrealistic synthetic sample
- [ ] Licence / provenance unclear
- [ ] **Sensitive content** (e.g. possible human remains, restricted location) → also notify PM immediately

## Affected items
<!-- Tile IDs / file paths / detection IDs. Don't attach restricted data. -->

## Description and proposed fix
<!-- What is wrong, how you found it, and what the correct label/handling should be (see Annotation Guidelines section). -->

## Impact
<!-- Does it affect a released model or the frozen test set? -->
