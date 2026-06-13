"""Module 2 — Codebase DNA Fingerprint engine.

Learns the team's actual conventions from merged history instead of generic
lint rules. Two complementary layers:

1. Semantic layer — code chunks embedded into ChromaDB. A new chunk whose
   nearest historical neighbours are too dissimilar is "foreign DNA".
2. Trait layer — measurable conventions (naming style, type hints,
   docstrings, logging, error handling) extracted statically and compared
   against the learned profile, so every violation is explainable.

Embeddings: nvidia/nv-embedqa-e5-v5 via NIM when a key is configured,
otherwise a deterministic local hashing embedder (offline-safe, no download).
"""
import hashlib
import json
import logging
import math
import re

import chromadb

from . import config
from .database import get_db, now

logger = logging.getLogger("devguardian.dna")

COLLECTION = "codebase_dna"
SIMILARITY_THRESHOLD = 0.62  # below this, the chunk doesn't match team DNA
EMBED_DIM = 384


# --- Embedding --------------------------------------------------------------

def _local_embed(text: str) -> list[float]:
    """Deterministic hashed bag-of-tokens embedding (mock mode, no downloads)."""
    vec = [0.0] * EMBED_DIM
    tokens = re.findall(r"[A-Za-z_]\w*|[^\sA-Za-z0-9]", text)
    for tok in tokens:
        h = int(hashlib.md5(tok.encode(), usedforsecurity=False).hexdigest(), 16)
        vec[h % EMBED_DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _nim_embed(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI
    client = OpenAI(base_url=config.NIM_BASE_URL, api_key=config.NVIDIA_API_KEY)
    resp = client.embeddings.create(
        model=config.MODEL_EMBED, input=texts,
        extra_body={"input_type": "passage", "truncate": "END"},
    )
    return [d.embedding for d in resp.data]


def embed(texts: list[str]) -> list[list[float]]:
    if config.MOCK_NIM:
        return [_local_embed(t) for t in texts]
    return _nim_embed(texts)


# --- Trait extraction ---------------------------------------------------------

def extract_traits(code: str) -> dict:
    """Measure stylistic conventions in a code sample."""
    names = re.findall(r"\bdef\s+(\w+)|\b(\w+)\s*=", code)
    flat = [a or b for a, b in names if (a or b)]
    snake = sum(1 for n in flat if re.fullmatch(r"[a-z_][a-z0-9_]*", n))
    camel = sum(1 for n in flat if re.fullmatch(r"[a-z]+(?:[A-Z][a-z0-9]*)+", n))
    defs = len(re.findall(r"\bdef\s+\w+", code))
    return {
        "snake_case_ratio": round(snake / len(flat), 2) if flat else 1.0,
        "camel_case_ratio": round(camel / len(flat), 2) if flat else 0.0,
        "type_hint_ratio": round(
            len(re.findall(r"def\s+\w+\([^)]*:\s*\w", code)) / defs, 2) if defs else 0.0,
        "docstring_ratio": round(
            len(re.findall(r'def\s+\w+\([^)]*\)\s*(?:->[^:]+)?:\s*\n\s*("""|\'\'\')', code)) / defs, 2)
            if defs else 0.0,
        "uses_logging": bool(re.search(r"\blogging\b|\blogger\.", code)),
        "uses_print_debug": bool(re.search(r"\bprint\(", code)),
        "bare_except": bool(re.search(r"except\s*:", code)),
        "specific_except": bool(re.search(r"except\s+\w+", code)),
    }


def _aggregate_traits(samples: list[dict]) -> dict:
    if not samples:
        return {}
    agg = {}
    for key in samples[0]:
        vals = [s[key] for s in samples]
        if isinstance(vals[0], bool):
            agg[key] = round(sum(vals) / len(vals), 2)  # prevalence 0-1
        else:
            agg[key] = round(sum(vals) / len(vals), 2)
    return agg


# --- Engine -------------------------------------------------------------------

def _collection():
    client = chromadb.PersistentClient(path=config.CHROMA_PATH)
    return client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})


def chunk_code(content: str, max_lines: int = 40) -> list[str]:
    """Split a file into function-ish chunks for embedding."""
    lines = content.splitlines()
    chunks, current = [], []
    for line in lines:
        if re.match(r"^(def |class |async def )", line) and len(current) > 4:
            chunks.append("\n".join(current))
            current = []
        current.append(line)
        if len(current) >= max_lines:
            chunks.append("\n".join(current))
            current = []
    if len(current) > 2:
        chunks.append("\n".join(current))
    return [c for c in chunks if len(c.strip()) > 50]


def ingest_history(repo: str, files: dict[str, str]) -> dict:
    """Embed historical (merged) code into the DNA store and learn traits."""
    col = _collection()
    all_chunks, ids, metas, trait_samples = [], [], [], []
    for fname, content in files.items():
        for i, chunk in enumerate(chunk_code(content)):
            all_chunks.append(chunk)
            ids.append(hashlib.md5(
                f"{repo}:{fname}:{i}:{chunk[:80]}".encode(), usedforsecurity=False).hexdigest())
            metas.append({"repo": repo, "file": fname})
        trait_samples.append(extract_traits(content))
    if all_chunks:
        col.upsert(ids=ids, documents=all_chunks,
                   embeddings=embed(all_chunks), metadatas=metas)
    traits = _aggregate_traits(trait_samples)
    repo_count = len(col.get(where={"repo": repo}, include=[])["ids"])  # this repo only
    with get_db() as db:
        db.execute("DELETE FROM dna_profiles WHERE repo = ?", (repo,))
        db.execute(
            "INSERT INTO dna_profiles (repo, chunk_count, traits_json, updated_at) VALUES (?,?,?,?)",
            (repo, repo_count, json.dumps(traits), now()),
        )
    logger.info("DNA ingested for %s: %s chunks, traits=%s", repo, len(all_chunks), traits)
    return {"chunks_ingested": len(all_chunks), "repo_chunks": repo_count,
            "total_chunks": col.count(), "traits": traits}


def get_profile(repo: str) -> dict | None:
    with get_db() as db:
        row = db.execute("SELECT * FROM dna_profiles WHERE repo = ?", (repo,)).fetchone()
    if not row:
        return None
    return {"repo": row["repo"], "chunk_count": row["chunk_count"],
            "traits": json.loads(row["traits_json"]), "updated_at": row["updated_at"]}


def check_violations(repo: str, files: dict[str, str]) -> list[dict]:
    """Compare new PR code against the learned DNA. Returns explainable violations."""
    col = _collection()
    profile = get_profile(repo)
    violations: list[dict] = []
    # Scope the semantic comparison to THIS repo's own history — a single shared
    # ChromaDB collection holds every repo's chunks, so we must filter by repo or
    # PRs would be compared against unrelated codebases.
    repo_count = len(col.get(where={"repo": repo}, include=[])["ids"])

    for fname, content in files.items():
        chunks = chunk_code(content) or ([content] if content.strip() else [])
        if chunks and repo_count > 0:
            results = col.query(query_embeddings=embed(chunks),
                                n_results=min(3, repo_count), where={"repo": repo})
            for chunk, dists in zip(chunks, results["distances"]):
                similarity = 1 - min(dists)  # cosine distance -> similarity
                if similarity < SIMILARITY_THRESHOLD:
                    violations.append({
                        "type": "foreign_dna", "file": fname,
                        "similarity": round(similarity, 3),
                        "message": (f"This code is only {round(similarity * 100)}% similar to "
                                    "anything in your codebase history — it does not match "
                                    "your team's established patterns."),
                        "snippet": chunk[:200],
                    })

        if profile and profile["traits"]:
            t_new, t_team = extract_traits(content), profile["traits"]
            if t_new["camel_case_ratio"] > 0.5 and t_team.get("snake_case_ratio", 0) > 0.7:
                violations.append({
                    "type": "naming_convention", "file": fname,
                    "message": (f"PR uses camelCase ({t_new['camel_case_ratio']:.0%}) but "
                                f"{t_team['snake_case_ratio']:.0%} of your codebase uses snake_case."),
                })
            if t_new["bare_except"] and t_team.get("bare_except", 1) < 0.2:
                violations.append({
                    "type": "error_handling", "file": fname,
                    "message": "Bare `except:` used — your team consistently catches specific exceptions.",
                })
            if t_new["uses_print_debug"] and t_team.get("uses_logging", 0) > 0.5:
                violations.append({
                    "type": "logging_style", "file": fname,
                    "message": "print() used for output — your codebase standard is the logging module.",
                })
            if (t_new["type_hint_ratio"] < 0.3 and t_team.get("type_hint_ratio", 0) > 0.6):
                violations.append({
                    "type": "type_hints", "file": fname,
                    "message": (f"Only {t_new['type_hint_ratio']:.0%} of new functions have type "
                                f"hints; your team averages {t_team['type_hint_ratio']:.0%}."),
                })
    return violations
