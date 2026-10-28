from uuid import uuid4

from hiremate_ai.agents.root.ledger import Ledger

A = uuid4()
B = uuid4()


def test_same_evidence_keeps_one_number_and_lower_cap() -> None:
    ledger = Ledger()
    first = ledger.add(A, "Kafka 운영", quote="Kafka 클러스터를 운영했다.", source="이력서", cap="OK")
    again = ledger.add(A, "Kafka 운영", quote="Kafka 클러스터를 운영했다.", source="이력서", cap="CHECK")
    other = ledger.add(B, "Kafka 운영", source="이력서", cap="OK")

    assert (first, again, other) == ("E1", "E1", "E2")
    found = ledger.get("E1")
    assert found is not None and found.cap == "CHECK"


def test_line_shows_cap_quote_and_source() -> None:
    ledger = Ledger()
    ref = ledger.add(A, "Kafka 운영", quote="Kafka 클러스터를 운영했다.", source="이력서", cap="OK")
    plain = ledger.add(None, "지원자 8명", source="전형 결과", cap="CHECK")

    assert ledger.line(ref) == 'E1 [근거 확인] Kafka 운영 — 근거: "Kafka 클러스터를 운영했다." (이력서)'
    assert ledger.line(plain) == "E2 [확인 필요] 지원자 8명 (전형 결과)"


def test_unknown_ref_is_none() -> None:
    assert Ledger().get("E9") is None
