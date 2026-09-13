# frontend

SonarSentinel dashboard: React 18 + TypeScript + Vite + **Leaflet used directly** (no react-leaflet, see ADR-009).

- **Status (Sprint 3, ST-090):** app shell, routing for all wireframe screens, design tokens, typed API client and generated report types. The Live Map page runs against the mock API (track, streaming detections, filters); Upload, Reports and History are first cuts; review, waterfall and settings screens follow in Sprints 4–6.
- Design: [wireframes](../docs/wireframes/README.md) · styling: CSS Modules + design tokens ([ADR-014](../docs/architecture/08-architecture-decisions.md#adr-014--frontend-styling-css-modules--css-custom-property-design-tokens))
- API contract: [05-api-specification](../docs/architecture/05-api-specification.md)

```bash
npm ci
sonarsentinel serve --mock --port 8001   # in another terminal (backend with the api extra)
npm run dev                              # http://localhost:5173; /api and /ws proxy to SONARSENTINEL_API (default http://127.0.0.1:8001)
npm run lint && npm run typecheck && npm test && npm run build
npm run gen:types                        # regenerate src/api/report-schema.ts from the report JSON Schema
```

| Path | Contents |
|---|---|
| `src/api/` | `client.ts` (REST + WebSocket with `seq` resume), `report-schema.ts` (generated) |
| `src/components/` | App bar, workspace layout |
| `src/map/` | Leaflet map view and marker rendering |
| `src/pages/` | Screens per route |
| `src/styles/` | `tokens.css` (colours, class and tier tokens), global styles |

CI runs lint, typecheck, tests and build on every pull request.
