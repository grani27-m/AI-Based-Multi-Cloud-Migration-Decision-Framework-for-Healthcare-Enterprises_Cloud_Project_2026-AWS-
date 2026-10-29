"""Tanmay: multi-candidate ranking (edge vs several clouds) and equivalence with the two-alternative engine."""

from __future__ import annotations

import itertools

import pytest

from src.decision.candidates import CloudCandidate, rank_candidates
from src.decision.router import DecisionInput, DecisionInputError, decide


@pytest.mark.parametrize(
    "crit,lat,cost",
    list(itertools.product([0, 2.5, 5, 7, 8.5, 9.2], [0, 40, 150, 299, 300, 450, None], [0, 0.3, 1])),
)
def test_single_cloud_equals_two_alternative_engine(crit, lat, cost):
    a = decide(DecisionInput("D", crit, lat, cost))
    b = rank_candidates("D", crit, [CloudCandidate("CLOUD", lat, cost)])
    assert (b.destination == "EDGE") == (a.destination == "EDGE")
    assert b.reason == a.reason
    if a.edge_score is not None:
        scores = {s.name: s.score for s in b.ranking}
        assert scores["EDGE"] == pytest.approx(a.edge_score, abs=1e-6)
        assert scores["CLOUD"] == pytest.approx(a.cloud_score, abs=1e-6)


def test_cheaper_faster_cloud_wins():
    r = rank_candidates(
        "D",
        1.0,
        [CloudCandidate("aws-eu-north-1", 120, 0.6), CloudCandidate("aws-ap-south-1", 35, 0.3)],
    )
    assert r.destination == "aws-ap-south-1" and r.destination_kind == "cloud"
    assert [s.name for s in r.ranking][0] == "aws-ap-south-1"


def test_vetoed_cloud_is_excluded_but_others_remain():
    r = rank_candidates("D", 1.0, [CloudCandidate("slow", 350, 0.1), CloudCandidate("ok", 40, 0.4)])
    assert r.destination == "ok"
    slow = next(s for s in r.ranking if s.name == "slow")
    assert not slow.admissible and "veto" in slow.excluded_reason


def test_all_clouds_vetoed_goes_edge():
    r = rank_candidates("D", 1.0, [CloudCandidate("a", 310, 0.1), CloudCandidate("b", 500, 0.1)])
    assert r.destination == "EDGE" and r.reason == "network_degradation_veto"


def test_missing_forecasts_safe_edge():
    r = rank_candidates("D", 1.0, [CloudCandidate("a", None, 0.1)])
    assert r.destination == "EDGE" and r.reason == "prediction_unavailable_safe_default"


def test_emergency_skips_all_clouds():
    r = rank_candidates("D", 9.5, [CloudCandidate("a", 5, 0.0), CloudCandidate("b", 5, 0.0)])
    assert r.destination == "EDGE" and r.reason == "override_critical_patient"


def test_serious_patient_stays_at_edge_even_with_good_clouds():
    r = rank_candidates("D", 8.0, [CloudCandidate("a", 20, 0.2), CloudCandidate("b", 30, 0.1)])
    assert r.destination == "EDGE"


@pytest.mark.parametrize(
    "clouds",
    [
        [],
        [CloudCandidate("a", 10, 0.1), CloudCandidate("a", 20, 0.1)],
        [CloudCandidate("EDGE", 10, 0.1)],
        [CloudCandidate("a", 10, 1.5)],
        [CloudCandidate("", 10, 0.1)],
        [CloudCandidate("a", -1, 0.1)],
    ],
)
def test_invalid_candidates_rejected(clouds):
    with pytest.raises(DecisionInputError):
        rank_candidates("D", 1.0, clouds)


def test_invalid_criticality_rejected():
    with pytest.raises(DecisionInputError):
        rank_candidates("D", 11, [CloudCandidate("a", 10, 0.1)])
