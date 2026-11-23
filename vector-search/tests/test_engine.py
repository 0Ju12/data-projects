import sqlite3
import numpy as np
import pytest
from vectorlab import Index, save_new, append
from vectorlab.pipeline import pipeline


def test_persistent_exact_matches_independent_cosine_and_all_probes(tmp_path):
    rng = np.random.default_rng(3)
    matrix = rng.normal(size=(57, 9))
    q = matrix[32] + 0.07
    ids = [str(i) for i in range(len(matrix))]
    path = tmp_path / "index"
    save_new(path, ids, ids, matrix, clusters=7)
    exact = Index(path).search(q, 8)
    ref = matrix @ q / np.linalg.norm(matrix, axis=1) / np.linalg.norm(q)
    assert [i for i,_ in exact] == [ids[i] for i in np.argsort(-ref)[:8]]
    np.testing.assert_allclose([s for _,s in exact], sorted(ref, reverse=True)[:8], atol=1e-6)
    assert exact == Index(path).search(q, 8, probes=7)


def test_atomic_add_and_existing_snapshot(tmp_path):
    path = tmp_path / "db"
    save_new(path, ["a"], ["original"], [[1,0]])
    old = Index(path)
    with pytest.raises(sqlite3.IntegrityError):
        append(path, ["b","a"], ["new","duplicate"], [[1,0],[0,1]])
    assert Index(path).ids == ("a",)
    with pytest.raises(ValueError):
        append(path, ["b"], ["new"], [[0,0]])
    append(path, ["b"], ["new"], [[0,1]])
    assert old.ids == ("a",)
    assert Index(path).search([0,1], 1, 1)[0][0] == "b"
    with pytest.raises(sqlite3.OperationalError):
        save_new(path, ["x"], ["replacement"], [[1,1]])
    assert Index(path).ids == ("a","b")


def test_ties_and_query_validation(tmp_path):
    path = tmp_path / "ties"
    save_new(path, ["b","a"], ["B","A"], [[1,1],[1,1]], clusters=2)
    index = Index(path)
    assert index.search([1,1], 1)[0][0] == "a"
    for query,k,probes in [([0,0],1,None),([1],1,None),([1,1],0,None),([1,1],1,3),([np.nan,1],1,1)]:
        with pytest.raises(ValueError):
            index.search(query,k,probes)


def test_pipeline_metrics_and_unanswerable_denominator(tmp_path):
    report = pipeline(tmp_path/"result.json", sizes=(32,), queries=4)
    assert report["synthetic"][0]["modes"][-1]["recall_at_k"] == 1
    for block in report["heritage"].values():
        assert block["answerable"] == 6
        assert len(block["rows"]) == 9
        assert len([r for r in block["rows"] if not r["relevant"]]) == 3
