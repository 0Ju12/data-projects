import argparse
import json
import sqlite3
from pathlib import Path

from .index import Index, append, save_new
from .pipeline import pipeline
from .text import ENCODER, encode


def main():
    parser = argparse.ArgumentParser(description="Persistent cosine vector search")
    commands = parser.add_subparsers(required=True, dest="cmd")
    for name in ("build", "add"):
        cmd = commands.add_parser(name)
        cmd.add_argument("db")
        cmd.add_argument("documents", type=Path, help='JSON array of {"id": "...", "text": "..."}')
        if name == "build":
            cmd.add_argument("--clusters", type=int, default=1)
    search = commands.add_parser("search")
    search.add_argument("db")
    search.add_argument("query")
    search.add_argument("-k", type=int, default=3)
    search.add_argument("--probes", type=int)
    bench = commands.add_parser("pipeline")
    bench.add_argument("--out", default="report.json")
    bench.add_argument("--sizes", nargs="+", type=int, default=[1000, 10000])
    bench.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    try:
        if args.cmd == "pipeline":
            pipeline(args.out, args.sizes, args.seed)
            print(args.out)
        elif args.cmd == "search":
            index = Index(args.db)
            if index.encoder != ENCODER:
                raise ValueError("use the embedding model used at build time via the Python API")
            hits = index.search(encode(args.query), args.k, args.probes)
            texts = dict(zip(index.ids, index.texts))
            print(json.dumps([{"id": i, "score": s, "text": texts[i]} for i, s in hits], ensure_ascii=False, indent=2))
        else:
            docs = json.loads(args.documents.read_text(encoding="utf-8"))
            ids, texts = [d["id"] for d in docs], [d["text"] for d in docs]
            vectors = [encode(t) for t in texts]
            if args.cmd == "build":
                save_new(args.db, ids, texts, vectors, args.clusters, encoder=ENCODER)
            else:
                append(args.db, ids, texts, vectors, encoder=ENCODER)
    except (sqlite3.Error, ValueError, TypeError, AttributeError, KeyError, OSError) as exc:
        parser.exit(2, f"vectorlab: {exc}\n")


if __name__ == "__main__":
    main()
