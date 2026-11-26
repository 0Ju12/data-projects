import hashlib
import json
import os
import platform
import sys
import tempfile
from importlib.resources import files
from pathlib import Path
from time import perf_counter_ns

import numpy as np

from .index import Index, save_new
from .text import ENCODER, encode


def sample(name):
    return json.loads(files("vectorlab").joinpath("data", name + ".json").read_text(encoding="utf-8"))


def evaluate(folder):
    docs, questions = sample("documents"), sample("queries")
    path = folder / "heritage.sqlite"
    save_new(
        path,
        [d["id"] for d in docs],
        [d["text"] for d in docs],
        [encode(d["text"]) for d in docs],
        clusters=3,
        encoder=ENCODER,
    )
    index = Index(path)
    result = {}
    for mode, probes in (("exact", None), ("ivf", 1)):
        rows = []
        for q in questions:
            hits = index.search(encode(q["text"]), 3, probes)
            ids = [doc for doc, _ in hits]
            rank = next((i for i, doc in enumerate(ids, 1) if doc in q["relevant"]), None)
            rows.append({**q, "retrieved": ids, "rank": rank})
        answerable = [r for r in rows if r["relevant"]]
        result[mode] = {
            "hit_at_3": sum(bool(r["rank"]) for r in answerable) / len(answerable),
            "mrr_at_3": sum(1 / r["rank"] for r in answerable if r["rank"]) / len(answerable),
            "answerable": len(answerable),
            "rows": rows,
        }
    return result


def benchmark(folder, size, seed, count):
    rng = np.random.default_rng(seed)
    dim, clusters = 96, min(32, size)
    topics = rng.normal(size=(32, dim))

    def draw(n):
        return (topics[rng.integers(32, size=n)] + rng.normal(0, 1.3, (n, dim))).astype("f4")

    vectors, queries = draw(size), draw(count)
    path = folder / f"bench-{size}.sqlite"
    started = perf_counter_ns()
    save_new(path, [f"d{i}" for i in range(size)], [""] * size, vectors, clusters, seed)
    build_ms = (perf_counter_ns() - started) / 1e6
    index = Index(path)
    k = min(10, size)
    truth = [set(i for i, _ in index.search(q, k)) for q in queries]
    modes = []
    for probes in [None, *sorted({1, min(4, clusters), min(12, clusters), clusters})]:
        index.search(queries[0], k, probes)
        elapsed, recalls = [], []
        for q, target in zip(queries, truth):
            start = perf_counter_ns()
            top = index.search(q, k, probes)
            elapsed.append((perf_counter_ns() - start) / 1e6)
            recalls.append(len(target.intersection(i for i, _ in top)) / k)
        modes.append(
            {
                "probes": probes,
                "recall_at_k": float(np.mean(recalls)),
                "p50_ms": float(np.median(elapsed)),
                "p95_ms": float(np.percentile(elapsed, 95)),
            }
        )
    return {
        "documents": size,
        "dimensions": dim,
        "clusters": clusters,
        "k": k,
        "queries": count,
        "build_ms": build_ms,
        "database_bytes": path.stat().st_size,
        "index_array_bytes": index.array_bytes,
        "modes": modes,
    }


def pipeline(output, sizes=(1000, 10000), seed=42, queries=128):
    if not sizes or min(sizes) < 10 or len(set(sizes)) != len(sizes) or queries < 1:
        raise ValueError("use unique sizes >= 10 and a positive query count")
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        report = {
            "seed": seed,
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "platform": platform.platform(),
            "openblas_threads": os.getenv("OPENBLAS_NUM_THREADS"),
            "fixture_sha256": {
                s: hashlib.sha256(files("vectorlab").joinpath("data", s + ".json").read_bytes()).hexdigest()
                for s in ("queries", "documents")
            },
            "heritage": evaluate(folder),
            "synthetic": [benchmark(folder, n, seed, queries) for n in sizes],
        }
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, mode="w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(f.name, path)
    return report
