# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| `main` branch / latest release | ✅ |
| Older pre-releases (`0.x`) | ❌ Upgrade to the latest |

## Reporting a vulnerability

**Please don't open a public issue for security problems.**

1. Use **GitHub private vulnerability reporting** (*Security → Report a vulnerability*) on this repository, or contact the project maintainers privately through the channel listed in the team's contact sheet.
2. Include: affected version/commit, component (API, upload handling, parsers, dashboard, edge runner), steps to reproduce, impact, and any proof-of-concept files. **Don't** include restricted survey data.
3. We aim to acknowledge reports within **3 working days** and to agree on a fix timeline based on severity.
4. Please give us reasonable time to fix the issue before public disclosure. We credit reporters who wish to be named.

## Scope

In scope:
- Upload handling and file parsers (`.xtf`, GeoTIFF, images, CSV): malformed-file crashes, path traversal, resource exhaustion
- REST and WebSocket API: authorisation (once enabled), injection, information disclosure
- Dashboard: XSS, unsafe rendering of file names or metadata
- Docker images and default configuration
- Leakage of restricted data (uploads, results, label store)

Out of scope:
- Vulnerabilities in third-party dependencies without a demonstrated impact on SonarSentinel (report upstream; tell us if an upgrade is needed)
- Attacks requiring physical access to an unlocked operator machine
- Denial of service through intentionally huge legitimate workloads on a single-user workstation

## Security design summary

| Control | Implementation |
|---|---|
| On-premise by default | No telemetry; binds to localhost unless configured |
| Upload validation | Extension allow-list, header/magic-byte checks, size limits, streamed uploads |
| Safe storage | Sanitised filenames; files stored outside the web root; uploaded content never executed |
| Parser hardening | Timeouts and exception isolation per job; corrupt files fail gracefully |
| Dependencies | Pinned versions; `pip-audit`, `npm audit` and image scanning in CI |
| Access control (planned P2) | Token-based login with viewer / analyst / admin roles |
| Data handling | Restricted-data rules in the [Data Management Plan](docs/data/DATA_MANAGEMENT_PLAN.md) |

## Secure deployment recommendations

- Keep the service on a trusted network; use a reverse proxy with HTTPS if accessed by others.
- Keep the host OS, Docker, GPU drivers and images updated ([Operations Runbook §13](docs/guides/OPERATIONS_RUNBOOK.md#13-security-operations)).
- Store secrets in environment files with restricted permissions or a secrets manager. Never commit them.
- Encrypt drives that hold restricted survey data; back up securely.
