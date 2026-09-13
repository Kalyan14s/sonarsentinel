# frontend

SonarSentinel dashboard: React 18 + TypeScript + Vite + **Leaflet used directly** (no react-leaflet, see ADR-009) with `leaflet.markercluster`.

- **Status (Sprint 5):** Upload (S-01), Live Map with streaming markers, track, quality segments, footprints and mosaic (S-02), filters and detection list (ST-093), detection drawer with chips, score breakdown and review (S-03), Reports & export (S-06). Review queue, waterfall viewer, history/settings and offline tiles follow in Sprint 6.
- Design: [wireframes](../docs/wireframes/README.md) · styling: CSS Modules + design tokens ([ADR-014](../docs/architecture/08-architecture-decisions.md#adr-014--frontend-styling-css-modules--css-custom-property-design-tokens))
- API contract: [05-api-specification](../docs/architecture/05-api-specification.md) and [ADR-018](../docs/architecture/08-architecture-decisions.md#adr-018--sprint-5-dashboard-streaming-export-and-edge-decisions)

```bash
npm ci
sonarsentinel serve --mock --port 8001   # in another terminal (backend with the api extra), or the real API
npm run dev                              # http://localhost:5173; /api and /ws proxy to SONARSENTINEL_API (default http://127.0.0.1:8001)
npm run lint && npm run typecheck && npm test && npm run build
npm run gen:types                        # regenerate src/api/report-schema.ts from the report JSON Schema
```

| Path | Contents |
|---|---|
| `src/api/` | `client.ts` (REST + reconnecting WebSocket with `seq` resume), `report-schema.ts` (generated) |
| `src/dashboard/` | Detection store, filters (same rules as the API), filter panel, windowed list, drawer, pixel view |
| `src/map/` | Map controller (incremental Leaflet layers, clustering, mosaic), marker rendering |
| `src/geo/` | DD/DMS formatting identical to the backend |
| `src/upload/` | Upload screen model (validation, badges, options) |
| `src/pages/` | Screens per route |
| `src/styles/` | `tokens.css` (colours, class and tier tokens), global styles |

Manual checks still needed: frame rate with 2,000 clustered markers in a real browser, keyboard/screen-reader pass (TC-UI-010).

CI runs lint, typecheck, tests and build on every pull request.
