"""
Supersession engine correctness — Phase 1 cases (Stage 1+2 rules).
These must all pass before Phase 2 LLM adjudication is added.
"""
import pytest
from datetime import datetime, timezone, timedelta

from src.agentmem.supersession import classify_relation, _metadata_overlap


T0 = datetime(2026, 5, 1, tzinfo=timezone.utc)
T1 = datetime(2026, 5, 10, tzinfo=timezone.utc)
T2 = datetime(2026, 5, 20, tzinfo=timezone.utc)

META_NVDA_GUIDANCE = {"ticker": "NVDA", "metric": "guidance"}
META_NVDA_REVENUE = {"ticker": "NVDA", "metric": "revenue"}
META_AMD_GUIDANCE = {"ticker": "AMD", "metric": "guidance"}


class TestMetadataOverlap:
    def test_exact_match(self):
        assert _metadata_overlap(META_NVDA_GUIDANCE, META_NVDA_GUIDANCE) == {"ticker", "metric"}

    def test_different_ticker(self):
        assert _metadata_overlap(META_NVDA_GUIDANCE, META_AMD_GUIDANCE) == {"metric"}

    def test_different_metric(self):
        assert _metadata_overlap(META_NVDA_GUIDANCE, META_NVDA_REVENUE) == {"ticker"}

    def test_no_structured_keys(self):
        assert _metadata_overlap({"note": "x"}, {"note": "x"}) == set()


class TestClassifyRelation:
    def test_supersedes_newer_event_time(self):
        relation, conf = classify_relation(
            old_content="NVDA Q3 guidance $32B",
            new_content="NVDA Q3 guidance raised to $36B",
            old_event_time=T0,
            new_event_time=T1,
            old_meta=META_NVDA_GUIDANCE,
            new_meta=META_NVDA_GUIDANCE,
        )
        assert relation == "SUPERSEDES"
        assert conf >= 0.8

    def test_confirms_same_value(self):
        relation, conf = classify_relation(
            old_content="NVDA Q3 guidance $36B",
            new_content="NVDA Q3 guidance $36B",
            old_event_time=T0,
            new_event_time=T1,
            old_meta=META_NVDA_GUIDANCE,
            new_meta=META_NVDA_GUIDANCE,
        )
        assert relation == "CONFIRMS"
        assert conf >= 0.8

    def test_contradicts_same_time(self):
        relation, conf = classify_relation(
            old_content="NVDA Q3 guidance $36B",
            new_content="NVDA Q3 guidance lowered to $28B",
            old_event_time=T1,
            new_event_time=T1,
            old_meta=META_NVDA_GUIDANCE,
            new_meta=META_NVDA_GUIDANCE,
        )
        assert relation == "CONTRADICTS_SAME_TIME"

    def test_adds_older_event_time(self):
        """New memory is actually older — should not supersede."""
        relation, _ = classify_relation(
            old_content="NVDA Q3 guidance $36B",
            new_content="NVDA earlier guidance $30B",
            old_event_time=T2,
            new_event_time=T0,  # new is earlier!
            old_meta=META_NVDA_GUIDANCE,
            new_meta=META_NVDA_GUIDANCE,
        )
        assert relation == "ADDS"

    def test_supersedes_direction_agnostic(self):
        """Both 'raised to $36B' and 'lowered to $28B' supersede the old $32B fact."""
        for new_content in ["NVDA Q3 guidance raised to $36B", "NVDA Q3 guidance lowered to $28B"]:
            relation, _ = classify_relation(
                old_content="NVDA Q3 guidance $32B",
                new_content=new_content,
                old_event_time=T0,
                new_event_time=T1,
                old_meta=META_NVDA_GUIDANCE,
                new_meta=META_NVDA_GUIDANCE,
            )
            assert relation == "SUPERSEDES", f"Expected SUPERSEDES for: {new_content}"
