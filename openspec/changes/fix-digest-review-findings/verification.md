# Review and acceptance — 2026-10-24

Implementation commit: `23d1c0a`.

## Corrected findings

- Failed SMTP delivery no longer produces a successful execution. Saved unsent content can be retried; partial or ambiguous delivery requires explicit operator review before resending.
- Forced regeneration clears stale delivery state. Existing sent records remain idempotent; legacy database rows migrate without losing sent flags.
- Daily collection uses the requested Asia/Shanghai calendar day. GitHub queries latest push activity within the window, and arXiv queries historical submission timestamps. Current Trending remains a rolling discovery source, not an exact historical star snapshot.
- Trending has a 60-second overall budget. Generic workflow vocabulary requires a distinct AI/MCP signal before Agent classification.
- Latest and dated record reads honor digest type; the dashboard cancels stale loads when switching type.
- Dynamic image pages participate in attachment budgeting. STARTTLS is negotiated once, and partial recipient acceptance is detected.
- Public management routes require an administrator bearer key. The key is excluded from public build assets and stored privately.
- Pages now calls an HTTPS Worker origin backed by an encrypted Cloudflare Tunnel. The Tunnel is an independent systemd service; the backend remains in Docker Compose.
- Deployment dry-run does not back up or restart services. Deployment backups use SQLite's backup API and retain source, environment, and image identity. Environment backups and runtime data are ignored by Git.

## Automated and browser verification

- Backend: **430 passed**.
- Worker: **3 passed** with Node's test runner.
- Frontend TypeScript and production Vite build: passed.
- OpenSpec strict validation: passed.
- Isolated API generation: passed without changing seeded scheduled records.
- Isolated dashboard, arXiv view, history detail, and all three digest types: passed.
- Published browser test: daily, weekly, and monthly returned their matching record types; **zero failed API requests and zero page exceptions**.
- Pages deployment: [GitHub Actions run 40105546850](https://github.com/SenWeiV/daily_ai_digest/actions/runs/40105546850), completed successfully.

## Real email acceptance

A single uniquely identified test email used fresh source collection and model analysis in a temporary database inside the production runtime. The scheduled database and permanent feature switches were not used as test storage.

- Content date: `2026-10-23`.
- Selected content: **15 arXiv papers, 0 GitHub projects**. GitHub was not padded with out-of-window or lower-priority items.
- Six platform copy blocks: all passed validation and appeared in the received message.
- SMTP: accepted for both configured recipients.
- Readable 163 recipient mailbox: exactly **one** matching Message-ID.
- MIME: `multipart/mixed`, containing HTML and plain text alternatives.
- Received size: **98,386 bytes**; HTML: 31,008 characters; plain text: 17,295 characters.
- Attachments: **0**, matching the current permanent image switches, which remain disabled.
- Received HTML rendered in a real browser and was inspected.
- The company mailbox was not accessible for IMAP verification; SMTP acceptance and the correct To address are confirmed, but inbox receipt for that mailbox is not independently confirmed.

Raw reports, received HTML/EML, screenshots, and the administrator key are private artifacts and are not committed.

## Production checks

- Backend container: healthy.
- SQLite `PRAGMA quick_check`: `ok`; 278 existing records preserved, including 276 sent and two pending records.
- Unauthenticated generation request: rejected with HTTP 401.
- Authenticated no-op configuration update: HTTP 200; no schedule change.
- Next daily preparation: `2026-10-25 08:30 +08:00`; delivery: `09:00 +08:00`.
- Weekly: Sunday 20:30; monthly: last day 21:00, Asia/Shanghai.
- Render, image generation, and visual QA permanent switches: all false.
- Deployment backup: `/root/digest-backups/20261024-230748/`.
- Cloudflare Tunnel: healthy with four connections at verification.
- Public dashboard: `https://senweiv.github.io/daily_ai_digest/`.
- HTTPS API: `https://digest-api.vincentws.com/api`.

The next scheduled digest will exercise the corrected discovery window on the normal schedule. No exact 09:00 inbox-arrival guarantee is implied if upstream processing or SMTP delivery is delayed.
