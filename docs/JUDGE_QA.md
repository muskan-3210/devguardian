# DevGuardian — Judge Q&A Preparation

**Q: Isn't a trust score just surveillance of developers?**
A: No — three deliberate guardrails. (1) DTS is consumed *only* by the review pipeline; there is no manager-facing view and no export. (2) Every score is fully explainable — five public signals with published weights. (3) Team reports are anonymised at source. The score changes *how much protection* a PR gets, never anyone's performance review.

**Q: What happens to new developers with no history?**
A: They get the neutral baseline of 70 → standard review. New people are neither trusted nor punished, and they build history within their first few PRs.

**Q: Can a developer game the score?**
A: The signals are outcomes, not activity: bugs *linked to merged PRs after merge*, reverts of *their* commits, coverage delta, post-merge security findings, and first-pass acceptance. Gaming all five simultaneously is just… being a good engineer.

**Q: Why is this better than GitHub Copilot code review / generic AI reviewers?**
A: Two things they don't have. (1) **State**: generic reviewers treat PR #1 and PR #500 from the same author identically; we route depth by learned trust, so review cost goes where risk is. (2) **Context**: the DNA fingerprint compares code to *your* repository's history, not Stack Overflow conventions — it flags "this violates *your* standards."

**Q: How does the DNA fingerprint actually work?**
A: Merged history is chunked at function level and embedded (`nv-embedqa-e5-v5`) into ChromaDB; new PR chunks whose nearest neighbours fall below 0.62 cosine similarity are "foreign DNA". In parallel we extract measurable traits (snake_case ratio, type hints, docstrings, logging vs print, exception style) so every violation has a human-readable reason, not just a similarity number.

**Q: What if NVIDIA NIM is down or rate-limited?**
A: Three layers: retry with backoff, fallback chain to `nvidia/nemotron-super-49b-instruct`, and if everything is unreachable the deterministic offline engine (pattern-based scanner + built-in OWASP rules) still produces findings — the gate never fails open silently.

**Q: False positives — what if the AI blocks good code?**
A: Blocking is never an AI decision. Only DTS < 20 blocks, and that threshold is reached through months of measurable history. AI findings post as review comments a human can dismiss; the deploy gate reasons are listed explicitly so a lead can override consciously.

**Q: How does this scale beyond a demo team?**
A: The pipeline is stateless per-request; SQLite/WAL handles a team comfortably and the storage layer is a thin module — swapping to PostgreSQL is a connection-string change in one file. ChromaDB scales to millions of chunks locally. Review concurrency is bounded by NIM rate limits, which is a paid-tier knob, not an architecture change.

**Q: What was actually hard to build?**
A: Calibrating the trust formula (the published weights cap the max score at ~80, so band boundaries matter), reconstructing per-file content from unified diffs so Semgrep only scans *added* lines, and making every integration degrade to a mock so the demo can never be killed by wifi.

**Q: Security of DevGuardian itself?**
A: HMAC-SHA256 webhook verification with constant-time compare, secrets only via environment, parameterised SQL throughout, an audit log of every automated action, and our own CI runs Semgrep against this repo on every push — the guardian guards itself.

**Q: Business value for Microsoft?**
A: Azure DevOps has 10M+ users waiting 2–3 days per human review. Every shallow-routed PR returns engineering hours; every deep-routed PR catches what tired humans miss; the deploy gate protects the 99.9% Azure SLA. It complements Copilot: Copilot writes, DevGuardian guards.

**Q: Total cost?**
A: ₹0. NVIDIA NIM free tier, ChromaDB, Semgrep OSS, SQLite, FastAPI, Discord webhooks, GitHub free tier, Railway free tier. No credit card anywhere.
