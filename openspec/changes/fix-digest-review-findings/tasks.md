## 1. Delivery correctness
- [x] 1.1 Add and migrate durable delivery status; reset stale state on regeneration.
- [x] 1.2 Detect partial SMTP acceptance, report failed delivery, and guard uncertain retries.
- [x] 1.3 Add regression coverage for sent, failed, partial, uncertain, and forced runs.

## 2. Discovery and navigation
- [x] 2.1 Propagate timezone-aware periods to arXiv and GitHub discovery.
- [x] 2.2 Bound total Trending latency and tighten generic Agent matches.
- [x] 2.3 Make latest and dated APIs and the dashboard honor digest type.
- [x] 2.4 Cover date boundaries, source queries, type isolation, and false positives.

## 3. Acceptance and rollout
- [x] 3.1 Add isolated real-email acceptance and exact-message IMAP verification.
- [x] 3.2 Pass backend regressions, frontend build, OpenSpec validation, and isolated API/UI verification.
- [x] 3.3 Back up and deploy; verify health and unchanged delivery schedule.
- [x] 3.4 Send one real email to configured recipients and inspect the readable recipient mailbox.
- [x] 3.5 Push reviewed code, align server Git metadata, and record final evidence and any domain-dependent limitation.
