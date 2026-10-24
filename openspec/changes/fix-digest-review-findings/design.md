## Context

The live service sends a previous-day digest at 09:00 Asia/Shanghai. Existing rows and SMTP results are insufficient to distinguish successful, failed, and uncertain delivery. Discovery uses current feeds, and the dashboard ignores its selected period when loading.

## Goals / Non-Goals

**Goals:** Correct observable delivery outcomes; prevent accidental duplicate retries; constrain discovery to the requested period; fix period navigation; prove one real email arrived.

**Non-Goals:** Enable image generation permanently or change recipients or schedule. The connected Cloudflare account has an active owned domain; a dedicated Worker supplies the HTTPS browser entry point while the backend remains on the existing server.

## Decisions

- Add a backward-compatible delivery status alongside the existing boolean. Mark `sending` before SMTP. Known pre-DATA failures can be retried with the saved content. Partial acceptance, timeouts, or disconnects require operator confirmation before a forced resend.
- Use UTC half-open windows derived from the configured business timezone. arXiv queries use submission dates and validate returned timestamps. GitHub search and enrichment use latest push activity; current Trending is a discovery aid, not a historical star snapshot.
- Bound the entire Trending attempt loop, not just socket reads. Require a distinct AI/MCP signal when matching generic Agent vocabulary.
- Keep read APIs backward compatible while adding a validated digest-type query. Abort stale dashboard requests when switching period.
- Exercise actual source collection and SMTP in an isolated database. Identify the test with a unique subject and Message-ID; inspect that exact received message using IMAP PEEK.
- Attach `digest-api.vincentws.com` to a small fixed-origin Worker. Preserve existing origin behavior and CORS, disable caching, and use HTTPS in the Pages build. The fixed HTTPS origin is routed through an encrypted managed Tunnel to the backend loopback address.

## Risks / Trade-offs

- Historical GitHub search indexes latest push time, not every historical commit → document the activity-window meaning and do not claim exact prior-day star counts.
- arXiv submissions can become visible after moderation delays → empty windows stay empty rather than importing another day's papers.
- SMTP may accept DATA before the connection fails → persist an uncertain state and require explicit resend rather than automatic retry.
- Legacy rows have no delivery state → migrate sent rows to `sent` and unsent rows to `pending`.

## Migration Plan

Back up SQLite, environment, source, and image identity. Add the nullable-compatible status column at startup, deploy with existing dependency layers, verify schedules and health, and send the isolated acceptance email. Rollback can restore the prior image/source; the additive column is compatible with the previous release.

- Public management endpoints require a separately configured administrator key; the browser supplies it only for mutations, never via compiled assets. Scheduled jobs use the internal service directly.
