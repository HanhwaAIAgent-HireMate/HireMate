from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from hiremate_ai.agents.analysis.application.router import get_artifacts, get_store
from hiremate_ai.agents.analysis.application.table import (
    _Factor,
    _Factors,
    _Judgment,
    _Judgments,
    _Labels,
    check_factors,
    check_labels,
    company_factors,
    check_talents,
    feature_labels,
    judge_talents,
    short_label,
)
from hiremate_ai.agents.analysis.application.types import (
    Actor,
    ApplicationReview,
    DocumentSection,
    Fact,
    Quote,
)
from hiremate_ai.contract import DocumentType, Talent, TalentFit, TalentLevel
from hiremate_ai.llm.client import get_llm
from hiremate_ai.llm.fake import FakeLlm
from hiremate_ai.main import app

APPLICATION = uuid4()
TALENTS = [Talent(title="협업을 중요시한다", description=""), Talent(title="고객 신뢰", description="책임감")]


def quote(sentence: str) -> Quote:
    return Quote(document=DocumentType.RESUME, sentence=sentence)


def review(*facts: Fact, sections: list[DocumentSection] | None = None) -> ApplicationReview:
    return ApplicationReview(
        version="1",
        input_hash="hash-1",
        application_id=APPLICATION,
        readable=True,
        facts=list(facts),
        sections=sections or [],
    )


SELF = Fact(
    kind="EXPERIENCE",
    statement="타 팀과 API 명세를 조율했다",
    actor=Actor.SELF,
    quotes=[quote("타 팀과 API 명세를 조율")],
)
TEAM = Fact(
    kind="PROJECT", statement="결제 장애 대응 TF에 참여했다", actor=Actor.TEAM, quotes=[quote("결제 장애 대응 TF 참여")]
)
REJECTED = Fact(kind="EXPERIENCE", statement="고객 VOC를 직접 처리했다", actor=Actor.SELF, quotes=[], supported=False)


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("인성을 중요시한다", "인성"),
        ("인성", "인성"),
        ("고객 신뢰를 최우선으로", "고객 신뢰"),
        ("정보처리기사 보유자", "정보처리기사"),
        ("대용량 트래픽 환경에서 장애 대응 경험", "대용량 트래픽 환경에서 장애"),
        ("Java 또는 Kotlin 기반 서버 개발 경력 3년 이상", "Java 또는 Kotlin"),
        ("Kafka 또는 RabbitMQ 운영 경험", "Kafka"),
        ("Spring Boot로 REST API를 개발 · 운영한 경험", "Spring Boot"),
    ],
)
def test_short_label_drops_endings_and_cuts_on_words(text: str, label: str) -> None:
    assert short_label(text) == label


def test_labels_fall_back_per_text_when_answer_does_not_fit() -> None:
    texts = ["인성을 중요시한다", "협업", "Java/Spring 기반 백엔드 개발 경력 3년 이상"]

    checked = check_labels(texts, ["인성", "협업", "아주 길어서 열 이름으로 쓸 수 없는 키워드"])

    assert checked[:2] == ["인성", "협업"]
    assert checked[2] == short_label(texts[2])
    # 개수가 다르면 전부 잘라 만든다
    assert check_labels(texts, ["인성"]) == [short_label(text) for text in texts]


def test_labels_never_repeat() -> None:
    assert len(set(check_labels(["협업", "협업 능력"], ["협업", "협업"]))) == 2


async def test_labels_are_asked_once_per_text_set() -> None:
    llm = FakeLlm(_Labels(labels=["소통", "끈기"]))
    texts = [f"소통을 중요시한다 {uuid4()}", "끈기"]

    first = await feature_labels(llm, texts)
    second = await feature_labels(llm, texts)

    assert first == second == ["소통", "끈기"]
    assert len(llm.calls) == 1


CULTURE = "결제 플랫폼을 만듭니다. 무엇보다 인성을 중요시합니다. 실패를 두려워하지 않고 도전하는 분을 환영합니다."


def test_factors_keep_only_quotes_found_in_the_text() -> None:
    factors = check_factors(
        CULTURE,
        [
            ("인성", "무엇보다 인성을 중요시합니다."),
            ("성실", "성실한 사람을 찾습니다."),  # 글에 없는 문장
            ("", "실패를 두려워하지 않고 도전하는 분을 환영합니다."),
            ("인성", "무엇보다  인성을 중요시합니다."),  # 겹치는 이름
        ],
    )

    assert [item.title for item in factors.items] == ["인성", "실패를 두려워하지 않고"]
    assert factors.items[0].description == "무엇보다 인성을 중요시합니다."


async def test_factors_are_asked_once_and_blank_text_skips_the_model() -> None:
    llm = FakeLlm(_Factors(items=[_Factor(title="도전", quote="실패를 두려워하지 않고 도전하는 분을 환영합니다.")]))
    text = f"{CULTURE} {uuid4()}"

    first = await company_factors(llm, text)
    second = await company_factors(llm, text)
    blank = await company_factors(llm, "  ")

    assert first == second
    assert [item.title for item in first.items] == ["도전"]
    assert blank.items == []
    assert len(llm.calls) == 1


def test_talent_judgment_needs_a_real_source_and_own_work_for_high() -> None:
    saved = review(SELF, TEAM, REJECTED)
    judgments = [
        _Judgment(number=1, level=TalentLevel.HIGH, source="F2", evidence="장애 대응 TF", reason="TF 참여"),
        _Judgment(number=2, level=TalentLevel.HIGH, source="F3", evidence="VOC 처리", reason="고객 응대"),
    ]

    items = check_talents(saved, TALENTS, judgments)

    # 팀 성과에는 상을 주지 않는다
    assert (items[0].level, items[0].quote) == (TalentLevel.MID, "결제 장애 대응 TF 참여")
    # 검토를 통과하지 못한 경험은 근거가 될 수 없다
    assert items[1].level is TalentLevel.UNKNOWN


def test_missing_or_unknown_source_is_unknown() -> None:
    saved = review(SELF)
    judgments = [_Judgment(number=1, level=TalentLevel.LOW, source="F9", evidence="", reason="언급")]

    items = check_talents(saved, TALENTS, judgments)

    assert [item.level for item in items] == [TalentLevel.UNKNOWN, TalentLevel.UNKNOWN]
    assert [item.title for item in items] == [talent.title for talent in TALENTS]


def test_section_source_is_at_most_mid() -> None:
    section = DocumentSection(document=DocumentType.COVER_LETTER, title="협업", summary="갈등을 조율한 경험을 썼다")
    judgments = [_Judgment(number=1, level=TalentLevel.HIGH, source="s1", evidence="팀 갈등 조율", reason="사례")]

    items = check_talents(review(sections=[section]), TALENTS[:1], judgments)

    assert (items[0].level, items[0].evidence) == (TalentLevel.MID, "팀 갈등 조율")


async def test_no_saved_analysis_is_all_unknown_without_model() -> None:
    llm = FakeLlm()

    fit = await judge_talents(llm, None, TALENTS)

    assert [item.level for item in fit.items] == [TalentLevel.UNKNOWN] * 2
    assert llm.calls == []


class MemoryReviews:
    def __init__(self, saved: ApplicationReview | None) -> None:
        self.saved = saved

    async def latest(self, application_id: UUID, *, company_id: UUID, recruitment_id: UUID) -> ApplicationReview | None:
        return self.saved


class MemoryArtifacts:
    def __init__(self) -> None:
        self.fits: dict[str, TalentFit] = {}

    async def find_talents(self, *, source_hash: str, recipe_hash: str, **_: UUID) -> TalentFit | None:
        return self.fits.get(source_hash + recipe_hash)

    async def save_talents(self, fit: TalentFit, *, source_hash: str, recipe_hash: str, **_: UUID) -> None:
        self.fits[source_hash + recipe_hash] = fit


@pytest.fixture
def artifacts() -> Iterator[MemoryArtifacts]:
    memory = MemoryArtifacts()
    app.dependency_overrides[get_store] = lambda: MemoryReviews(review(SELF))
    app.dependency_overrides[get_artifacts] = lambda: memory
    yield memory
    app.dependency_overrides.clear()


def test_talents_endpoint_reuses_saved_judgment(artifacts: MemoryArtifacts) -> None:
    llm = FakeLlm(
        _Judgments(
            items=[
                _Judgment(
                    number=1, level=TalentLevel.HIGH, source="F1", evidence="타 팀 API 명세 조율", reason="직접 조율"
                )
            ]
        )
    )
    app.dependency_overrides[get_llm] = lambda: llm
    request = {
        "companyId": str(uuid4()),
        "recruitmentId": str(uuid4()),
        "applicationId": str(APPLICATION),
        "talents": [talent.model_dump(mode="json") for talent in TALENTS],
    }
    client = TestClient(app)

    first = client.post("/agents/candidate-analyst/talents", json=request)
    second = client.post("/agents/candidate-analyst/talents", json=request)

    assert first.status_code == 200
    items = first.json()["items"]
    assert [item["level"] for item in items] == ["HIGH", "UNKNOWN"]
    assert items[0]["quote"] == "타 팀과 API 명세를 조율"
    assert second.json() == first.json()
    assert len(llm.calls) == 1
