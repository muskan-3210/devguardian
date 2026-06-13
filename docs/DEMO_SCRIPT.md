# DevGuardian — Demo Scripts

> Pre-demo checklist: `python -m app.seeder` run, server up, dashboard open on the **Trust Overview** tab, DNA ingested (DNA tab → "Learn DNA from history"), one dry run completed. Record a 1080p backup video in advance.

---

## 5-minute script

**[0:00] Hook (30 s)**
> "Every team here built an AI that reviews code. We built an AI that knows your *developers*. DevGuardian doesn't review every PR the same way — it learns who ships clean code and who introduces auth bugs, and adapts its scrutiny automatically."

**[0:30] Trust Overview (60 s)**
- Point at the four developer cards: Muskan 80 (shallow), Sam 0 (block).
- Click Muskan's card → show the **explainable breakdown** — "no black boxes; every point is traceable to a signal from the DevOps APIs."
- Point at the trend chart: "scores are recalculated weekly — this is a *stateful* system that improves for months."

**[1:30] The money shot — buggy PR from a low-trust dev (90 s)**
- Live PR Review tab → persona **Yogesh (deep)**, scenario **Buggy PR** → Submit.
- Walk the result: "Deep review fired automatically. SQL injection, hardcoded secret, TLS disabled — each with the exact file and line, severity, and a suggested fix. And look: it *generated the missing tests* for the untested functions."
- Show DNA violations: "this isn't lint — camelCase flagged because **95% of this team's code is snake_case**. That's the Codebase DNA fingerprint."

**[3:00] Same PR, trusted dev (30 s)**
- Persona **Muskan**, scenario **Clean PR** → Submit.
- "Shallow scan, approved in milliseconds. High-trust developers get speed; low-trust code gets protection. That's adaptive review."

**[3:30] Block + Gate (45 s)**
- Persona **Sam Iqbal**, Buggy PR → Submit. "DTS 0 — no AI call at all. Merge blocked, team lead alerted."
- Team Intelligence tab → Evaluate release → **RED gate**: "one untrusted author plus unresolved criticals — this release would never reach production."

**[4:15] Close (45 s)**
> "Zero cost — NVIDIA NIM free tier, ChromaDB, Semgrep OSS, SQLite. Plugs into Azure DevOps or GitHub with one webhook. Copilot writes the code; DevGuardian guards what was written."

---

## 10-minute script (additions)

1. **(+1 min) Weekly Team Risk Intelligence** — Generate report: anonymised cohort insight ("low-trust engineers who joined in the last 6 months → schedule security onboarding"). Stress the ethics: individuals are never named, DTS is never shown to managers.
2. **(+1.5 min) Live GitHub round-trip** *(only if keys + ngrok configured)* — open a real PR from the low-trust GitHub account; show inline comments appearing in GitHub and the Discord alert firing within ~45 s.
3. **(+1 min) Architecture slide** — 3 layers (webhook → trust-routed AI orchestration → action engine); model routing table; 429 fallback chain.
4. **(+1 min) Engineering quality** — 28 passing tests, HMAC-verified webhooks, audit log, Docker one-command deploy, CI that Semgrep-scans DevGuardian itself.
5. **(+0.5 min) Business value** — PRs wait 2–3 days for human review; DevGuardian gives feedback in seconds and blocks risky releases before they threaten the SLA.

---

## Demo personas cheat-sheet

| Persona | DTS | Depth | Use to show |
|---|---|---|---|
| Muskan | 80 | shallow | speed for trusted devs |
| Alex Rivera | 65 | standard | the default path |
| Yogesh | 36 | deep | full audit + test generation |
| Sam Iqbal | 0 | block | hard gate + alert |
