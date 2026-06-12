# DevGuardian — Architecture

## 1. High-level architecture

```mermaid
flowchart LR
    subgraph SCM["Source control (free tier)"]
        GH[GitHub / Azure DevOps]
    end
    subgraph Core["DevGuardian core (FastAPI, single deploy)"]
        WH[/POST /webhook/]
        DTS[Module 1<br/>DTS Engine]
        ORCH[AI Review<br/>Orchestrator]
        DNA[Module 2<br/>DNA Fingerprint]
        SEC[Module 3<br/>Security Scanner]
        TG[Module 4<br/>Test Generator]
        RR[Module 5<br/>Risk Reporter]
        DG[Module 6<br/>Deploy Gate]
        DASH[SPA Dashboard]
    end
    subgraph Storage
        SQL[(SQLite<br/>trust · reviews · findings · audit)]
        CH[(ChromaDB<br/>code embeddings)]
    end
    subgraph External["Free external services"]
        NIM[NVIDIA NIM<br/>Llama 4 · Devstral · Qwen3 · EmbedQA]
        DISC[Discord/Teams webhook]
    end

    GH -->|PR event| WH --> DTS --> ORCH
    ORCH <--> NIM
    ORCH --> DNA <--> CH
    DNA <-->|embeddings| NIM
    ORCH --> SEC --> NIM
    ORCH --> TG --> NIM
    DTS <--> SQL
    ORCH --> SQL
    RR --> SQL & NIM & DISC
    DG --> SQL & DISC
    ORCH -->|inline comments + status| GH
    ORCH -->|HIGH risk| DISC
    DASH --> SQL
```

## 2. PR review sequence

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant GH as GitHub
    participant DG as DevGuardian (FastAPI)
    participant SQ as SQLite
    participant NIM as NVIDIA NIM
    participant CB as ChromaDB
    participant DC as Discord

    Dev->>GH: open pull request
    GH->>DG: webhook (HMAC-signed payload)
    DG->>DG: verify X-Hub-Signature-256
    DG->>GH: fetch unified diff
    DG->>SQ: lookup author DTS
    alt DTS 0–19 (block)
        DG->>GH: commit status = failure
        DG->>DC: 🚫 blocked-PR alert
    else DTS ≥ 20
        DG->>NIM: depth-routed review (Llama4/Devstral/Qwen3)
        DG->>CB: DNA similarity query (standard/deep)
        DG->>DG: Semgrep / built-in OWASP scan (deep)
        DG->>NIM: generate missing tests (deep)
        DG->>GH: inline review comments + commit status
        DG->>SQ: persist review, findings, risk assessment
        opt HIGH/CRITICAL found
            DG->>DC: ⚠️ high-risk alert
        end
    end
```

## 3. Entity-relationship diagram

```mermaid
erDiagram
    developers ||--o{ developer_metrics : "weekly window"
    developers ||--o{ trust_scores : "DTS history"
    developers ||--o{ pull_requests : authors
    developers ||--o{ security_findings : introduced
    pull_requests ||--o{ reviews : "AI reviews"
    pull_requests ||--o{ security_findings : contains
    pull_requests ||--o{ risk_assessments : classified

    developers { int id PK string username UK string display_name string role string joined_at }
    developer_metrics { int id PK int developer_id FK real bug_rate real revert_rate real coverage_delta int security_count real accept_rate }
    trust_scores { int id PK int developer_id FK int score string depth string breakdown_json string calculated_at }
    pull_requests { int id PK string external_id string repo string title int author_id FK string status }
    reviews { int id PK int pr_id FK string depth string model string verdict string findings_json int duration_ms }
    security_findings { int id PK int pr_id FK int developer_id FK string rule_id string severity string file int line string explanation int resolved }
    risk_assessments { int id PK int pr_id FK string bug_risk string security_risk string maintainability_risk string deployment_risk }
    dna_profiles { int id PK string repo int chunk_count string traits_json }
    audit_logs { int id PK string actor string action string detail_json }
```

Indexes: `idx_metrics_dev`, `idx_trust_dev`, `idx_pr_author`, `idx_findings_dev` — all hot paths (latest score per developer, findings per window) are index-backed. SQLite runs in WAL mode so webhook handling and background jobs share the database safely.

## 4. Component responsibilities

| Component | Responsibility | Key decision |
|---|---|---|
| `config.py` | env + model routing + auto mock flags | Missing key ⇒ that integration mocks itself; pipeline never breaks |
| `dts_engine.py` | trust formula, depth routing, history | Explainable breakdown stored with every score |
| `nim_client.py` | NIM calls, 429 fallback to Nemotron | OpenAI SDK against `integrate.api.nvidia.com` |
| `dna_engine.py` | embeddings + trait extraction | Two layers: semantic similarity *and* measurable traits, so every violation is explainable |
| `security_scanner.py` | Semgrep subprocess, OWASP fallback pack | Scans only **added** lines reconstructed from the diff |
| `test_generator.py` | AST gap detection → AI tests | Only public functions without test references count as gaps |
| `risk_reporter.py` | weekly anonymised aggregation | Individuals never named; cohort-level signals only |
| `deploy_gate.py` | release gate | RED on any DTS<20 author or unresolved CRITICAL |
| `main.py` | orchestrator + REST + SPA | Webhook returns 200 immediately; review runs as background task |

## 5. Data flow — DNA fingerprint

```mermaid
flowchart TD
    A[Merged history<br/>last 6 months] -->|chunk_code: function-level chunks| B[Embeddings<br/>nv-embedqa-e5-v5 or local hash embedder]
    B --> C[(ChromaDB · cosine HNSW)]
    A -->|static trait extraction| D[Team trait profile<br/>snake_case 95% · type hints 88% · logging 100%]
    E[New PR diff] --> F[Chunk + embed]
    F -->|query top-3 neighbours| C
    C -->|max similarity < 0.62| G[⚠ foreign_dna violation]
    E --> H[Trait extraction] -->|compare vs profile| I[⚠ naming / error-handling / logging / type-hint violations]
```

## 6. Security model

- Webhook HMAC-SHA256 signature verification (constant-time compare).
- Secrets only via `.env` (git-ignored); `.env.example` documents every variable.
- Diff content capped at 60 KB before model calls; SQL access is parameterised throughout.
- Every automated action is written to `audit_logs`.
- DevGuardian scans itself: CI runs Semgrep over the repo on every push.
