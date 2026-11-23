"""Small persistent cosine index. Readers use one complete SQLite snapshot."""
from pathlib import Path
from contextlib import closing
import sqlite3
import numpy as np


def units(values):
    a = np.asarray(values, dtype=np.float32)
    if a.ndim != 2 or not all(a.shape) or not np.isfinite(a).all():
        raise ValueError("expected a finite nonempty matrix")
    norms = np.linalg.norm(a.astype(np.float64), axis=1, keepdims=True)
    if (norms == 0).any():
        raise ValueError("zero vectors have no cosine direction")
    return (a / norms).astype(np.float32)


def scores(matrix, query):
    return np.einsum("ij,j->i", matrix, query)


def train(vectors, clusters, seed):
    if not 1 <= clusters <= len(vectors):
        raise ValueError("clusters must be between 1 and the document count")
    rng = np.random.default_rng(seed)
    sample = vectors[rng.choice(len(vectors), min(len(vectors), max(4096, clusters)), replace=False)]
    centers = sample[rng.choice(len(sample), clusters, replace=False)].copy()
    for _ in range(18):
        labels = np.argmax(sample @ centers.T, axis=1)
        sums = np.zeros_like(centers)
        np.add.at(sums, labels, sample)
        occupied = np.linalg.norm(sums, axis=1) > 0
        updated = centers.copy()
        if occupied.any():
            updated[occupied] = units(sums[occupied])
        if np.allclose(updated, centers):
            break
        centers = updated
    return centers


def entries(ids, texts, vectors):
    matrix = units(vectors)
    if len(ids) != len(matrix) or len(texts) != len(ids):
        raise ValueError("ids, texts and vectors must have equal length")
    if any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("document ids must be unique nonempty strings")
    if any(not isinstance(t, str) for t in texts):
        raise ValueError("document texts must be strings")
    return matrix


def insert(db, ids, texts, matrix, centers):
    if matrix.shape[1] != centers.shape[1]:
        raise ValueError("vector dimensions do not match")
    for start in range(0, len(ids), 1024):
        batch = matrix[start:start+1024]
        labels = np.argmax(batch @ centers.T, axis=1)
        rows = ((ids[i], texts[i], v.astype("<f4").tobytes(), int(c))
                for i, (v, c) in enumerate(zip(batch, labels), start))
        db.executemany("INSERT INTO docs VALUES(?,?,?,?)", rows)


def write_connection(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=rw", uri=True)


def save_new(path, ids, texts, vectors, clusters=1, seed=42, encoder="external"):
    matrix = entries(ids, texts, vectors)
    centers = train(matrix, clusters, seed)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE meta(encoder TEXT, dim INTEGER, centers BLOB, version INTEGER)")
        db.execute("CREATE TABLE docs(id TEXT PRIMARY KEY, text TEXT, vec BLOB, cluster INTEGER)")
        db.execute("INSERT INTO meta VALUES(?,?,?,1)", (encoder, matrix.shape[1], centers.astype("<f4").tobytes()))
        insert(db, ids, texts, matrix, centers)


def metadata(db):
    encoder, dim, raw, version = db.execute("SELECT * FROM meta").fetchone()
    if version != 1:
        raise ValueError("unsupported index version")
    return encoder, np.frombuffer(raw, dtype="<f4").reshape(-1, dim)


def append(path, ids, texts, vectors, encoder="external"):
    matrix = entries(ids, texts, vectors)
    with closing(write_connection(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        stored, centers = metadata(db)
        if stored != encoder:
            raise ValueError("encoder mismatch")
        insert(db, ids, texts, matrix, centers)


class Index:
    def __init__(self, path):
        uri = Path(path).resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            db.execute("BEGIN")
            self.encoder, self.centers = metadata(db)
            rows = db.execute("SELECT id,text,vec,cluster FROM docs ORDER BY id").fetchall()
        self.ids, self.texts, blobs, labels = zip(*rows)
        self.matrix = np.frombuffer(b"".join(blobs), dtype="<f4").reshape(len(rows), -1)
        self.all_ids = np.arange(len(rows))
        groups = [[] for _ in self.centers]
        for row, label in enumerate(labels):
            groups[label].append(row)
        self.postings = [np.asarray(g, dtype=np.intp) for g in groups]

    @property
    def array_bytes(self):
        return self.matrix.nbytes + self.centers.nbytes + self.all_ids.nbytes + sum(g.nbytes for g in self.postings)

    def search(self, query, k=10, probes=None):
        """None probes gives exhaustive search. Ties are ordered by document id."""
        q = units([query])[0]
        if k < 1 or len(q) != self.matrix.shape[1]:
            raise ValueError("invalid k or query dimension")
        ids = self.all_ids
        if probes is None:
            similarity = scores(self.matrix, q)
        else:
            if not 1 <= probes <= len(self.centers):
                raise ValueError("invalid probe count")
            chosen = np.argsort(-scores(self.centers, q), kind="stable")[:probes]
            ids = np.concatenate([self.postings[c] for c in chosen])
            similarity = scores(self.matrix[ids], q)
        ranked = np.lexsort((ids, -similarity))[:k]
        return [(self.ids[i], float(similarity[j])) for j, i in zip(ranked, ids[ranked])]
