## Why

The digest currently ends at an HTML email. Sharing any of it means reading the email, deciding what is worth posting, rewriting it for each platform's format, and rebuilding the visual by hand — every day, for six platforms with six different conventions.

Two constraints shape what can be automated. First, the server is in mainland China: `api.twitter.com`, `graph.facebook.com`, and `oauth.reddit.com` are not reachable without a VPN, so posting to X, Instagram, and Reddit cannot be automated from this deployment at all. Second, 小红书 has no official publish API and is actively banning automated posting, so even a reachable host would not make it safe. That leaves 微信公众号 and 知乎 as the only technically automatable targets, and 微信公众号 individual subscription accounts lost `freepublish` in 2025-07, so even there the ceiling is a draft.

Given that, automated posting is the wrong goal. What is actually useful is removing the manual production work: render the digest as an ultra-HD long image plus per-platform sized images in each platform's own visual style, generate copy in each platform's voice, verify every image is actually correct, and deliver all of it in one email so the choice of what to post stays with the reader.

Correctness of the images is the hard requirement, not a nice-to-have. A missing-glyph box where a Chinese character should be makes an image unusable, and it is exactly the failure that a text-only pipeline cannot see. So the images must be inspected by a vision model before they are allowed out, and an image that cannot be made correct must be withheld rather than shipped broken.

## What Changes

- Add an image renderer that turns the digest HTML into `digest-full.png`, an ultra-HD long image at 2× device pixel ratio, using headless Chromium. Long pages exceed Chromium's 16384px texture limit, so the render MUST be segmented and stitched rather than captured in one shot.
- Add five platform-sized images derived from the same digest data: `xhs-cover.png` and `xhs-content-1..3.png` at 1242×1656 (3:4), `x-card.png` at 1600×900, `ig-square.png` at 1080×1080.
- Add a declared per-platform style — tone, structure, palette, type scale, layout density — as inspectable data, and generate each platform's image prompt per run from that style plus the day's actual content.
- Add a `publishers` layer that generates per-platform copy for 小红书, 微信公众号, X, Instagram, 知乎, and Reddit, each respecting that platform's length limit, tone, and tag convention.
- **Add an automated visual QA gate.** Every rendered image is inspected by a vision model for missing glyphs, clipped or overflowing text, occlusion, and legibility. A failing image is regenerated with a correction targeting the reported defect and re-inspected, up to a bounded attempt count. An image that never passes is withheld from the email and named as withheld. A defective image is never delivered.
- **Split the LLM into three configured roles.** Text analysis and copy generation use DeepSeek V4 Flash; visual inspection uses Kimi K3 against the mainland-reachable `api.moonshot.cn` endpoint; optional background generation uses Seedream 5.0 Lite on Volcano Engine Ark. No role falls back to another. Text analysis stays cheap; the vision model is called only for the handful of images per run; generation is capped per run because it bills per output image.
- Use image generation for backgrounds and decoration only. Any text that must be accurate is composed by the template layer, never asked of a generation model — the only published Chinese-text-rendering figure for Seedream is a 94% per-character availability rate from the 3.0 paper, which is not good enough for a repository name.
- **All of it in one email.** The digest body, the per-platform copy section, and every passing image arrive in a single message. The send waits for the QA gate to finish. **BREAKING** for the email structure: `send_digest_email()` currently builds `MIMEMultipart("alternative")`, which cannot carry attachments; it must become a `mixed` container wrapping the existing `alternative` part.
- Add Chromium and CJK plus color-emoji fonts to `Dockerfile.backend`, and verify font resolvability at startup, since a missing font would make every image fail QA.
- Degrade rather than fail: the digest email is sent even when rendering, generation, copy, or inspection fails. What is never done is sending a broken image.

Non-goals: no publishing API calls, no platform credentials, no OAuth, no scheduled posting, no change to content discovery, selection, grading, or to which items appear in the digest.

## Capabilities

### New Capabilities

- `digest-image-rendering`: The ultra-HD long image and the five platform-sized images — dimensions, the segmented-capture rule that keeps each screenshot under Chromium's texture limit, font requirements for Chinese text and emoji, a total attachment size budget, and the requirement that a render failure never blocks the email.
- `visual-qa-gate`: The automated inspection every image must pass before delivery, the defect categories checked, the bounded regenerate-and-re-inspect cycle with corrections targeting the reported defect, the rule that a persistently failing image is withheld and named rather than shipped, startup font-coverage verification, and structured auditable verdicts where an unparseable verdict counts as a failure.
- `multimodal-model-roles`: The three independently configured model roles, their defaults, the prohibition on cross-role fallback, the mainland-reachable endpoint requirement for the vision and generation roles, the base64-or-file-reference constraint on image submission, request-size handling that downscales only the inspection copy and never below a detectability floor, the pinned-identifier and per-run cap rules for per-image-billed generation, and per-role cost logging.
- `platform-style-design`: The declared per-platform visual and editorial styles, per-run prompt construction from style plus content, the rule that accurate text is composed by the template rather than generated, generated imagery restricted to background and decoration with quiet regions reserved for composited text, the minimum generation resolution and prohibition on upscaling, consistent-series generation for multi-page sets, a watermark setting defaulting to disabled and sent explicitly on every request, immediate download of expiring provider URLs, and the grounding rule extended to generation prompts.
- `platform-publishing-copy`: Per-platform copy generation for the six platforms, each platform's format constraints, the requirement that copy is derived only from already-analyzed digest items, and the requirement that generated copy never fabricates an item, number, or link absent from the digest.
- `digest-email-packaging`: The single-email requirement including the rule that the send waits for the QA gate, the MIME structure change that allows attachments, the placement of the per-platform section after the main content, and the degradation path when rendering, copy, or inspection fails.

### Modified Capabilities

None. Discovery, selection, and grading are untouched.

## Impact

- Backend: new `app/services/image_renderer.py`, new `app/services/visual_qa.py`, new `app/publishers/` package, new per-platform style definitions and templates, `app/services/email_service.py` (MIME structure, per-platform section, attachments), `app/services/digest_service.py` (render → inspect → correct → send sequencing between save and send).
- Configuration: three model roles, each with model, base URL, and credential. Rendering, generation, and inspection each independently disable-able. Maximum QA attempts, maximum inspection request body size, minimum inspection resolution floor, per-run generated-image cap, attachment size budget, retention window.
- Build: `Dockerfile.backend` gains Chromium, `fonts-noto-cjk`, and `fonts-noto-color-emoji`. Image size grows substantially — Chromium alone is several hundred MB. This is the largest practical cost of the change and needs measuring, not estimating.
- Runtime: `--disable-dev-shm-usage` is required, since the container's default `/dev/shm` is too small for Chromium and the symptom is an opaque crash rather than a clear error.
- **Wall-clock duration grows materially.** The QA cycle adds a vision call per image per attempt, and the vision model always reasons. The user has accepted slower runs in exchange for correctness, so no timeout may be tightened to compensate.
- Cost: text analysis stays on the cheap model and scales with item count. Vision calls scale with image count times attempts — roughly 6 to 8 per run at best, more with retries. Generation bills ¥0.22 per output image and is capped per run. Per-role logging exists so the real figure is measured rather than assumed.
- Storage: rendered PNGs and any generated backgrounds are written under the existing `./data` volume, with a retention rule.
- Email size: seven images at 2× DPR can exceed common attachment limits, so the change needs an explicit size budget with a documented drop order.
- Tests: segmentation and stitching, exact platform aspect ratios, QA pass and fail paths, corrective regeneration, withholding after exhausted attempts, unparseable verdict treated as failure, role separation, base64 submission, single-email structure, and grounding validation for both copy and generation prompts.
