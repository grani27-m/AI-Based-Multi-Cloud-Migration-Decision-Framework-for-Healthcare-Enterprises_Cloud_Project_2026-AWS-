"""
02 - Compute the AHP weights step by step and check consistency.

    python 02_calculate_ahp.py                       # project matrix
    python 02_calculate_ahp.py --matrix "1,9,1/9;1/9,1,9;9,1/9,1"   # try your own (this one is inconsistent)
"""

from __future__ import annotations

import argparse
from fractions import Fraction

from demo_common import RESULTS
from src.decision.ahp import (CR_LIMIT, CRITERIA, DEFAULT_PAIRWISE_MATRIX, RANDOM_INDEX, REPORTED_CR, REPORTED_WEIGHTS,
                              AHPError, column_normalisation_weights, consistency, validate_matrix)


def parse(s: str) -> list[list[float]]:
    return [[float(Fraction(x.strip())) for x in row.split(",")] for row in s.split(";")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matrix", help='rows separated by ";", values by "," (fractions allowed)')
    a = ap.parse_args()
    m = parse(a.matrix) if a.matrix else DEFAULT_PAIRWISE_MATRIX
    n = len(m)
    try:
        validate_matrix(m)
    except AHPError as exc:
        print("INVALID MATRIX:", exc)
        return 1
    names = CRITERIA if n == 3 else [f"C{i + 1}" for i in range(n)]
    print("Step 1 - matrix")
    for nm, r in zip(names, m):
        print(f"  {nm:<12}" + "".join(f"{v:>9.4f}" for v in r))
    print("\nStep 2 - principal eigenvector by power iteration (w <- M w / sum)")
    w = [1 / n] * n
    for it in range(1, 50):
        v = [sum(m[i][j] * w[j] for j in range(n)) for i in range(n)]
        s = sum(v)
        v = [x / s for x in v]
        delta = max(abs(x - y) for x, y in zip(v, w))
        w = v
        if it <= 5 or delta < 1e-12:
            print(f"  iteration {it:>2}: " + "  ".join(f"{x:.6f}" for x in w) + f"   change {delta:.2e}")
        if delta < 1e-12:
            break
    c = consistency(m, w)
    print(f"\nStep 3 - consistency: lambda_max = {c['lambda_max']:.4f}, CI = (lambda_max - n)/(n - 1) = {c['ci']:.5f}")
    print(f"  CR = CI / RI(n={n}) = {c['ci']:.5f} / {RANDOM_INDEX[n]} = {c['cr']:.4f}  -> "
          f"{'CONSISTENT' if c['consistent'] else 'INCONSISTENT'} (limit {CR_LIMIT})")
    if n == 3:
        print(f"  with the alternative RI = 0.52: CR = {c['ci'] / 0.52:.4f}")
    print("\nStep 4 - weights")
    for nm, x in zip(names, w):
        print(f"  {nm:<12} {x:.4f}")
    if m == DEFAULT_PAIRWISE_MATRIX:
        col = column_normalisation_weights(m)
        print("\nComparison with other values for the same matrix:")
        print(f"  {'method':<32}" + "".join(f"{nm:>12}" for nm in names) + f"{'CR':>8}")
        print(f"  {'principal eigenvector (used)':<32}" + "".join(f"{x:>12.4f}" for x in w) + f"{c['cr']:>8.4f}")
        print(f"  {'column normalisation (old code)':<32}" + "".join(f"{x:>12.4f}" for x in col) + f"{consistency(m, col)['cr']:>8.4f}")
        print(f"  {'printed in project report':<32}" + "".join(f"{x:>12.4f}" for x in REPORTED_WEIGHTS) + f"{REPORTED_CR:>8.3f}")
        print("  -> the report's criticality/cost weights cannot be derived from this matrix; latency matches.")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "ahp_weights.txt").write_text("\n".join(f"{nm} {x:.6f}" for nm, x in zip(names, w)) + f"\nCR {c['cr']:.6f}\n")
    return 0 if c["consistent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
