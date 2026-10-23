from uuid import uuid4

import httpx
import pytest

from hiremate_ai.agents.analysis.application.router import get_store
from hiremate_ai.agents.analysis.application.types import (
    Actor,
    ApplicationReview,
    CriterionResult,
    Fact,
    Level,
    Note,
    PreferenceResult,
    PreferenceStatus,
    QualificationResult,
    Quote,
)
from hiremate_ai.agents.analysis.interview.agent import AnswerReading
from hiremate_ai.agents.generation.interview.agent import (
    CHECK,
    CLAIM,
    FINAL_SLOTS,
    INTRO,
    NOTABLE,
    PREFERRED,
    REQUIRED,
    QuestionDraft,
    generate_questions,
    load_review,
    review_gaps,
    summary_gaps,
)
from hiremate_ai.agents.generation.interview.router import (
    InterviewQuestion,
    InterviewView,
    PreviousInterview,
    QuestionSource,
)
from hiremate_ai.contract import (
    ApplicantDetail,
    CandidateAnalysis,
    CompanyProfile,
    Condition,
    DocumentType,
    Finding,
    PostingContent,
)
from hiremate_ai.llm.client import get_llm
from hiremate_ai.llm.fake import FakeLlm, LlmCall
from hiremate_ai.main import app


@pytest.fixture
def newcomer_analysis(sample_posting: PostingContent) -> CandidateAnalysis:
    """이도윤(신입): 경력 3년 이상 요건 미충족, 모의 결제 프로젝트는 눈여겨볼 점 (tests/samples/README.md)."""
    required, rdbms = sample_posting.qualifications
    return CandidateAnalysis(
        conditions=[
            Condition(label="Java·Spring", met=False, requirement=required),
            Condition(label="RDBMS", met=True, requirement=rdbms),
            Condition(label="금융", met=False, requirement=sample_posting.preferred[0]),
        ],
        notable=[
            Finding(
                text="Spring Boot와 MySQL로 결제 승인 · 취소 API를 만들고 JUnit으로 테스트했습니다.", source="이력서"
            )
        ],
        checks=[Finding(text=f'"{required}"의 근거가 제출 문서에 없어요.', source="공고 · 자격 요건")],
        holds=[],
        fit=[],
        highlights=[],
        agent="Application Agent",
        stub=False,
    )


def view(*previous: PreviousInterview, questions: list[InterviewQuestion] | None = None) -> InterviewView:
    return InterviewView(application_id=uuid4(), schedule=None, questions=questions or [], previous=list(previous))


def draft(call: LlmCall, *, bad: bool = False, sid: str = "S1") -> QuestionDraft:
    """user 프롬프트에 나온 gap_id마다 서로 다른 질문을 하나씩 쓴다."""
    gap_ids = [line.split("gap_id: ")[1].split(" |")[0] for line in call.user.splitlines() if "gap_id: " in line]
    texts = [
        "서버 개발 경험이 있다면 맡았던 기능과 결과를 말해 주세요.",
        "금융 서비스를 다뤄 본 적이 있다면 어떤 데이터를 처리했는지 설명해 주세요.",
        "대용량 요청을 처리하며 겪은 병목과 해결 과정을 들려주세요.",
    ]
    bad_text = "결혼 계획이 있으신가요? 업무 몰입에 영향이 없는지 말해 주세요."
    questions = []
    for i, gap_id in enumerate(gap_ids):
        questions.append({"gap_id": gap_id, "question": bad_text if bad else texts[i % len(texts)]})
    # 최종면접이면 프롬프트에 적힌 자리(- VALUES (…)…)마다 그 주제의 열린 질문을 하나씩 쓴다
    slot_texts = {
        "VALUES": "일하면서 가장 중요하게 지켜 온 원칙이 드러났던 경험이 있다면, 그때 한 선택을 말해 주세요.",
        "CULTURE": "동료와 일하는 방식이 달랐던 경험이 있다면, 어떻게 소통하며 맞춰 갔는지 말해 주세요.",
        "LEADERSHIP": "여러 사람의 의견을 모아 결정을 이끈 경험이 있다면, 그때 맡은 역할을 말해 주세요.",
        "MOTIVE": "결제 플랫폼 개발 직무에 지원하게 된 계기를 실제 경험과 함께 말해 주세요.",
    }
    slot_picks = []
    for line in call.user.splitlines():
        key = line[2:].split(" (")[0] if line.startswith("- ") else ""
        if key in slot_texts:
            slot_picks.append({"slot": key, "question": bad_text if bad else slot_texts[key]})
    return QuestionDraft.model_validate(
        {
            "questions": questions,
            "free_pick": {
                "sid": sid,
                "question": "모의 결제 API를 테스트할 때 어떤 경우를 먼저 검증했는지 말해 주세요.",
            },
            "slot_picks": slot_picks,
        }
    )


async def test_required_gap_comes_first_and_free_pick_is_last(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent, newcomer_analysis: CandidateAnalysis
) -> None:
    llm = FakeLlm(draft)

    questions = await generate_questions(
        llm,
        applicant=sample_applicants["이도윤"],
        posting=sample_posting,
        analysis=newcomer_analysis,
        interview=view(),
        focus=None,
    )

    assert len(questions) == 4
    assert questions[0] == INTRO  # 맨 앞은 1분 자기소개 ('공통' 표시 없이 일반 질문)
    assert questions[1].startswith("서버 개발 경험")  # 필수 조건 근거 없음 빈틈의 질문
    assert questions[-1].startswith("모의 결제 API")  # 이 사람만의 확인 포인트
    [call] = llm.calls
    assert "필수 조건 근거 없음" in call.user.splitlines()[1]
    assert '<data kind="documents"' in call.user
    assert "한결대학교" not in call.user  # 학력 줄은 질문 소재로 넘기지 않는다


async def test_document_headers_are_not_question_material(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent, newcomer_analysis: CandidateAnalysis
) -> None:
    applicant = sample_applicants["이도윤"]
    header = f"{applicant.info.name} | 금융권 백엔드 개발자 (Java/Spring) | 경력 7년"
    marker = "SYNTHETIC SAMPLE - 채용 AI 시스템 테스트용 가상 문서"
    job_label = "경력 지원직무 금융권 백엔드 개발자"
    documents = [
        document.model_copy(update={"text": header + "\n" + marker + "\n" + job_label + "\n" + document.text})
        for document in applicant.documents
    ]
    analysis = newcomer_analysis.model_copy(
        update={"notable": [Finding(text=header, source="이력서"), Finding(text=marker, source="자기소개서")]}
    )
    llm = FakeLlm(draft)

    questions = await generate_questions(
        llm,
        applicant=applicant.model_copy(update={"documents": documents}),
        posting=sample_posting,
        analysis=analysis,
        interview=view(),
        focus=None,
    )

    assert questions[0] == INTRO
    assert all(header not in call.user and marker not in call.user for call in llm.calls)
    assert all(job_label not in call.user for call in llm.calls)
    assert not any(applicant.info.name + " |" in question or "SYNTHETIC SAMPLE" in question for question in questions)


async def test_discriminatory_question_is_rewritten_then_replaced_by_template(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent, newcomer_analysis: CandidateAnalysis
) -> None:
    llm = FakeLlm(lambda call: draft(call, bad=True), lambda call: draft(call, bad=True))

    questions = await generate_questions(
        llm,
        applicant=sample_applicants["이도윤"],
        posting=sample_posting,
        analysis=newcomer_analysis,
        interview=view(),
        focus=None,
    )

    assert len(llm.calls) == 2  # 걸린 이유를 알려 주고 한 번 더 썼다
    assert "결혼" in llm.calls[1].user.split("fix_errors: ")[1]
    assert all("결혼" not in text for text in questions)
    assert "Java · Spring Boot" in questions[1]  # 템플릿 질문 (0번은 자기소개)


async def test_previous_unconfirmed_answer_becomes_follow_up(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent, newcomer_analysis: CandidateAnalysis
) -> None:
    first = PreviousInterview(
        stage_id=uuid4(),
        stage_name="1차 실무면접",
        schedule=None,
        questions=[
            InterviewQuestion(
                question_id=uuid4(),
                text="모의 결제 서비스에서 본인 역할은?",
                source=QuestionSource.AI,
                answer="열심히 했어요.",
            )
        ],
    )
    answers = AnswerReading.model_validate(
        {"results": [{"no": 1, "status": "NOT_CONFIRMED", "unconfirmed": ["취소 API를 설계한 본인 판단"]}]}
    )
    llm = FakeLlm(answers, draft)

    questions = await generate_questions(
        llm,
        applicant=sample_applicants["이도윤"],
        posting=sample_posting,
        analysis=newcomer_analysis,
        interview=view(first),
        focus="1차에서 확인 안 된 부분 중심으로",
    )

    assert [call.output.__name__ for call in llm.calls] == ["AnswerReading", "QuestionDraft"]
    gap_lines = [line for line in llm.calls[1].user.splitlines() if "gap_id: " in line]
    assert "이전 면접에서 확인 안 됨" in gap_lines[0]
    assert "취소 API를 설계한 본인 판단" in gap_lines[0]
    # 이전 면접 기록이 있으면 최종면접 구성: 자기소개 + ① 1차 미확인 + ②~⑤ 자리
    assert len(questions) == 2 + len(FINAL_SLOTS)
    assert questions[0] == INTRO
    assert "slot_picks: 요청함" in llm.calls[1].user


async def test_invalid_free_pick_falls_back_to_next_gap(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent, newcomer_analysis: CandidateAnalysis
) -> None:
    llm = FakeLlm(lambda call: draft(call, sid="S999"), lambda call: draft(call, sid="S999"))

    questions = await generate_questions(
        llm,
        applicant=sample_applicants["이도윤"],
        posting=sample_posting,
        analysis=newcomer_analysis,
        interview=view(),
        focus=None,
    )

    assert len(questions) == 4
    assert not any(text.startswith("모의 결제 API") for text in questions)
    assert "S999" in llm.calls[1].user


async def test_skips_questions_already_on_the_card(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent, newcomer_analysis: CandidateAnalysis
) -> None:
    existing = InterviewQuestion(
        question_id=uuid4(),
        text="모의 결제 API를 테스트할 때 어떤 경우를 먼저 검증했는지 말해 주세요.",
        source=QuestionSource.MANUAL,
        answer="",
    )
    llm = FakeLlm(draft, draft)

    questions = await generate_questions(
        llm,
        applicant=sample_applicants["이도윤"],
        posting=sample_posting,
        analysis=newcomer_analysis,
        interview=view(questions=[existing]),
        focus=None,
    )

    assert existing.text not in questions


async def test_blocked_focus_is_ignored(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent, newcomer_analysis: CandidateAnalysis
) -> None:
    llm = FakeLlm(draft)

    await generate_questions(
        llm,
        applicant=sample_applicants["이도윤"],
        posting=sample_posting,
        analysis=newcomer_analysis,
        interview=view(),
        focus="나이 많은 지원자는 체력 위주로",
    )

    assert "hr_focus: -" in llm.calls[0].user


async def test_questions_route(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent, newcomer_analysis: CandidateAnalysis
) -> None:
    app.dependency_overrides[get_llm] = lambda: FakeLlm(draft)
    app.dependency_overrides[get_store] = lambda: ReviewOnly(None)  # 상세 판정 저장소를 메모리로 (DB 없이)
    body = {
        "applicant": sample_applicants["이도윤"].model_dump(mode="json"),
        "posting": sample_posting.model_dump(mode="json"),
        "analysis": newcomer_analysis.model_dump(mode="json"),
        "interview": view().model_dump(mode="json"),
        "focus": None,
    }
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/agents/interview/questions", json=body)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert len(response.json()) == 4  # 1분 자기소개 + 3개


def test_similar_ignores_shared_template_wording() -> None:
    """주제가 다른 두 템플릿 질문은 문장 틀이 같아도 중복이 아니다 (데모에서 질문이 2개만 남던 문제)."""
    from hiremate_ai.agents.generation.interview.agent import NOTABLE, TEMPLATES, _similar

    a = TEMPLATES[NOTABLE].format(topic="서버프로그램 구현")
    b = TEMPLATES[NOTABLE].format(topic="인터페이스 구현")
    assert not _similar(a, b)
    # 같은 주제를 조금 다르게 쓴 질문은 여전히 중복으로 잡는다
    same = TEMPLATES[NOTABLE].format(topic="서버 프로그램 구현")
    assert _similar(a, same)


def test_style_problem_catches_habits_of_small_models() -> None:
    """실제 7.8B 모델 출력에서 나온 문제들: 질문 여러 개, 면접에서 안 한 말 전제, 내부 판단 노출, 경험 전제."""
    from hiremate_ai.agents.generation.interview.agent import NOTABLE, REQUIRED, _style_problem

    two_asks = "중복 결제 방지 설계에서 맡은 부분을 설명해 주실 수 있나요? 특히, 추적 방식도 말씀해 주세요."
    presumed = "이전에 언급한 중복 결제 방지 시스템에서 본인이 맡은 부분을 말해 주세요."
    judgment = "Java 경력이 현재 0년으로 공고에서 요구하는 3년에 부족합니다. 관련 경험이 있다면 말해 주세요."
    closed = "Java와 Spring으로 백엔드를 개발한 경험에 대해 자세히 설명해 주세요."
    assert _style_problem(two_asks, NOTABLE)
    assert _style_problem(presumed, NOTABLE)
    assert _style_problem(judgment, REQUIRED)
    assert _style_problem(closed, REQUIRED)
    assert _style_problem("서류에 Java 경험이 명시되어 있지 않은데, 관련 경험이 있다면 말해 주세요.", REQUIRED)
    assert _style_problem("역할별 접근 테스트를 통합 테스트로 확장한 경험이 있으신가요?", NOTABLE)
    assert _style_problem("백엔드를 담당하셨다고 말씀하셨는데 맡은 기능을 설명해 주세요.", NOTABLE)
    assert (
        _style_problem("Java와 Spring으로 백엔드를 개발해 본 경험이 있다면, 맡은 일과 결과를 말해 주세요.", REQUIRED)
        is None
    )


def test_extra_ask_is_trimmed_to_the_first_question() -> None:
    """두 번째 질문을 덧붙였으면 버리지 않고 첫 질문만 살린다. 출처 표시도 지운다."""
    from hiremate_ai.agents.generation.interview.agent import NOTABLE, _checked

    text = (
        "'[자기소개서] 거래 키로 중복 호출을 구별하는 방식'을 실제로 적용한 사례를 설명해 주실 수 있나요? "
        "특히 그 과정의 어려움도 말씀해 주세요."
    )
    kept, problem = _checked(text, NOTABLE, [])
    assert problem is None
    assert kept == "'거래 키로 중복 호출을 구별하는 방식'을 실제로 적용한 사례를 말해 주세요."


def test_filler_is_removed_before_the_length_check() -> None:
    """실제 모델 출력처럼 앞머리 · 채움말 · 긴 끝맺음 때문에 140자를 넘던 질문을 줄여서 살린다."""
    from hiremate_ai.agents.generation.interview.agent import NOTABLE, STYLE_MAX_LENGTH, _checked

    text = (
        "서버 프로그램 구현 경험 중에서, '중복 결제 방지 멱등키 및 거래 로그 추적 설계'와 같은 구체적인 설계나 구현 "
        "사례를 통해 어떻게 시스템의 안정성과 효율성을 향상시켰고, 운영 환경에서 어떤 문제를 해결해 어떤 결과를 "
        "가져왔는지 구체적인 사례와 함께 자세히 설명해 주실 수 있을까요?"
    )
    assert len(text) > STYLE_MAX_LENGTH
    kept, problem = _checked(text, NOTABLE, [])
    assert problem is None
    assert kept is not None
    assert kept.startswith("'중복 결제 방지")
    assert kept.endswith("말해 주세요.")


def test_same_quote_or_same_numbers_count_as_repeat() -> None:
    """다른 질문이 이미 인용한 문장, 또는 같은 숫자 성과를 다른 말로 인용하면 중복으로 본다."""
    from hiremate_ai.agents.generation.interview.agent import _problem

    first = "'재현 가능한 부하 조건을 만든 뒤 처리량을 1,200 TPS에서 3,400 TPS로 높임'에서 맡은 부분을 말해 주세요."
    again = "'모의 주문 부하 테스트 1,200→3,400 TPS 개선'에서 측정 방법을 어떻게 정했는지 말해 주세요."
    other = "'주문 이벤트 순서 보장 로직 작성'에서 순서가 틀어진 경우를 어떻게 찾았는지 말해 주세요."
    assert _problem(again, [first]) == "다른 질문이 이미 인용한 서류 문장을 또 인용함"
    assert _problem(other, [first]) is None


def test_gap_label_written_instead_of_id_is_mapped() -> None:
    """모델이 gap_id 자리에 빈틈 이름을 쓰면, 이름과 topic이 맞는 열린 빈틈으로 맞춘다."""
    from hiremate_ai.agents.generation.interview.agent import CHECK, REQUIRED, Gap, _resolve_gap_id

    gaps = [
        Gap(gap_id="G1", kind=REQUIRED, topic="Java, Spring", note=""),
        Gap(gap_id="G2", kind=CHECK, topic="서버 프로그램 구현", note=""),
        Gap(gap_id="G3", kind=CHECK, topic="데이터 입출력 구현", note=""),
    ]
    open_ids = {"G1", "G2", "G3"}
    assert _resolve_gap_id("G2", gaps, open_ids) == "G2"
    assert _resolve_gap_id("필수 조건 근거 없음", gaps, open_ids) == "G1"
    assert _resolve_gap_id("확인 필요 (데이터 입출력 구현)", gaps, open_ids) == "G3"
    assert _resolve_gap_id("확인 필요", gaps, open_ids) is None
    assert _resolve_gap_id("확인 필요", gaps, {"G2"}) == "G2"
    assert _resolve_gap_id("필수 조건 근거 없음 (기술)", gaps, open_ids) == "G1"


def test_trimming_keeps_the_one_good_question() -> None:
    """실제 7.8B 출력: 판단 문장 + 질문, 막연한 질문 + '특히' 질문, 한 문장 안의 '특히'를 살리거나 그대로 둔다."""
    from hiremate_ai.agents.generation.interview.agent import CHECK, NOTABLE, _checked, _style_problem

    scored = (
        "기술 역량 평가에서 기술 영역에 대한 점수가 다소 낮게 나왔습니다. 특히, 실제 프로젝트에서 복잡한 시스템 오류를 "
        "진단하고 해결한 경험이나, 보안 관련 이슈를 어떻게 처리했는지 구체적인 사례를 들어 설명해 주실 수 있을까요?"
    )
    vague = (
        "데이터 입출력 구현 경험에 대해 말씀해 주시겠습니까? 특히, 논리 데이터 저장소 확인이나 물리 데이터 저장소 "
        "설계 과정에서 직면한 특정 도전 과제와 그 해결 방안을 구체적으로 설명해 주실 수 있나요?"
    )
    refers = (
        "결제 시스템을 개발하셨습니다. 이 프로젝트에서 어떤 장애를 겪었는지 말해 주세요. 또한, 그 결과도 알려 주세요."
    )
    assert _checked(scored, CHECK, []) == (
        "실제 프로젝트에서 복잡한 시스템 오류를 진단하고 해결한 경험이나, "
        "보안 관련 이슈를 어떻게 처리했는지 말해 주세요.",
        None,
    )
    assert _checked(vague, CHECK, [])[0] == (
        "논리 데이터 저장소 확인이나 물리 데이터 저장소 설계 과정에서 "
        "직면한 특정 도전 과제와 그 해결 방안을 말해 주세요."
    )
    assert (
        _checked(refers, NOTABLE, [])[0]
        == "결제 시스템을 개발하셨습니다. 이 프로젝트에서 어떤 장애를 겪었는지 말해 주세요."
    )
    inside = "주문 장애율을 낮출 때 취한 방법 중 특히 기억에 남는 사례에서 어떤 결정을 내렸는지 말해 주세요."
    assert _style_problem(inside, NOTABLE) is None
    assert _style_problem("'[서버프로그램 구현]'에서 공통 모듈을 어떻게 만들었는지 말해 주세요.", NOTABLE)
    assert _style_problem(
        "논리 데이터 저장소와 물리 데이터 저장소 설계 시 고려해야 할 주요 요소를 설명해 주세요.", CHECK
    )
    assert _style_problem("주문 시스템을 설계하실 때 고려해야 할 요소를 어떻게 정하셨는지 말해 주세요.", CHECK) is None


def test_notable_quote_keeps_the_applicants_own_action() -> None:
    """긴 문장은 앞(문제 상황)이 아니라 본인이 한 일이 적힌 절을 인용하고, 역할이 적혀 있으면 역할을 또 묻지 않는다."""
    from hiremate_ai.agents.generation.interview.agent import NOTABLE, Gap, _quote_part, _template

    text = (
        "장 시작 직후 몇 분 동안 몰리는 요청을 견디지 못해 알림이 늦게 도착하는 문제가 있었고, "
        "저는 동기 호출로 묶여 있던 알림 발송을 큐 기반 비동기 구조로 바꾸는 작업을 직접 설계했습니다."
    )
    topic = _quote_part(text)
    assert topic == "동기 호출로 묶여 있던 알림 발송을 큐 기반 비동기 구조로 바꾸는 작업을 직접 설계했습니다"
    question = _template(Gap("G1", NOTABLE, topic, "", [text]))
    assert "본인이 맡은 역할" not in question
    assert question.startswith(f"'{topic}'라고 적어 주셨는데, 그 방법을 고른 이유")
    plain = _template(Gap("G2", NOTABLE, _quote_part("정기 결제 재시도 로직을 고쳐 이탈률을 낮춤"), "", ["x"]))
    assert plain.startswith("'정기 결제 재시도 로직을 고쳐 이탈률을 낮춤'이라고")


def test_generic_or_repeated_questions_are_caught() -> None:
    """실제 4회차 결과: 평가 항목만 늘어놓은 질문, 같은 말로 시작하는 질문, '언급해 주시지 않았습니다'."""
    from hiremate_ai.agents.generation.interview.agent import CHECK, PREFERRED, _checked

    evidence = ["재현 가능한 부하 조건을 만든 뒤 주문 처리량을 1,200 TPS에서 3,400 TPS로 높였습니다."]
    generic = (
        "개발 환경 구축이나 공통 모듈 구현 과정에서 성능 최적화를 위해 어떤 기술적 접근법을 사용했는지 말해 주세요."
    )
    grounded = "부하 테스트에서 주문 처리량을 높일 때 병목을 어떻게 찾았는지 말해 주세요."
    assert _checked(generic, CHECK, [], evidence)[0] is None
    assert _checked(grounded, CHECK, [], evidence)[0] == grounded
    first = "가상 인터넷뱅킹 프로젝트에서 이체 한도 검증 로직을 구현하며 직면한 기술적 도전과 해결 과정을 말해 주세요."
    second = "가상 인터넷뱅킹 프로젝트에서 이체 한도 검증 로직을 구현하면서 찾은 경계값 테스트 사례를 말해 주세요."
    assert _checked(second, CHECK, [first])[0] is None
    told = "대용량 트랜잭션 경험에 대해 언급해 주시지 않았는데, 관련 경험이 있다면 맡은 일을 말해 주세요."
    assert _checked(told, PREFERRED, [])[0] is None
    assert _checked("'공통 모듈 구현하기'에서 어떤 기술 스택을 썼는지 말해 주세요.", CHECK, [])[0] is None
    both = "멱등키 설계를 어떻게 구현하셨는지 설명해 주시고, 그 설계가 어떤 영향을 미쳤는지 말씀해 주세요."
    assert _checked(both, CHECK, [])[0] is None
    lacking = "Spring 트랜잭션 처리 경험이 부족하다는 점을 고려할 때, 배치 작업에서 겪은 문제를 말해 주세요."
    assert _checked(lacking, CHECK, [])[0] is None
    years = "Java 개발 경험이 있다면, 특히 3년 이상의 경력 중에서 시스템을 개선한 사례를 말해 주세요."
    assert _checked(years, PREFERRED, [])[0] is None
    what_if = "웹훅 중복 처리 문제를 다른 기술 스택에서 어떻게 해결할 수 있을지 제안해 주세요."
    assert _checked(what_if, CHECK, [])[0] is None
    assert _checked("저는 테스트를 먼저 보강했습니다.' 사례에서 어떻게 합의했는지 말해 주세요.", CHECK, [])[0] is None


def test_same_experience_asked_twice_is_caught() -> None:
    """인용 없이 같은 경험을 다른 말로 두 번 물으면 잡는다. 이전 면접을 이어 묻는 FOLLOW_UP 은 예외."""
    from hiremate_ai.agents.generation.interview.agent import FOLLOW_UP, NOTABLE, _checked

    first = "알림 발송 시스템을 동기 호출에서 큐 기반 비동기 구조로 변경한 과정과 그 변화로 인한 성과를 말해 주세요."
    second = (
        "알림 발송 시스템의 성능 문제를 해결하기 위해 동기 호출 방식에서 큐 기반 비동기 구조로 전환한 경험이 있다면, "
        "구현 과정을 말해 주세요."
    )
    other = "가상 인터넷뱅킹 프로젝트에서 이체 한도 검증 로직의 경계값을 어떻게 정했는지 말해 주세요."
    assert _checked(second, NOTABLE, [first])[0] is None
    assert _checked(other, NOTABLE, [first])[0] == other
    assert _checked(second, FOLLOW_UP, [first])[0] is not None


def test_said_is_rewritten_and_endings_are_opened() -> None:
    """서류 내용을 '말씀하셨는데'로 쓴 질문은 '적어 주셨는데'로 살리고, 예/아니오 끝맺음은 열어서 묻게 바꾼다."""
    from hiremate_ai.agents.generation.interview.agent import CHECK, NOTABLE, _checked

    said = "중고거래 웹 서비스에서 백엔드를 담당하셨다고 말씀하셨는데, 어떤 기술적 결정을 내렸는지 말해 주세요."
    assert _checked(said, NOTABLE, [])[0] == said.replace("말씀하셨는데", "적어 주셨는데")
    yes_no = "결제 승인 API에서 JUnit5와 Testcontainers로 통합 테스트를 만든 경험이 있으신가요?"
    assert _checked(yes_no, CHECK, [])[0] == yes_no.replace("있으신가요?", "있다면 말해 주세요.")
    example = "결제 장애 대응에서 동료와 원인을 나눠 찾은 사례를 하나 들어주시겠어요?"
    assert _checked(example, CHECK, [])[0] == example.replace("들어주시겠어요?", "말해 주세요.")


def test_hypothetical_and_leaked_instructions_are_caught() -> None:
    """가정 질문 · 내부 판단 · 프롬프트 지시 누설 (실제 최종면접 결과)."""
    from hiremate_ai.agents.generation.interview.agent import CHECK, NOTABLE, _style_problem

    grow = "체크리스트로 배포를 개선한 경험을 바탕으로, 그 습관을 어떻게 팀에 맞게 발전시킬 수 있을지 말해 주세요."
    think = "주문 처리량 개선 경험이 고객 신뢰 향상에 어떻게 기여할 수 있다고 생각하시나요?"
    no_career = "금융 서비스 분야의 직접적인 경험은 없지만, 금융에 관심을 갖게 된 계기를 말해 주세요."
    leak = "지원 동기 문장 '자동 배포로 바로 바꾸지 않았습니다'를 인용해 보세요. 그 이유를 말해 주세요."
    for text in (grow, think, no_career, leak):
        assert _style_problem(text, CHECK), text
    assert _style_problem("결제 재시도 로직을 고칠 때 어떤 실패 사례를 기준으로 삼았는지 말해 주세요.", NOTABLE) is None


def test_source_mark_with_particle_and_list_number_are_cleaned() -> None:
    """'[이력서]에 …'는 '이력서에 …'로, 인용 앞 목록 번호 "'01 …"는 떼어 낸다."""
    from hiremate_ai.agents.generation.interview.agent import _clean

    assert _clean("[이력서]에 Java, Spring Boot를 적어 주셨는데, 맡은 기능을 말해 주세요.").startswith("이력서에 Java")
    assert _clean("'01 이체 요청 타임아웃 정리' 경험에서 맡은 일을 말해 주세요.").startswith("'이체 요청")


def test_title_only_quote_uses_the_title_template() -> None:
    """이력서의 프로젝트 · 업무 이름만 인용하게 되면 '판단한 근거' 대신 그 일에서 맡은 부분을 묻는다."""
    from hiremate_ai.agents.generation.interview.agent import NOTABLE, Gap, _template

    title = _template(
        Gap("G1", NOTABLE, "팀 프로젝트 - 중고거래 웹 서비스 (백엔드 담당)", "본인 역할 확인 (이력서)", ["x"])
    )
    assert title.startswith("서류에 적어 주신 '중고거래 웹 서비스'에서 본인이 맡은 부분")
    work = _template(Gap("G2", NOTABLE, "쿠폰 중복 사용 버그 원인 분석 및 수정", "본인 역할 확인 (이력서)", ["x"]))
    assert work.startswith("'쿠폰 중복 사용 버그 원인 분석 및 수정'이라고")
    letter = _template(Gap("G3", NOTABLE, "빠른 시스템보다 순서를 설명할 수 있는 시스템", "(자기소개서)", ["x"]))
    assert not letter.startswith("서류에 적어 주신")


def test_template_josa_and_internal_note_are_fixed() -> None:
    """템플릿 조사('경험와' → '경험과')와, 답변 분석이 실패했을 때의 면접관용 메모가 질문에 나오지 않는지."""
    from hiremate_ai.agents.generation.interview.agent import FOLLOW_UP, NO_ANSWER, PREFERRED, Gap, _template

    preferred = _template(Gap("G1", PREFERRED, "금융 도메인 경험", ""))
    assert preferred.startswith("금융 도메인 경험과 관련된")
    assert _template(Gap("G2", PREFERRED, "대용량 트래픽 처리", "")).startswith("대용량 트래픽 처리와 관련된")
    failed = _template(Gap("G3", FOLLOW_UP, "결제 API", "", detail="AI가 해석하지 못한 답변 (면접관 확인 필요)"))
    assert "AI가" not in failed and "면접관" not in failed
    quoted = Gap("G4", FOLLOW_UP, "'카드 결제 승인 API를 개발했습니다'라고 적어", "", status=NO_ANSWER)
    assert "''" not in _template(quoted)


async def test_final_interview_fills_every_slot_in_order(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent, newcomer_analysis: CandidateAnalysis
) -> None:
    """최종면접: 1차 답변이 모두 확인됐으면 ① 자리는 모델이 서류에서 고른 질문(free_pick), ②~⑤는 자리 질문."""
    first = PreviousInterview(
        stage_id=uuid4(),
        stage_name="1차 실무면접",
        schedule=None,
        questions=[
            InterviewQuestion(
                question_id=uuid4(),
                text="결제 승인 API에서 맡은 역할은?",
                source=QuestionSource.AI,
                answer="승인 API의 재시도 로직을 직접 설계했고, 중복 승인을 0건으로 줄였습니다.",
            )
        ],
    )
    # 확인됨은 답변 원문에 있는 인용이 있어야 인정된다 (없으면 analyze_answers가 '확인 안 됨'으로 낮춤)
    answers = AnswerReading.model_validate(
        {
            "results": [
                {
                    "no": 1,
                    "status": "CONFIRMED",
                    "confirmed": [{"point": "재시도 로직 설계", "quote": "재시도 로직을 직접 설계했고"}],
                }
            ]
        }
    )
    llm = FakeLlm(answers, draft)

    questions = await generate_questions(
        llm,
        applicant=sample_applicants["이도윤"],
        posting=sample_posting,
        analysis=newcomer_analysis,
        interview=view(first),
        focus=None,
    )

    assert questions[0] == INTRO
    assert questions[1].startswith("모의 결제 API")  # ① 1차 미확인이 없어 모델이 고른 이 사람만의 확인 포인트
    assert questions[2].startswith("일하면서 가장 중요하게")  # ② 인성 · 가치관
    assert questions[5].startswith("결제 플랫폼 개발 직무에 지원")  # ⑤ 진정성 · 커리어
    assert "free_pick: 요청함" in llm.calls[1].user


async def test_final_slot_off_topic_falls_back_to_slot_question(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent, newcomer_analysis: CandidateAnalysis
) -> None:
    """자리 주제를 묻지 않은 질문(리더십 자리에 기술 질문)은 두 번 다 걸리면 자리별 기본 질문으로 채운다."""
    first = PreviousInterview(stage_id=uuid4(), stage_name="1차 실무면접", schedule=None, questions=[])

    def off_topic(call: LlmCall) -> QuestionDraft:
        made = draft(call)
        for pick in made.slot_picks:
            if pick.slot == "LEADERSHIP":
                pick.question = "결제 승인 API의 응답 시간을 어떤 지표로 측정했는지 말해 주세요."
        return made

    llm = FakeLlm(off_topic, off_topic)

    questions = await generate_questions(
        llm,
        applicant=sample_applicants["이도윤"],
        posting=sample_posting,
        analysis=newcomer_analysis,
        interview=view(first),
        focus=None,
    )

    assert questions[4] == FINAL_SLOTS["LEADERSHIP"].fallback
    assert "'리더십' 자리인데" in llm.calls[1].user.split("fix_errors: ")[1]


async def test_intro_is_not_added_twice(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent, newcomer_analysis: CandidateAnalysis
) -> None:
    """카드에 자기소개 질문이 이미 있으면(면접관이 직접 넣음) 다시 넣지 않는다."""
    intro = InterviewQuestion(
        question_id=uuid4(), text="1분 자기소개 부탁드립니다.", source=QuestionSource.MANUAL, answer=""
    )
    llm = FakeLlm(draft)

    questions = await generate_questions(
        llm,
        applicant=sample_applicants["이도윤"],
        posting=sample_posting,
        analysis=newcomer_analysis,
        interview=view(questions=[intro]),
        focus=None,
    )

    assert INTRO not in questions
    assert len(questions) == 3


async def test_previous_intro_is_not_followed_up_and_intro_comes_again(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent, newcomer_analysis: CandidateAnalysis
) -> None:
    """1차의 1분 자기소개는 답변 분석 · 이어서 묻기에서 빼고, 최종면접에서도 맨 앞에 다시 묻는다."""
    first = PreviousInterview(
        stage_id=uuid4(),
        stage_name="1차 실무면접",
        schedule=None,
        questions=[
            InterviewQuestion(
                question_id=uuid4(), text=INTRO, source=QuestionSource.AI, answer="결제 백엔드 개발자입니다."
            ),
            InterviewQuestion(
                question_id=uuid4(),
                text="모의 결제 서비스에서 본인 역할은?",
                source=QuestionSource.AI,
                answer="열심히 했어요.",
            ),
        ],
    )
    answers = AnswerReading.model_validate(
        {"results": [{"no": 1, "status": "NOT_CONFIRMED", "unconfirmed": ["취소 API를 설계한 본인 판단"]}]}
    )
    llm = FakeLlm(answers, draft)

    questions = await generate_questions(
        llm,
        applicant=sample_applicants["이도윤"],
        posting=sample_posting,
        analysis=newcomer_analysis,
        interview=view(first),
        focus=None,
    )

    assert "자기소개" not in llm.calls[0].user  # 답변 분석에 자기소개를 넘기지 않았다
    assert questions[0] == INTRO
    assert len(questions) == 2 + len(FINAL_SLOTS)
    assert not any("자기소개" in text for text in questions[1:])


async def test_final_follow_up_quoting_the_first_question_is_kept(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent, newcomer_analysis: CandidateAnalysis
) -> None:
    """① 1차 미확인 질문은 1차 질문을 인용하므로, 1차 질문과 비슷하다는 이유로 빠지지 않는다.

    1차 질문이 템플릿 질문이면 두 질문의 핵심 내용이 거의 같아져 '비슷함'으로 걸리던 경우다.
    """
    asked = "동료와 적극적으로 소통하며 협업해 온 경험 부분을 실제 경험을 예로 들어 구체적으로 설명해 주세요."
    first = PreviousInterview(
        stage_id=uuid4(),
        stage_name="1차 실무면접",
        schedule=None,
        questions=[
            InterviewQuestion(question_id=uuid4(), text=asked, source=QuestionSource.AI, answer="열심히 했습니다.")
        ],
    )
    answers = AnswerReading.model_validate(
        {"results": [{"no": 1, "status": "NOT_CONFIRMED", "unconfirmed": ["본인이 맡은 역할"]}]}
    )

    def slots_only(call: LlmCall) -> QuestionDraft:
        made = draft(call)
        made.questions = []  # ① 자리를 모델이 못 써서 템플릿(지난 면접에서 '…')으로 채워지는 경우
        return made

    llm = FakeLlm(answers, slots_only, slots_only)

    questions = await generate_questions(
        llm,
        applicant=sample_applicants["이도윤"],
        posting=sample_posting,
        analysis=newcomer_analysis,
        interview=view(first),
        focus=None,
    )

    assert questions[1].startswith("지난 면접에서")
    assert len(questions) == 2 + len(FINAL_SLOTS)


async def test_final_interview_uses_company_talents_and_culture(
    sample_applicants: dict[str, ApplicantDetail],
    sample_posting: PostingContent,
    sample_company: CompanyProfile,
    newcomer_analysis: CandidateAnalysis,
) -> None:
    """회사 정보(인재상 · 조직 문화)를 주면 최종면접 프롬프트에 기준으로 들어간다.

    자리 질문을 못 쓰면 그 기준으로 기본 질문을 만든다.
    """
    first = PreviousInterview(stage_id=uuid4(), stage_name="1차 실무면접", schedule=None, questions=[])
    llm = FakeLlm(lambda call: draft(call, bad=True), lambda call: draft(call, bad=True))

    questions = await generate_questions(
        llm,
        applicant=sample_applicants["이도윤"],
        posting=sample_posting,
        analysis=newcomer_analysis,
        interview=view(first),
        focus=None,
        company=sample_company,
    )

    talent = sample_company.talents[0].title
    assert '<data kind="company_talents"' in llm.calls[0].user
    assert talent in llm.calls[0].user
    assert questions[2].startswith(f"'{talent}'")  # ② 인성 · 가치관 기본 질문에 인재상 이름
    assert questions[3].startswith("저희는 '")  # ③ 조직 적응 기본 질문에 조직 문화
    assert all("결혼" not in text for text in questions)


async def test_without_company_the_slot_questions_still_come(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent, newcomer_analysis: CandidateAnalysis
) -> None:
    """회사 정보가 없어도(backend가 아직 안 보냄) 깨지지 않고 자리별 기본 질문으로 채운다."""
    first = PreviousInterview(stage_id=uuid4(), stage_name="1차 실무면접", schedule=None, questions=[])
    llm = FakeLlm(lambda call: draft(call, bad=True), lambda call: draft(call, bad=True))

    questions = await generate_questions(
        llm,
        applicant=sample_applicants["이도윤"],
        posting=sample_posting,
        analysis=newcomer_analysis,
        interview=view(first),
        focus=None,
    )

    assert "company_talents" not in llm.calls[0].user
    assert questions[2] == FINAL_SLOTS["VALUES"].fallback


# ---------------------------------------------------------------- 상세 판정(ApplicationReview)으로 빈틈 고르기

API = "Spring Boot와 MySQL로 결제 승인 · 취소 API를 만들고 JUnit으로 테스트했습니다."
SDK = "결제 SDK 문서의 예제 코드를 고쳤습니다."


class ReviewOnly:
    """load_review가 쓰는 latest만 있는 메모리 저장소 (DB 없이)."""

    def __init__(self, review: ApplicationReview | None, *, broken: bool = False) -> None:
        self.review = review
        self.broken = broken

    async def latest(self, application_id: object) -> ApplicationReview | None:
        if self.broken:
            raise ConnectionError("DB에 연결하지 못함")
        return self.review


def newcomer_review(applicant: ApplicantDetail, *, readable: bool = True) -> ApplicationReview:
    """이도윤(신입)의 상세 판정.

    경력 요건 미충족, 우대 '대용량 트래픽'의 NCS 수행준거 하나 근거 없음,
    오픈소스 기여는 본인 역할이 불분명(UNCLEAR), 모의 결제 API는 본인이 한 일(SELF).
    """
    resume = DocumentType.RESUME
    sdk = Fact(
        kind="PROJECT",
        statement="오픈소스 SDK 문서 기여",
        actor=Actor.UNCLEAR,
        quotes=[Quote(document=resume, sentence=SDK)],
    )
    api = Fact(
        kind="PROJECT", statement="모의 결제 API 개발", actor=Actor.SELF, quotes=[Quote(document=resume, sentence=API)]
    )
    traffic = PreferenceResult(
        number=1,
        text="대용량 트래픽 처리 경험",
        weight=5,
        unit_code="2001020212_23v6",
        unit_name="인터페이스 구현",
        criteria=[
            CriterionResult(
                number=1,
                content_no="1-1",
                content="대용량 요청을 처리하기 위한 인터페이스 성능 기준을 정할 수 있다.",
                level=Level.NONE,
                reason="근거 없음",
            ),
            CriterionResult(
                number=2,
                content_no="1-2",
                content="인터페이스 오류를 처리할 수 있다.",
                level=Level.MET,
                reason="취소 API",
            ),
        ],
        status=PreferenceStatus.SCORED,
        score=0.5,
    )
    finance = PreferenceResult(
        number=2,
        text="금융 도메인 경험",
        weight=None,
        unit_code=None,
        unit_name=None,
        status=PreferenceStatus.UNRATED,
        score=None,
    )
    return ApplicationReview(
        version="test",
        input_hash="h",
        application_id=applicant.info.application_id,
        readable=readable,
        facts=[sdk, api],
        qualifications=[
            QualificationResult(
                number=1,
                text="Java · Spring Boot 기반 서버 개발 경력 3년 이상",
                met=False,
                shortfall="신입",
                reason="경력 없음",
            ),
            QualificationResult(number=2, text="RDBMS 설계와 운영 경험", met=True, reason="MySQL 사용"),
        ],
        preferences=[traffic, finance],
        checks=[Note(text="실무 경력 없이 모의 프로젝트만 있음", source="자격 요건")],
    )


def test_review_gaps_follow_the_demo_like_priority(sample_applicants: dict[str, ApplicantDetail]) -> None:
    """상세 판정으로 고른 빈틈: 필수 → 확인 필요 → 우대(NCS) → 주장만 → 본인 역할. 평가 기준 없는 우대사항은 뺀다."""
    gaps = review_gaps(newcomer_review(sample_applicants["이도윤"]))

    assert [gap.kind for gap in gaps] == [REQUIRED, CHECK, PREFERRED, CLAIM, NOTABLE]
    assert "인터페이스 구현" in gaps[2].note and "성능 기준" in gaps[2].note  # NCS 수행준거가 메모로 간다
    assert all("금융" not in gap.topic for gap in gaps)  # 평가 기준(UNRATED)이 없는 우대사항은 빈틈이 아니다
    assert gaps[3].evidence == [SDK] and "불분명" in gaps[3].note  # 역할이 불분명한 경험은 '주장만'
    assert gaps[4].evidence == [API]  # 본인 역할 확인은 요약 문장이 아니라 서류 원문을 인용한다


@pytest.mark.parametrize("use_review", [True, False])
def test_configuration_notices_are_excluded_but_applicant_checks_remain(
    sample_applicants: dict[str, ApplicantDetail],
    sample_posting: PostingContent,
    newcomer_analysis: CandidateAnalysis,
    use_review: bool,
) -> None:
    """평가 미설정 안내만 제외하고 기술 요건과 '평가 기준'을 언급한 실제 확인 사항은 유지한다."""
    notices = [
        Note(
            text=f"우대사항 P{number} '{topic}'은 평가 기준(가중치 · NCS)이 없어 점수에 넣지 않았어요.",
            source="공고 · 우대사항",
        )
        for number, topic in enumerate(["Java/Spring 기반 백엔드 개발 경험", "RDBMS 관리·최적화 경험"], 1)
    ]
    # 저장된 안내의 줄바꿈 · 공백 차이도 같은 운영 안내로 처리한다.
    notices[1] = notices[1].model_copy(update={"text": notices[1].text.replace("이 없어 ", "이 없어\n  ")})
    real_check = Note(text="프로젝트 성능 평가 기준을 정할 때 본인이 맡은 역할 확인 필요", source="자기소개서")
    checks = [*notices, real_check]
    if use_review:
        review = newcomer_review(sample_applicants["이도윤"]).model_copy(update={"checks": checks})
        gaps = review_gaps(review)
    else:
        analysis = newcomer_analysis.model_copy(
            update={"checks": [Finding(text=check.text, source=check.source) for check in checks]}
        )
        gaps = summary_gaps(sample_posting, analysis)

    assert [gap.evidence for gap in gaps if gap.kind == CHECK] == [[real_check.text]]
    assert any(gap.kind == REQUIRED and "Spring" in gap.topic for gap in gaps)
    assert any(gap.kind == NOTABLE for gap in gaps)


@pytest.mark.parametrize("use_review", [True, False])
async def test_configuration_notices_do_not_reach_question_writing_or_fallback(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent, use_review: bool
) -> None:
    """안내를 제외한 뒤 원문 경험을 질문 소재로 쓰고, 모델 재작성 실패 시에도 안내 템플릿을 만들지 않는다."""
    applicant = sample_applicants["이도윤"]
    notice = Note(
        text="우대사항 P1 'Java/Spring 경험'은 평가 기준(가중치 · NCS)이 없어 점수에 넣지 않았어요.",
        source="공고 · 우대사항",
    )
    review = newcomer_review(applicant).model_copy(update={"qualifications": [], "preferences": [], "checks": [notice]})
    analysis = CandidateAnalysis(
        conditions=[],
        notable=[Finding(text=API, source="이력서")],
        checks=[Finding(text=notice.text, source=notice.source)],
        holds=[],
        fit=[],
        highlights=[],
        agent="Application Agent",
        stub=False,
    )
    llm = FakeLlm(lambda call: draft(call, bad=True), lambda call: draft(call, bad=True))

    questions = await generate_questions(
        llm,
        applicant=applicant,
        posting=sample_posting,
        analysis=analysis,
        interview=view(),
        focus=None,
        review=review if use_review else None,
    )

    assert llm.calls
    assert all(notice.text not in call.user for call in llm.calls)
    assert API in llm.calls[0].user
    assert questions[0] == INTRO
    assert len(questions) > 1
    assert all("평가 기준" not in question and "점수에 넣지" not in question for question in questions)
    assert any("결제" in question for question in questions[1:])


async def test_detailed_review_is_used_instead_of_the_summary(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent, newcomer_analysis: CandidateAnalysis
) -> None:
    """상세 판정이 있으면 요약(CandidateAnalysis) 대신 그것으로 빈틈 2개를 고른다: 필수 조건, 확인 필요."""
    applicant = sample_applicants["이도윤"]
    llm = FakeLlm(draft, draft)  # 확인 필요 질문이 근거 문장과 안 이어지면 한 번 더 쓴다

    questions = await generate_questions(
        llm,
        applicant=applicant,
        posting=sample_posting,
        analysis=newcomer_analysis,
        interview=view(),
        focus=None,
        review=newcomer_review(applicant),
    )

    assert len(questions) == 4
    assert "자격 요건 근거 부족 — 신입" in llm.calls[0].user
    assert "실무 경력 없이 모의 프로젝트만 있음" in llm.calls[0].user


async def test_unreadable_review_falls_back_to_the_summary(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent, newcomer_analysis: CandidateAnalysis
) -> None:
    """서류를 읽지 못한 상세 판정은 쓰지 않고 요약으로 고른다."""
    applicant = sample_applicants["이도윤"]
    llm = FakeLlm(draft)

    await generate_questions(
        llm,
        applicant=applicant,
        posting=sample_posting,
        analysis=newcomer_analysis,
        interview=view(),
        focus=None,
        review=newcomer_review(applicant, readable=False),
    )

    assert "근거가 지원 자료에 없음" in llm.calls[0].user  # 요약(conditions)에서 온 메모
    assert "자격 요건 근거 부족" not in llm.calls[0].user


async def test_load_review_returns_none_when_the_store_fails(sample_applicants: dict[str, ApplicantDetail]) -> None:
    """저장소를 읽지 못해도 질문 생성은 멈추지 않는다 (요약으로 만든다)."""
    applicant = sample_applicants["이도윤"]

    assert await load_review(ReviewOnly(None, broken=True), applicant) is None
    assert await load_review(ReviewOnly(newcomer_review(applicant)), applicant) is not None


async def test_experience_already_asked_on_the_card_is_not_asked_again(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    """카드가 이미 물은 서류 경험(자동 생성 질문)은 AI Chat으로 더 만들 때 다시 묻지 않는다 (문장이 달라도).

    눈여겨볼 점이 하나뿐이고 그 경험을 카드가 이미 물었으면, 템플릿으로라도 같은 경험을 또 묻지 않는다.
    """
    analysis = CandidateAnalysis(
        conditions=[],
        notable=[Finding(text=API, source="이력서")],
        checks=[],
        holds=[],
        fit=[],
        highlights=[],
        agent="Application Agent",
        stub=False,
    )
    asked = InterviewQuestion(
        question_id=uuid4(),
        text=(
            "Spring Boot와 MySQL로 결제 승인 · 취소 API를 만들고 JUnit으로 테스트했다고 적어 주셨는데, "
            "이 과정에서 본인이 담당하신 역할과 판단 근거를 말씀해 주세요."
        ),
        source=QuestionSource.AI,
        answer="",
    )
    llm = FakeLlm(draft, draft)

    questions = await generate_questions(
        llm,
        applicant=sample_applicants["이도윤"],
        posting=sample_posting,
        analysis=analysis,
        interview=view(questions=[asked]),
        focus=None,
    )

    assert not any("결제 승인 · 취소 API" in text for text in questions)
