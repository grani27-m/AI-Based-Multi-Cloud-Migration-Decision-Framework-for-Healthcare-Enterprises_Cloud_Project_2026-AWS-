"""Tanmay's decision engine: AHP maths, vetoes, validation, determinism, explanations."""

from __future__ import annotations

import math

import pytest

from src.decision.ahp import (
    DEFAULT_PAIRWISE_MATRIX,
    AHPError,
    REPORTED_WEIGHTS,
    ahp_report,
    column_normalisation_weights,
    consistency,
    principal_eigenvector,
    validate_matrix,
    weight_set,
)
from src.decision.criticality import criticality_from_vitals
from src.decision.router import DecisionInput, DecisionInputError, decide, route_decision


def test_eigenvector_weights_match_verified_values():
    w, lam = principal_eigenvector(DEFAULT_PAIRWISE_MATRIX)
    assert [round(x, 4) for x in w] == [0.6370, 0.2583, 0.1047]
    assert round(lam, 4) == 3.0385
    assert abs(sum(w) - 1) < 1e-12


def test_consistency_ratio_saaty_and_alternative_ri():
    w, _ = principal_eigenvector(DEFAULT_PAIRWISE_MATRIX)
    c = consistency(DEFAULT_PAIRWISE_MATRIX, w)
    assert round(c["cr"], 4) == 0.0332 and c["consistent"]
    assert round(c["ci"] / 0.52, 3) == 0.037  # the report's 0.037 = alternative random index


def test_reported_weights_are_not_reproducible_from_matrix():
    eig, _ = principal_eigenvector(DEFAULT_PAIRWISE_MATRIX)
    col = column_normalisation_weights(DEFAULT_PAIRWISE_MATRIX)
    assert abs(eig[0] - REPORTED_WEIGHTS[0]) > 0.002 and abs(col[0] - REPORTED_WEIGHTS[0]) > 0.002
    assert abs(eig[1] - REPORTED_WEIGHTS[1]) < 1e-4  # latency weight does match
    assert "not reproducible" in ahp_report()["note"]


def test_weight_sets_sum_to_one():
    for name in ("eigenvector", "column_normalisation", "report"):
        assert abs(sum(weight_set(name)["weights"].values()) - 1) < 1e-3


@pytest.mark.parametrize("m", [[[1, 2], [2, 1]], [[1, 3, 5], [1 / 3, 1, 3]], [[2, 1], [1, 2]], [[1, -1], [-1, 1]]])
def test_invalid_matrices_rejected(m):
    with pytest.raises(AHPError):
        validate_matrix(m)


def test_inconsistent_matrix_rejected():
    bad = [[1, 9, 1 / 9], [1 / 9, 1, 9], [9, 1 / 9, 1]]
    with pytest.raises(AHPError):
        from src.decision import ahp

        ahp.weight_set("eigenvector", bad)


@pytest.mark.parametrize("crit", [9.0, 9.5, 10.0])
def test_emergency_override_always_edge(crit):
    for lat in (0.0, 50.0, 299.0, 1000.0):
        for cost in (0.0, 1.0):
            r = decide(DecisionInput("D", crit, lat, cost))
            assert r.destination == "EDGE" and r.reason == "override_critical_patient" and r.edge_score is None


@pytest.mark.parametrize("lat", [300.0, 450.0, 5000.0])
def test_network_veto_always_edge(lat):
    r = decide(DecisionInput("D", 0.0, lat, 0.0))
    assert r.destination == "EDGE" and r.reason == "network_degradation_veto" and r.veto == "network"


def test_boundaries():
    assert decide(DecisionInput("D", 8.99, 10, 0.1)).reason == "ahp_decision"
    assert decide(DecisionInput("D", 1.0, 299.99, 0.1)).reason == "ahp_decision"


def test_missing_prediction_is_safe_edge_default():
    r = decide(DecisionInput("D", 3.0, None, 0.4))
    assert r.destination == "EDGE" and r.reason == "prediction_unavailable_safe_default"


@pytest.mark.parametrize(
    "args",
    [
        ("", 1, 10, 0.1),
        ("D", -0.1, 10, 0.1),
        ("D", 10.1, 10, 0.1),
        ("D", 1, -5, 0.1),
        ("D", 1, 10, 1.5),
        ("D", math.nan, 10, 0.1),
        ("D", 1, math.nan, 0.1),
        ("D", "5", 10, 0.1),
        ("D", True, 10, 0.1),
    ],
)
def test_invalid_inputs_raise(args):
    with pytest.raises(DecisionInputError):
        decide(DecisionInput(*args))


def test_routine_cloud_and_serious_edge():
    assert decide(DecisionInput("D", 0.9, 33.8, 0.2)).destination == "CLOUD"
    assert decide(DecisionInput("D", 7.0, 80.0, 0.7)).destination == "EDGE"


def test_scores_explainable_and_consistent():
    r = decide(DecisionInput("D", 5.0, 120.0, 0.5))
    assert abs(sum(r.contributions["edge"].values()) - r.edge_score) < 1e-5
    assert abs(sum(r.contributions["cloud"].values()) - r.cloud_score) < 1e-5
    assert r.explanation and r.engine_version and set(r.weights) == {"criticality", "latency", "cost"}


def test_monotonic_in_criticality():
    """Raising criticality never moves a reading from EDGE to CLOUD."""
    for lat in (10, 100, 250):
        prev_edge = False
        for c in [x / 10 for x in range(0, 90)]:
            is_edge = decide(DecisionInput("D", c, lat, 0.3)).destination == "EDGE"
            assert not (prev_edge and not is_edge)
            prev_edge = is_edge


def test_deterministic():
    a = decide(DecisionInput("D", 4.4, 77.0, 0.33)).to_dict()
    b = decide(DecisionInput("D", 4.4, 77.0, 0.33)).to_dict()
    assert a == b


def test_backward_compatible_wrapper():
    r = route_decision("ECG-101", 9.5, 210.5, 0.4)
    assert r == {
        "device_id": "ECG-101",
        "routing_decision": "EDGE",
        "reason": "override_critical_patient",
        "cloud_score": None,
        "edge_score": None,
    }


@pytest.mark.parametrize(
    "v,agg,score", [((75, 16, 98), 0, 0.0), ((95, 22, 95), 4, 5.71), ((135, 26, 90), 9, 10.0), ((105, 21, 93), 5, 7.14)]
)
def test_partial_news2_criticality(v, agg, score):
    r = criticality_from_vitals(*v)
    assert r.aggregate == agg and r.score == score


def test_news2_emergency_maps_to_override():
    assert criticality_from_vitals(120, 25, 92).aggregate == 7  # 2 + 3 + 2
    assert criticality_from_vitals(120, 25, 92).score >= 9.0
    assert criticality_from_vitals(120, 25, 94).score < 9.0  # aggregate 6


def test_criticality_rejects_implausible():
    with pytest.raises(ValueError):
        criticality_from_vitals(500, 16, 98)
