# Implementation Tasks

## 1. Prerequisite

- [x] 1.1 Land `switch-llm-to-deepseek-v4` first. The text role depends on it, and `kimi-k2.5` — what production runs today — sunsets 2026-08-31, so the text model has to move this month regardless.

## 2. Model roles and configuration

- [x] 2.1 Add a text analysis role and a visual inspection role to `backend/app/config.py`, each with its own model identifier, base URL, and credential setting. Default the text role to DeepSeek V4 Flash and the visual role to `kimi-k3`.
- [x] 2.2 Default the visual role base URL to the mainland Kimi endpoint `https://api.moonshot.cn/v1`. Measured from a Beijing IP: that host answered 10/10 at ~0.1s while `api.moonshot.ai` answered 6/10 with four timeouts.
- [x] 2.3 Add a comment in `backend/.env.example` and `.env.example.docker` stating that the `.cn` and `.ai` Kimi endpoints are separate platforms with separate accounts, credentials, and currencies. Neither provider doc mentions the other, so this is a trap for whoever next edits the server `.env`.
- [x] 2.4 Add settings for maximum QA attempts (default 3), maximum inspection request body size, minimum inspection resolution floor, attachment size budget, retention window, the generation watermark switch (default **disabled**), and independent enable switches for rendering, generation, and inspection.
- [x] 2.5 Update `docker-compose.yml` to pass every new setting through with matching defaults.
- [x] 2.6 Add tests: both roles resolve independently; the visual role default host is the `.cn` endpoint; no code path sends an image to the text model; no code path sends text analysis to the visual model.
- [x] 2.7 Add per-role call counting and log the counts at the end of each run. Vision-role count must track images times attempts, not item count.

## 3. Container image and font verification

- [x] 3.1 Add Chromium and its runtime libraries, `fonts-noto-cjk`, and `fonts-noto-color-emoji` to `Dockerfile.backend`. Use `fonts-noto-color-emoji` specifically — it is CBDT bitmap, which Chromium renders; SVG-based emoji fonts do not.
- [x] 3.2 Record the current image size, build the new image, and record the new size. Report the increase as a measured number, not an estimate. **Measured on the server, 2026-08-01.** Baseline `daily_ai_digest-backend:2f74a32` = **1.09GB**. New `:latest` (`8e6284128c21`) = **2.76GB** — an increase of **1.67GB (+153%)**. Per-layer attribution from `docker history`: Chromium download **904MB**, apt (fonts + Chromium runtime libs + gcc) **384MB**, pip **626MB** (of which Playwright's bundled Node driver is the bulk), application code 1.38MB. Server disk went 27G → 31G used, 7.0G free of 40G. **Two findings that changed the Dockerfile, both of which made the previous build unusable rather than merely slow:** (a) the container inherits neither `/etc/pip.conf` nor an apt mirror from the host — on public sources `pip` could not resolve `google-auth>=2.15.0` at all (`from versions: none`, hard build failure) and the apt layer took **8296 seconds**; switching both to `mirrors.baidubce.com` took apt to **37.9s** and pip to **25.4s**. (b) `playwright install --with-deps` cannot work on Debian 13 — it falls back to ubuntu20.04 package names, fails to locate 9 packages, prints `Failed to install browser dependencies`, and **exits 0**, so the build succeeds and the missing libraries only surface at `chromium.launch()`. Runtime libraries are now listed explicitly from trixie's own `chromium` dependencies. Verified with `ldd` inside the built image: both `chrome` and `headless_shell` report no missing shared objects.
- [x] 3.3 Implement the startup font check: verify a Simplified Chinese font and a color emoji font are resolvable by the rendering engine, log the resolved family names, and refuse to render if either is absent. Without this, a missing font makes every image fail every retry to discover one fact.
- [x] 3.4 Implement per-character fallback so a character outside the primary font's coverage still renders as a glyph.
- [x] 3.5 Verify inside the built container that the browser launches with shared-memory usage disabled and that a Chinese-plus-emoji test page renders with no missing-glyph boxes. Local darwin success does not count as verification. **Verified in the built image, 2026-08-01** — the first time any code in the render path has actually executed. `tests/manual/probe_render.py` launches Chromium with `--disable-dev-shm-usage --no-sandbox --font-render-hinting=none` through the production `font_stack()`, renders `中文渲染测试深度求索 🎉🚀✅` at `device_scale_factor=2`, and judges the resulting pixels on three independent criteria: every character must carry ink; no two characters may produce a pixel-identical crop (a tofu box's shape is independent of the character, so missing-glyph runs collapse to one fingerprint — a more reliable signature than contour detection); and emoji crops must contain saturated colour (`fonts-noto-color-emoji` is CBDT bitmap; falling through to a monochrome family shows up as zero saturated pixels). Result: 13 characters, 13 distinct fingerprints, emoji at 8483–16156 coloured pixels, **no tofu**. **This probe also caught a real defect that every existing defence would have passed:** `fonts-noto-cjk` registers **15** families matching `:lang=zh-cn` (SC/TC/HK/JP/KR × Sans/Serif/Mono) and the check took `fc-list`'s first three, which in the container are `Noto Serif CJK JP / KR / HK` — Simplified Chinese body text rendering with Japanese glyph variants. Tofu detection passes it (every character has a glyph) and the vision gate would most likely pass it too; the defect reads only as "the characters look slightly off". Confirmed as a real difference by rendering 直/骨/込 from the same `.ttc` at two face indices and comparing pixel hashes. Fixed by ranking CJK families (SC → TC/HK → JP/KR; Sans over Serif; Mono last) in `FontReport.__post_init__` — placed there rather than in `inspect_fonts()` or `font_stack()` because both read `cjk_families`, one for the log line and one for what the browser actually uses, and ordering in only one produces a divergence where the log claims SC while the browser uses JP. Post-fix, the container resolves `Noto Sans CJK SC` first. 5 tests added, one of which feeds the real observed `fc-list` order.

- [x] 3.6 Add a test asserting the startup check fails loudly when the CJK font is absent, and that rendering is not attempted in that state.

## 4. Renderer

- [x] 4.1 Add `backend/app/services/image_renderer.py` that loads the digest HTML, measures full page height, and captures at the configured device pixel ratio with a default of 2.
- [x] 4.2 Implement segmented capture: when page height at scale exceeds the configured safe segment height, capture sequential non-overlapping segments and stitch them vertically with Pillow. Chromium's 16384px texture limit truncates silently, so this is not optional for a 24-item digest at 2× DPR.
- [x] 4.3 Add a test asserting the stitched output height equals full page height at scale, using a page tall enough to require at least three segments. This assertion catches offset bugs, which otherwise appear as seams or dropped bands.
- [x] 4.4 Add a test asserting a page below the safe segment height is captured in a single screenshot with no stitching.
- [x] 4.5 Add a test asserting two renders of the same stored digest produce identical pixel dimensions.
- [x] 4.6 Fix the two `<span>??</span>` mojibake spots at `backend/app/services/email_service.py:196` and `:210`. They predate this change but rendering to an image makes them conspicuous.

## 5. Platform styles and templates

- [x] 5.1 Define the per-platform style as structured, inspectable data — tone, structure, title convention, tag convention, palette, type scale, layout density — for all six platforms. Not embedded inside prompt literals.
- [x] 5.2 Add templates for `xhs-cover.png` and `xhs-content-1..3.png` at 1242×1656 logical, laid out from digest data rather than cropped from the long image. Cropping a 3:4 frame out of a long vertical render gives an arbitrary slice with text cut at both edges.
- [x] 5.3 Add templates for `x-card.png` at 1600×900 and `ig-square.png` at 1080×1080.
- [x] 5.4 Preserve complete text when a frame is tight; use wrapping, dynamic pagination, content-density reduction, or type-scale reduction rather than ellipsis truncation.
- [x] 5.5 Implement the item-count rules: more items than the three content pages hold, carry the highest-ranked in digest order; fewer items than the pages would fill, omit the unused pages rather than emitting them blank.
- [x] 5.6 Ensure a multi-page set shares palette, type scale, and layout system so the four 小红书 images read as one post.
- [x] 5.7 Add tests asserting each platform image's aspect ratio is exact and that stored dimensions equal logical dimensions times the configured DPR.
- [x] 5.8 Add a test asserting each platform's copy and images draw from the same items in the same order.

## 6. Image generation (optional layer)

- [x] 6.1 Add the generation role to configuration: model `doubao-seedream-5-0-260128` (the 组图-capable Lite model), endpoint `https://ark.cn-beijing.volces.com/api/v3`, `Authorization: Bearer` credential, plus a per-run cap on generated images. Pin the dated identifier; do not use a rolling alias.
- [x] 6.2 **Closed live, 2026-08-01, from the server itself.** `POST https://ark.cn-beijing.volces.com/api/v3/images/generations` with the real `IMAGE_GEN_API_KEY` accepted `doubao-seedream-5-0-260128` and returned HTTP 200 with a `2048x2048` JPEG URL, `usage.generated_images: 1`. `sequential_image_generation: "auto"` with `max_images: 2` also returned 200 from the local probe. The URL carries `X-Tos-Expires=86400`, confirming first-hand the 24-hour expiry that task 6.6 exists to defend against. `doubao-seedream-5-0-pro-260628` was **not** substituted at any point — it cannot do 组图.
- [x] 6.3 Add a watermark setting that **defaults to disabled**, and send its value explicitly on every request. The provider default is `true` and stamps "AI生成" into the bottom-right corner, so any request that omits the field ships a watermark. Defaulting our own setting to `false` means the watermark can only appear if an operator deliberately turns it on.
- [x] 6.4 Request generation at a resolution tier at or above the composited frame size at 2× DPR, then downscale locally. 5.0 Lite enforces a **minimum** total-pixel floor of 3,686,400, and all three logical frame sizes are below it — 1242×1656 is 2.06M, 1600×900 is 1.44M, 1080×1080 is 1.17M — so requesting the logical size is rejected outright. Select the smallest tier clearing both the floor and the frame's 2× dimensions.
- [x] 6.5 Never upscale a generated image to fill a frame. If no available tier reaches the frame's rendered size, use the fallback background — upscaling softness is indistinguishable from a rendering defect.
- [x] 6.6 Download every generated image to local storage during the run and record the local path. Provider URLs expire after 24 hours, so a stored URL points at nothing by the next day.
- [x] 6.7 Implement per-run image prompt construction from the platform's declared style plus the day's actual content. Prompts must differ across days and across platforms.
- [x] 6.8 Restrict generation to background and decoration. Every project name, figure, and link MUST be composed by the template layer — the only published Chinese-text-rendering figure for Seedream is 94% availability from the 3.0 paper, no metric exists for 5.0, and ByteDance's own launch post concedes weakness at fine text sizes. 94% per character is unacceptable for a repository name.
- [x] 6.9 Instruct the prompt to keep regions reserved for composited text visually quiet, so a busy background does not fail the legibility check and burn a retry.
- [x] 6.10 Use `sequential_image_generation: "auto"` with `max_images` for the 小红书 set so the four backgrounds are a consistent series rather than four unrelated images.
- [x] 6.11 Implement the non-generated fallback background and use it when generation is disabled, fails, times out, exceeds the per-run cap, or when the configured model lacks 组图 support for a multi-page platform.
- [x] 6.12 Apply the grounding rule to generation prompts: no subject absent from the digest, and no recognisable third-party logo or brand identity.
- [x] 6.13 Add tests: prompts differ across two days' digests; prompts differ across platforms; the watermark setting defaults to disabled and every request carries the field explicitly; a requested resolution always clears the provider's pixel floor; upscaling is never used; a disabled or failing generator still yields an inspected image on the fallback background; the per-run cap forces fallback rather than more generation; a prompt never names a subject absent from the digest.

## 7. Visual QA gate

- [x] 7.1 Add `backend/app/services/visual_qa.py` that submits a rendered image to the visual role and returns a structured verdict: pass or fail, failing categories, and a short location description per defect.
- [x] 7.2 Submit images as base64 data URLs or provider file references, never as public HTTP URLs — K3 rejects remote URLs. Build `content` as a genuine typed parts array, not a serialized string.
- [x] 7.3 Implement the defect checks: missing-glyph boxes, text clipped at a frame edge, text overflowing its container, overlapping or occluded text, body-text legibility at intended viewing size, and every supplied text field actually present.
- [x] 7.4 Enforce the request body size limit by downscaling only the inspection copy. The delivered image keeps full resolution.
- [x] 7.5 Enforce the minimum inspection resolution floor. An image too large to inspect above the floor MUST be inspected in segments rather than downscaled below it — an inspection that cannot read the text reports a false pass, which is the worst outcome in this design.
- [x] 7.6 Implement the bounded regenerate-and-re-inspect cycle. Each retry MUST change the parameter targeting the reported defect: font-coverage failure applies a fallback font, overflow or clipping applies a smaller type scale or lower page density without dropping text. A retry identical to the failed attempt is a bug.
- [x] 7.7 Treat an unparseable verdict as a failure. Never as a pass.
- [x] 7.8 When attempts are exhausted, withhold the image from the email and record which image and which defect category. Never attach a placeholder or a lower-quality substitute in its place.
- [x] 7.9 When the visual model is unreachable, mark no image as passing and send the email without the unverified images rather than with them. No fallback to the text model — a text model handed an image either errors or fabricates a verdict, and a fabricated pass ships the exact defect the gate exists to catch.
- [x] 7.10 Log every verdict for every attempt of every image so a recurring defect is diagnosable from logs without re-running the pipeline.
- [x] 7.11 Add tests: a clean image passes; a tofu image fails; a clipped-text image fails; a failing image regenerates with a changed parameter and passes on retry; exhausted attempts withhold and name the image; an unparseable verdict counts as a failure; vision unavailable marks nothing as passing.
- [x] 7.12 Test the gate against deliberately broken inputs — a font removed from the container, a title long enough to overflow. A gate that has never caught a real defect has not been tested.

## 8. Publishers and copy generation

- [x] 8.1 Add `backend/app/publishers/` with a shared copy-generation call on the text role that receives the selected, already-analyzed digest items and returns copy for all six platforms in one call.
- [x] 8.2 Implement each platform's format constraints: X at or under 280 characters per post or thread part; 小红书 title at or under 20 characters, body at or under 1000, 3 to 10 hashtags; Instagram caption at or under 2200 with trailing hashtags; 微信公众号 title at or under 64 characters with a heading-structured body; 知乎 long-form with no hashtags; Reddit English Markdown with no hashtags.
- [x] 8.3 Confirm how X counts CJK characters — CJK counts as two toward the 280 limit — and implement the counting to match rather than using string length. Getting this wrong produces copy that passes validation and is rejected at post time.
- [x] 8.4 Implement grounding validation: extract every URL from generated copy and assert membership in the digest's link set; check every quoted star count or benchmark figure against the stored item value. Ungrounded copy MUST fail that platform rather than being silently edited.
- [x] 8.5 Implement over-limit handling: truncate or regenerate so delivered copy is within its platform's limit.
- [x] 8.6 Add per-platform enable/disable configuration. A disabled platform produces no copy and MUST NOT be reported as a failure.
- [x] 8.7 Add tests: each platform's limit is enforced; a fabricated URL fails validation; a fabricated star count fails validation; 小红书 tag count is within range; Reddit output is English with no hashtags; two platforms' copy differ in structure and length.

## 9. Single-email packaging

- [x] 9.1 Restructure `send_digest_email()` so a `mixed` container wraps the existing plain-and-HTML `alternative` part, with attachments as siblings of that part. The current `alternative`-only structure cannot carry attachments without the images displacing the body.
- [x] 9.2 Sequence the send after the QA gate completes for every image. Exactly one email carries the digest body, the copy section, and every passing image — no split delivery, no follow-up message for late assets.
- [x] 9.3 Attach images with date-stamped, purpose-identifying filenames so successive days do not collide.
- [x] 9.4 Implement the attachment size budget: keep the long image first, then drop platform images in a fixed documented order until the total fits. Record the drop order in the configuration comments.
- [x] 9.5 Add the per-platform copy section after the existing digest sections, each platform a labelled block with selectable plain-text copy naming its associated attachment filename.
- [x] 9.6 Name in the email any platform whose copy failed and any image that was withheld, with its defect category. Silent omission leaves the reader unable to tell a missing asset from an unproduced one.
- [x] 9.7 Add tests: both body parts sit inside an alternative container nested in a mixed container; a message with no attachments is still valid; existing GitHub, arXiv, and YouTube section markup is unchanged; the copy section appears after the main sections; exactly one message is sent per digest.

## 10. Degradation and retention

- [x] 10.1 Default rendering to off for the initial deploy so landing this change cannot break the daily email before the render path is proven in the container.
- [x] 10.2 Wrap rendering, generation, inspection, copy generation, and attachment so each fails independently. Any failure logs and MUST NOT prevent the email.
- [x] 10.3 Implement retention cleanup for rendered images and generated backgrounds older than the configured window, guarded so the current run's files are never deleted.
- [x] 10.4 Add tests: browser launch failure still sends the email; one platform image withheld still sends the others; rendering, generation, and copy all failing sends exactly the current email content; retention does not delete the current run.

## 11. Verification and rollout

- [x] 11.1 Run the backend test suite and a Python compile check.
- [x] 11.2 Rendered a real stored digest inside the built container; font self-check passed, the 7,000+ px long image was segmented into two pages, and the long-image visual QA passed.
- [ ] 11.3 **Blocked locally — needs a live vision credential plus a working browser in the container.** Run the full render → inspect → correct → pass cycle on a real digest. Record attempts per image and total vision calls.
- [x] 11.4 Ran a real text-role copy-only probe; all six platforms were accepted, no omission markers were present, and X produced 12 ordered thread parts.
- [ ] 11.5 **Blocked locally — needs live SMTP credentials.** Send one test email to the operator's own address. Confirm in the actual mail client that the HTML body renders as the body and attachments appear as attachments. Record total attachment size against the provider's limit — this sets the budget default.
- [x] 11.6 On the server: recorded the current image reference, backed up `/opt/daily_ai_digest/data/digest.db`, deployed with rendering disabled, and confirmed the resident service remained healthy.
- [ ] 11.7 Enable rendering and inspection, restart, and watch the first scheduled run. Record per-role call counts, retry counts, and wall-clock duration. If rendering fails, disable it in configuration and restart rather than rolling back — the email keeps working and the failure stays diagnosable.
- [ ] 11.8 Report measured cost per run broken down by role, against the pre-change baseline. Text calls scale with item count; vision calls scale with images times attempts.

## Notes

Task 7.12 is the task that decides whether this change delivered its point. Every other test proves the pipeline runs; only that one proves the gate catches what it exists to catch. A QA gate that has only ever seen correct images is untested.

Task 7.5's resolution floor is the subtlest correctness requirement here. Downscaling to fit a body limit is the obvious fix for an oversized request, and taken far enough it produces an inspection that cannot read the text and therefore reports a pass. A false pass ships the defect. Segmenting is slower and correct.

Task 7.9 exists because "fall back to the other model" is the reflex when a provider is down, and here it is actively harmful: a text model handed an image can fabricate a plausible pass verdict, which is worse than having no verdict.

Task 3.3's startup font check is cheap and removes the most likely systematic defect class. Without it, a missing font is discovered by exhausting the retry budget on every image — paying a full run of vision calls to learn one fact.

Task 10.1's default-off matters because three independent failure domains — browser, generation, vision — now sit between a working digest and a sent email. The digest arriving daily matters more than the images.

Kimi K3's vision numbers are all vendor-reported: OmniDocBench 91.1 is the best of the five models compared, and OmniDocBench balances Chinese and English pages, but there are no OCRBench, DocVQA, ChartQA, or CCBench figures for K3 and no independent third-party vision evaluation exists. The gate is a strong improvement over no gate; it is not a proof of correctness.

Doubao Seed 2.1 Pro (`doubao-seed-2-1-pro-260628`, OCRBench v2 63.2, ¥6/¥30 per M) is the documented alternative for the inspection role and would collapse three provider accounts into two, since Ark hosts both Seed and Seedream. It also accepts public image URLs, which K3 does not. K3 was chosen on request shape — its 1M context and 100 MB body limit mean fewer segments for the long image, and segment count is what drives inspection cost. Switching is a configuration change, which is why the roles are independently configurable.

Task 6.4's pixel floor is the non-obvious provider constraint in this change. Every target frame size is *below* Seedream 5.0 Lite's minimum, so the intuitive request — ask for the size you want — fails outright. Generate above the floor and downscale.
