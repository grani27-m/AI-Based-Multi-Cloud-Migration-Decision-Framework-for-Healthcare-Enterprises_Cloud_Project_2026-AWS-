"""
src/decision/ahp.py  —  Owner: Tanmay Kapoor (24BIT0079)
=========================================================
Analytic Hierarchy Process (Saaty, 1980) for the three routing criteria:
    C1 patient criticality, C2 predicted network latency, C3 cloud cost.

Pure Python (no numpy) so the identical file runs in AWS Lambda without layers.

Verified numbers for the project's pairwise matrix  [[1,3,5],[1/3,1,3],[1/5,1/3,1]]
(reproduced by `python -m src.decision.ahp` and tests/unit/test_decision.py):

    method                          C1       C2       C3      lambda_max  CR (RI=0.58)
    principal eigenvector (Saaty)   0.6370   0.2583   0.1047  3.0385      0.0332
    column normalisation (old code) 0.6333   0.2605   0.1062  -           0.0334
    reported in project report      0.6396   0.2583   0.1021  -           0.037

The reported C1/C3 values cannot be produced from this matrix by any standard AHP
method, and CR 0.037 is obtained only with the alternative random index RI=0.52.
The engine therefore uses the principal eigenvector by default (WEIGHT_SET="eigenvector");
the report's numbers stay available as WEIGHT_SET="report" so results can be compared
(see reports/ROUTING_EVALUATION_REPORT.md, which shows how many decisions differ).
"""

from __future__ import annotations

from typing import Sequence

DEFAULT_PAIRWISE_MATRIX: list[list[float]] = [
    [1.0, 3.0, 5.0],  # criticality vs (criticality, latency, cost)
    [1 / 3, 1.0, 3.0],  # latency
    [1 / 5, 1 / 3, 1.0],  # cost
]
CRITERIA = ("criticality", "latency", "cost")
# Saaty's random consistency index
RANDOM_INDEX = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}
REPORTED_WEIGHTS = (0.6396, 0.2583, 0.1021)
REPORTED_CR = 0.037
CR_LIMIT = 0.10


class AHPError(ValueError):
    pass


def validate_matrix(m: Sequence[Sequence[float]], tol: float = 1e-6) -> None:
    n = len(m)
    if n < 2 or any(len(r) != n for r in m):
        raise AHPError("pairwise matrix must be square with n >= 2")
    for i in range(n):
        if abs(m[i][i] - 1.0) > tol:
            raise AHPError(f"diagonal element [{i}][{i}] must be 1")
        for j in range(n):
            if m[i][j] <= 0:
                raise AHPError(f"element [{i}][{j}] must be positive")
            if abs(m[i][j] * m[j][i] - 1.0) > 1e-3:
                raise AHPError(f"matrix is not reciprocal at [{i}][{j}]")


def principal_eigenvector(m: Sequence[Sequence[float]], iters: int = 1000, tol: float = 1e-12):
    """Power iteration. Returns (weights summing to 1, lambda_max)."""
    validate_matrix(m)
    n = len(m)
    w = [1.0 / n] * n
    for _ in range(iters):
        v = [sum(m[i][j] * w[j] for j in range(n)) for i in range(n)]
        s = sum(v)
        v = [x / s for x in v]
        if max(abs(a - b) for a, b in zip(v, w)) < tol:
            w = v
            break
        w = v
    mw = [sum(m[i][j] * w[j] for j in range(n)) for i in range(n)]
    lam = sum(mw[i] / w[i] for i in range(n)) / n
    return w, lam


def column_normalisation_weights(m: Sequence[Sequence[float]]) -> list[float]:
    """Approximation used by the original repository code (kept for comparison only)."""
    validate_matrix(m)
    n = len(m)
    cols = [sum(m[i][j] for i in range(n)) for j in range(n)]
    return [sum(m[i][j] / cols[j] for j in range(n)) / n for i in range(n)]


def consistency(m: Sequence[Sequence[float]], weights: Sequence[float], ri: float | None = None) -> dict:
    n = len(m)
    mw = [sum(m[i][j] * weights[j] for j in range(n)) for i in range(n)]
    lam = sum(mw[i] / weights[i] for i in range(n)) / n
    ci = (lam - n) / (n - 1)
    ri = RANDOM_INDEX[n] if ri is None else ri
    cr = ci / ri if ri else 0.0
    return {"lambda_max": lam, "ci": ci, "ri": ri, "cr": cr, "consistent": cr < CR_LIMIT}


def weight_set(name: str = "eigenvector", m: Sequence[Sequence[float]] = DEFAULT_PAIRWISE_MATRIX) -> dict:
    """Return {'name','weights':{criterion: w},'cr'} for the requested weight set."""
    if name == "eigenvector":
        w, _ = principal_eigenvector(m)
    elif name == "column_normalisation":
        w = column_normalisation_weights(m)
    elif name == "report":
        w = list(REPORTED_WEIGHTS)
    else:
        raise AHPError(f"unknown weight set {name!r}")
    c = consistency(m, w)
    if not c["consistent"]:
        raise AHPError(f"pairwise judgements inconsistent: CR={c['cr']:.3f} >= {CR_LIMIT}")
    return {"name": name, "weights": dict(zip(CRITERIA, w)), "cr": c["cr"], "lambda_max": c["lambda_max"]}


def ahp_report(m: Sequence[Sequence[float]] = DEFAULT_PAIRWISE_MATRIX) -> dict:
    eig, lam = principal_eigenvector(m)
    col = column_normalisation_weights(m)
    c = consistency(m, eig)
    return {
        "matrix": [list(r) for r in m],
        "eigenvector": {
            "weights": dict(zip(CRITERIA, eig)),
            "lambda_max": lam,
            "ci": c["ci"],
            "cr_ri_0_58": c["cr"],
            "cr_ri_0_52": c["ci"] / 0.52,
        },
        "column_normalisation": {"weights": dict(zip(CRITERIA, col)), "cr_ri_0_58": consistency(m, col)["cr"]},
        "reported": {"weights": dict(zip(CRITERIA, REPORTED_WEIGHTS)), "cr": REPORTED_CR},
        "note": "Reported C1/C3 weights are not reproducible from the documented matrix; CR 0.037 corresponds "
        "to RI=0.52. Default engine uses the principal eigenvector.",
    }


if __name__ == "__main__":
    import json

    print(json.dumps(ahp_report(), indent=2))
