from hiremate_ai.agents.generation.posting.criteria import (
    CRITERIA_STEP,
    CRITERIA_SYSTEM,
    CriterionDraft,
    RuleDraft,
    draft_criterion,
)
from hiremate_ai.contract import CriterionCategory, CriterionType, PostingContent
from hiremate_ai.llm.fake import FakeLlm
from hiremate_ai.tools.ncs import unit_by_code

CONTENT = PostingContent(
    title="결제 플랫폼 백엔드 개발자",
    job_category="백엔드 개발",
    employment_type="정규직",
    career="경력 3년 이상",
    location="서울 중구",
    intro="카드 결제와 정산을 처리하는 플랫폼을 함께 만들 백엔드 개발자를 찾습니다.",
    duties=["결제 승인 · 정산 API 개발"],
    qualifications=["Java 서버 개발 경력 3년 이상", "정보처리기사 또는 SQLD 자격증 보유"],
    preferred=["RDBMS 스키마 설계와 SQL 튜닝 경험"],
    benefits=["유연 근무"],
)
SERVER = "2001020211_23v6"
"""서버프로그램 구현"""


def rules(
    kind: CriterionType = CriterionType.SINGLE,
    met: str = "충족",
    partial: str | None = None,
    unmet: str = "미충족",
    certificates: list[str] | None = None,
) -> RuleDraft:
    return RuleDraft(criterion_type=kind, met=met, partial=partial, unmet=unmet, certificates=certificates or [])


async def test_drafts_type_and_rules_for_one_item() -> None:
    llm = FakeLlm(
        rules(
            CriterionType.COMPOSITE,
            met=" 스키마를 본인이 설계하고 SQL을 튜닝했다. ",
            partial="SQL 튜닝만 확인된다.",
            unmet="RDBMS를 다룬 기록이 서류에서 확인되지 않는다.",
        )
    )

    draft = await draft_criterion(llm, CONTENT, CriterionCategory.PREFERENCE, "RDBMS 스키마 설계와 SQL 튜닝 경험", None)

    assert draft == CriterionDraft(
        criterion_type=CriterionType.COMPOSITE,
        met="스키마를 본인이 설계하고 SQL을 튜닝했다.",
        partial="SQL 튜닝만 확인된다.",
        unmet="RDBMS를 다룬 기록이 서류에서 확인되지 않는다.",
        certificates=[],
    )


async def test_composite_without_partial_rule_becomes_single() -> None:
    llm = FakeLlm(rules(CriterionType.COMPOSITE, partial="  "))

    draft = await draft_criterion(llm, CONTENT, CriterionCategory.PREFERENCE, "SQL 튜닝 경험", None)

    assert (draft.criterion_type, draft.partial) == (CriterionType.SINGLE, None)


async def test_partial_rule_is_dropped_for_other_types() -> None:
    llm = FakeLlm(rules(CriterionType.CONDITION, partial="일부만 있다"))

    draft = await draft_criterion(llm, CONTENT, CriterionCategory.QUALIFICATION, "Java 서버 개발 경력 3년 이상", None)

    assert draft.partial is None


async def test_empty_rules_fall_back_to_the_posting_sentence() -> None:
    llm = FakeLlm(rules(met=" ", unmet=""))

    draft = await draft_criterion(llm, CONTENT, CriterionCategory.PREFERENCE, "금융 도메인 경험", None)

    assert draft.met == "서류에서 '금융 도메인 경험'을 확인할 수 있다"
    assert draft.unmet == "서류에서 '금융 도메인 경험'이 확인되지 않는다"


async def test_demanding_endings_become_plain_facts() -> None:
    """서류 평가 AI가 판정할 사실이어야 해서, 요구하는 말로 끝난 기준은 사실을 적는 말로 바꾼다."""
    llm = FakeLlm(
        rules(
            CriterionType.COMPOSITE,
            met="지원 서류에서 SQL 튜닝 경험을 확인할 수 있어야 한다.",
            partial="SQL 튜닝만 서류에서 확인되어야 한다",
            unmet="지원 서류에서 SQL 튜닝 경험이 확인되지 않아야 한다.",
        )
    )

    draft = await draft_criterion(llm, CONTENT, CriterionCategory.PREFERENCE, "RDBMS 스키마 설계와 SQL 튜닝 경험", None)

    assert draft.met == "지원 서류에서 SQL 튜닝 경험을 확인할 수 있다."
    assert draft.partial == "SQL 튜닝만 서류에서 확인된다"
    assert draft.unmet == "지원 서류에서 SQL 튜닝 경험이 확인되지 않는다."


async def test_keeps_only_certificates_named_in_the_item() -> None:
    """'관련 자격증'처럼 이름이 없는 항목에 모델이 지어낸 자격증은 버린다 (규칙 7)."""
    named = FakeLlm(rules(CriterionType.CONDITION, certificates=["정보처리기사", "SQLD", "SQLD", "리눅스마스터"]))
    vague = FakeLlm(rules(CriterionType.CONDITION, certificates=["정보처리기사"]))

    kept = await draft_criterion(
        named, CONTENT, CriterionCategory.QUALIFICATION, "정보처리기사 또는 SQLD 자격증 보유", None
    )
    dropped = await draft_criterion(vague, CONTENT, CriterionCategory.QUALIFICATION, "관련 자격증 보유", None)

    assert kept.certificates == ["정보처리기사", "SQLD"]
    assert dropped.certificates == []


async def test_prompt_shows_posting_item_and_ncs_reference() -> None:
    llm = FakeLlm(rules(), rules())

    await draft_criterion(llm, CONTENT, CriterionCategory.QUALIFICATION, "서버 프로그램 구현 경험", SERVER)
    await draft_criterion(llm, CONTENT, CriterionCategory.PREFERENCE, "금융 도메인 경험", None)

    first, second = (call.user for call in llm.calls)
    unit = unit_by_code(SERVER)
    assert unit is not None
    shared = (
        "지금 공고: 결제 플랫폼 백엔드 개발자 (백엔드 개발, 경력 3년 이상)\n주요 업무:\n- 결제 승인 · 정산 API 개발\n\n"
    )
    assert first.startswith(f"{shared}판정할 자격 요건: 서버 프로그램 구현 경험\n참고 NCS 능력단위 서버프로그램 구현:")
    assert f"  · {unit.elements[0].criteria[0]}" in first
    assert first.endswith(CRITERIA_STEP)
    assert second == f"{shared}판정할 우대 사항: 금융 도메인 경험\n{CRITERIA_STEP}"
    assert all(call.system == CRITERIA_SYSTEM and call.agent == "posting" for call in llm.calls)
