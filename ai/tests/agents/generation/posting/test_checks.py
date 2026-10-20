from hiremate_ai.agents.generation.posting.checks import blocked_terms, problems
from hiremate_ai.agents.generation.posting.reviser import FIELD_LABELS
from hiremate_ai.agents.generation.posting.types import StageDraft
from hiremate_ai.contract import PostingContent, StageType

CONTENT = PostingContent(
    title="백엔드 개발자",
    job_category="백엔드 개발",
    employment_type="정규직",
    career="경력 3년 이상",
    location="서울",
    intro="",
    duties=["API 개발"],
    qualifications=["Java 경력 3년 이상"],
    preferred=["금융 도메인 경험"],
    benefits=["유연 근무"],
)


def check(content: PostingContent, changed: list[str], stages: list[StageDraft] | None = None) -> list[str]:
    return problems(content, changed, stages, FIELD_LABELS, source="HR 요청: 고쳐 줘")


def test_problems_passes_clean_changes() -> None:
    assert check(CONTENT, ["title", "preferred"]) == []


def test_problems_checks_only_changed_fields() -> None:
    content = CONTENT.model_copy(update={"duties": ["사內 API 개발"]})

    assert check(content, ["preferred"]) == []
    assert check(content, ["duties"]) == ["주요 업무에 한국어가 아닌 문자(한자, 일본어)를 썼다: 內"]


def test_problems_finds_length_and_count_limits() -> None:
    content = CONTENT.model_copy(update={"location": "가" * 101, "preferred": ["경험"] * 31, "benefits": ["가" * 101]})

    assert check(content, ["location", "preferred", "benefits"]) == [
        "근무지 칸이 100자를 넘는다",
        "우대 사항 항목이 30개를 넘는다",
        "복지 항목 하나가 100자를 넘는다",
    ]


def test_problems_finds_blank_title_even_when_unchanged() -> None:
    assert check(CONTENT.model_copy(update={"title": ""}), []) == ["채용명이 비어 있다"]


def test_problems_finds_money_not_in_source() -> None:
    content = CONTENT.model_copy(update={"benefits": ["연봉 6,000만 원", "식대 20만원"]})

    found = problems(content, ["benefits"], None, FIELD_LABELS, source="HR 요청: 식대 20만 원 넣어 줘")

    assert found == ["복지에 주어진 정보에 없는 금액을 썼다: 6,000만 원"]


def test_problems_finds_stage_mistakes() -> None:
    stages = [
        StageDraft(name="면접", type=StageType.INTERVIEW),
        StageDraft(name="면접", type=StageType.INTERVIEW),
        StageDraft(name="", type=StageType.DOCUMENT),
        StageDraft(name="가" * 51, type=StageType.ASSESSMENT),
    ]

    assert check(CONTENT, [], stages) == [
        "이름이 빈 전형이 있다",
        "전형 이름이 50자를 넘는다",
        "같은 이름의 전형이 여러 번 있다: 면접",
    ]
    assert check(CONTENT, [], []) == ["전형이 하나도 없다"]


def test_blocked_terms_look_only_at_changed_judged_fields() -> None:
    content = CONTENT.model_copy(
        update={"preferred": ["30세 이하", "남성 우대"], "qualifications": ["미혼자"], "location": "지역 무관"}
    )

    assert blocked_terms(content, ["preferred", "qualifications", "location"]) == ["미혼", "30세", "남성"]
    assert blocked_terms(content, ["location"]) == []
