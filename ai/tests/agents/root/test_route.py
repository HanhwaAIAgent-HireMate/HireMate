from uuid import uuid4

from root_context import make_context

from hiremate_ai.agents.root.route import (
    DECISION_REPLY,
    DEFAULT_CLARIFY,
    LOCKED,
    NO_ASSESSMENT,
    NO_INTERVIEW,
    NOT_YET_ASSESSMENT,
    NOT_YET_INTERVIEW,
    RootRoute,
    asks_comparison,
    classify,
    decided_filter,
    posting_section,
    precheck,
    refers_previous,
    required_data,
)
from hiremate_ai.agents.root.targets import resolve
from hiremate_ai.agents.root.types import ChatContext, ChatPlan, Decision, EditAction, Intent
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType
from hiremate_ai.llm.fake import FakeLlm

type Applicants = dict[str, ApplicantDetail]


def context_for(
    applicants: Applicants,
    company: CompanyProfile,
    posting: PostingContent,
    stage_type: StageType = StageType.DOCUMENT,
    previous_types: tuple[StageType, ...] = (),
    message: str = "질문",
    later_types: tuple[StageType, ...] = (),
) -> ChatContext:
    return make_context(
        applicants,
        company,
        posting,
        message=message,
        stage_type=stage_type,
        previous_types=previous_types,
        later_types=later_types,
    )


async def test_prompt_has_question_and_targets_but_no_documents(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="@정유민 빼줘",
        mentions=["정유민"],
        checked=["김하늘", "박서준"],
    )
    route = RootRoute(kind="EDIT", edit=EditAction.REMOVE)
    llm = FakeLlm(route)

    result = await classify(llm, context, resolve(context))

    assert result == route
    call = llm.calls[0]
    assert call.agent == "root"
    assert "@정유민 빼줘" in call.user
    assert "정유민" in call.user.replace("@정유민 빼줘", "")
    assert "체크한 지원자: 김하늘, 박서준" in call.user
    first_line = sample_applicants["정유민"].documents[0].text.splitlines()[0]
    assert first_line not in call.user


def test_decision_clarifies(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)

    assert precheck(RootRoute(kind="DECISION"), context) == ChatPlan.answer(Intent.CLARIFY, DECISION_REPLY)


def test_clarify_uses_model_question(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)

    plan = precheck(RootRoute(kind="CLARIFY", clarify="어느 지원자를 말씀하세요?"), context)

    assert plan == ChatPlan.answer(Intent.CLARIFY, "어느 지원자를 말씀하세요?")


def test_clarify_falls_back_to_default(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)

    assert precheck(RootRoute(kind="CLARIFY"), context) == ChatPlan.answer(Intent.CLARIFY, DEFAULT_CLARIFY)


def test_needs_assessment_in_document_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting, message="평가 점수 좋은 사람 찾아줘")

    plan = precheck(RootRoute(kind="FIND", needs_assessment=True), context)

    assert plan == ChatPlan.answer(Intent.CLARIFY, NO_ASSESSMENT)


def test_needs_assessment_before_assessment_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(
        sample_applicants,
        sample_company,
        sample_posting,
        message="평가 점수 좋은 사람 찾아줘",
        later_types=(StageType.ASSESSMENT,),
    )

    plan = precheck(RootRoute(kind="FIND", needs_assessment=True), context)

    assert plan == ChatPlan.answer(Intent.CLARIFY, NOT_YET_ASSESSMENT.format(order=2, name="과제 평가"))


def test_needs_assessment_in_interview_stage_without_assessment(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(
        sample_applicants,
        sample_company,
        sample_posting,
        StageType.INTERVIEW,
        (StageType.DOCUMENT,),
        message="@정유민 과제에서 협업이 보였어?",
    )

    plan = precheck(RootRoute(kind="ANSWER", needs_assessment=True), context)

    assert plan == ChatPlan.answer(Intent.CLARIFY, NO_ASSESSMENT)


def test_needs_assessment_after_assessment_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(
        sample_applicants, sample_company, sample_posting, StageType.INTERVIEW, (StageType.ASSESSMENT,)
    )

    assert precheck(RootRoute(kind="FIND", needs_assessment=True), context) is None


def test_needs_assessment_in_assessment_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting, StageType.ASSESSMENT)

    assert precheck(RootRoute(kind="FIND", needs_assessment=True), context) is None


def test_needs_interview_before_interview(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(
        sample_applicants,
        sample_company,
        sample_posting,
        StageType.ASSESSMENT,
        (StageType.DOCUMENT,),
        message="면접 답변에서 확인된 거 알려줘",
        later_types=(StageType.INTERVIEW,),
    )

    plan = precheck(RootRoute(kind="ANSWER", needs_interview=True), context)

    assert plan == ChatPlan.answer(Intent.CLARIFY, NOT_YET_INTERVIEW.format(order=3, name="1차 면접"))


def test_needs_interview_without_interview_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(
        sample_applicants,
        sample_company,
        sample_posting,
        StageType.ASSESSMENT,
        message="면접 답변에서 확인된 거 알려줘",
    )

    plan = precheck(RootRoute(kind="ANSWER", needs_interview=True), context)

    assert plan == ChatPlan.answer(Intent.CLARIFY, NO_INTERVIEW)


def test_needs_interview_in_interview_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting, StageType.INTERVIEW)

    assert precheck(RootRoute(kind="ANSWER", needs_interview=True), context) is None


def test_find_and_edit_pass_precheck(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)

    assert precheck(RootRoute(kind="FIND", concepts=["금융 도메인 경험"]), context) is None
    assert precheck(RootRoute(kind="EDIT", edit=EditAction.CLEAR), context) is None


def test_needs_flag_without_matching_words_is_ignored(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(
        sample_applicants,
        sample_company,
        sample_posting,
        StageType.INTERVIEW,
        (StageType.DOCUMENT,),
        message="@정유민 서류 기준으로 기술 심화 질문 만들어줘",
    )

    route = RootRoute(kind="ANSWER", interview_questions=True, needs_assessment=True)

    assert precheck(route, context) is None


def test_interview_words_do_not_count_as_assessment(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(
        sample_applicants, sample_company, sample_posting, message="@정유민 면접 답변에서 확인된 거 알려줘"
    )

    plan = precheck(RootRoute(kind="ANSWER", needs_assessment=True, needs_interview=True), context)

    assert plan == ChatPlan.answer(Intent.CLARIFY, NO_INTERVIEW)


def test_required_data_keeps_only_flags_with_matching_words() -> None:
    route = RootRoute(kind="ANSWER", needs_assessment=True, needs_interview=True)

    assert required_data(route, "@정유민 과제 결과와 면접 답변을 같이 봐줘") == {
        StageType.ASSESSMENT,
        StageType.INTERVIEW,
    }
    assert required_data(route, "@정유민 면접 답변에서 확인된 거 알려줘") == {StageType.INTERVIEW}
    assert required_data(route, "@정유민 서류 기준으로 질문 만들어줘") == set()


def test_document_score_is_not_assessment(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    route = RootRoute(kind="FIND", needs_assessment=True)

    for message in ("서류 점수 80점 이상만 골라줘", "@정유민 서류 평가 어때?", "자소서 점수 높은 사람"):
        context = context_for(sample_applicants, sample_company, sample_posting, message=message)
        assert precheck(route, context) is None, message


def test_assessment_words_next_to_document_words_still_count() -> None:
    route = RootRoute(kind="ANSWER", needs_assessment=True)

    assert required_data(route, "@정유민 자기소개서에 쓴 협업이 과제에서도 보였어?") == {StageType.ASSESSMENT}
    assert required_data(route, "서류 점수는 높은데 평가 결과가 낮은 사람") == {StageType.ASSESSMENT}
    assert required_data(route, "80점 이상인 사람 골라줘") == {StageType.ASSESSMENT}


def test_locked_stage_refuses_find_and_edit(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting).model_copy(update={"selectable": False})

    assert precheck(RootRoute(kind="FIND", concepts=["금융"]), context) == ChatPlan.answer(Intent.CLARIFY, LOCKED)
    assert precheck(RootRoute(kind="EDIT", edit=EditAction.CLEAR), context) == ChatPlan.answer(Intent.CLARIFY, LOCKED)
    assert precheck(RootRoute(kind="ANSWER"), context) is None


async def test_prompt_caps_checked_names(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    names = ["정유민", "김하늘", "박서준", "이도윤", "최지우", "한예린", "윤태오"]
    context = make_context(sample_applicants, sample_company, sample_posting, message="요약해줘", checked=names)
    llm = FakeLlm(RootRoute(kind="ANSWER"))

    await classify(llm, context, resolve(context))

    user = llm.calls[0].user
    assert "체크한 지원자: 정유민, 김하늘, 박서준, 이도윤, 최지우 외 2명" in user
    assert "한예린" not in user


def checked_context(
    applicants: Applicants, company: CompanyProfile, posting: PostingContent, message: str, checked: list[str]
) -> ChatContext:
    return make_context(applicants, company, posting, message=message, checked=checked)


def test_previous_ignored_when_checked_without_previous_words(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = checked_context(sample_applicants, sample_company, sample_posting, "둘 비교해줘", ["박서준", "이도윤"])

    assert refers_previous(RootRoute(kind="ANSWER", previous_ref="result"), context) is False


def test_previous_kept_with_ordinal_words_or_no_checked(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    two = ["박서준", "이도윤"]
    ordinal = checked_context(sample_applicants, sample_company, sample_posting, "두 번째 사람 강점은?", two)
    words = checked_context(sample_applicants, sample_company, sample_posting, "아까 그 사람 빼줘", two)
    nothing_checked = checked_context(sample_applicants, sample_company, sample_posting, "둘 비교해줘", [])

    assert refers_previous(RootRoute(kind="ANSWER", previous_ref="result", ordinal=2), ordinal)
    assert refers_previous(RootRoute(kind="EDIT", edit=EditAction.REMOVE, previous_ref="subject"), words)
    assert refers_previous(RootRoute(kind="ANSWER", previous_ref="result"), nothing_checked)
    assert not refers_previous(RootRoute(kind="ANSWER"), nothing_checked)


def test_comparison_needs_flag_and_word() -> None:
    assert asks_comparison(RootRoute(kind="ANSWER", compare=True), "둘 비교해줘")
    assert asks_comparison(RootRoute(kind="ANSWER", compare=True), "둘 중 누가 더 나아?")
    assert not asks_comparison(RootRoute(kind="ANSWER"), "둘 비교해줘")
    assert not asks_comparison(RootRoute(kind="ANSWER", compare=True), "강점 알려줘")
    assert asks_comparison(RootRoute(kind="ANSWER", compare=True), "이 사람들 비교해줘")


def test_comparing_with_posting_is_not_between_applicants() -> None:
    # 실제 모델은 한 지원자를 공고와 견주는 요청에도 compare를 표시한다
    assert not asks_comparison(RootRoute(kind="ANSWER", compare=True), "@김하늘 공고 자격 요건과 비교해줘")
    assert not asks_comparison(RootRoute(kind="ANSWER", compare=True), "@정유민 인재상과 비교해줘")


def test_checked_outside_stage_does_not_hide_previous(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = checked_context(sample_applicants, sample_company, sample_posting, "강점 알려줘", [])
    context = context.model_copy(update={"checked": [uuid4()]})

    assert refers_previous(RootRoute(kind="ANSWER", previous_ref="result"), context)


def test_words_starting_with_jung_are_not_previous(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    two = ["박서준", "이도윤"]
    route = RootRoute(kind="ANSWER", previous_ref="result")

    for message in ("그 중요한 경험이 뭐야?", "그 중간 결과 알려줘", "그 중심 역할은?"):
        assert not refers_previous(
            route, checked_context(sample_applicants, sample_company, sample_posting, message, two)
        )
    for message in ("그중 강점은?", "그 중에서 강점은?", "그중에 누가 나아?", "그중엔 누구야?"):
        assert refers_previous(route, checked_context(sample_applicants, sample_company, sample_posting, message, two))


def test_posting_section_needs_word() -> None:
    route = RootRoute(kind="FIND", posting_criteria="preferred", criteria_match="all")

    assert posting_section(route, "우대 사항을 다 충족하는 사람을 찾아줘") == "preferred"
    assert posting_section(route, "공고에 아주 적합한 사람 찾아줘") == "preferred"
    assert posting_section(route, "금융 경험 있는 사람 찾아줘") is None
    assert posting_section(RootRoute(kind="FIND"), "우대 사항 다 충족하는 사람") is None


def test_posting_section_only_for_find() -> None:
    route = RootRoute(kind="ANSWER", posting_criteria="qualifications")

    assert posting_section(route, "@김하늘 자격 요건 다 충족해?") is None


async def test_ordinal_kept_only_with_ordinal_words(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    # 실제 모델은 "몇 명이야?", "두 지원자를 비교해봐"에도 ordinal을 적는다
    async def ordinal_of(message: str) -> int | None:
        context = context_for(sample_applicants, sample_company, sample_posting, message=message)
        llm = FakeLlm(RootRoute(kind="ANSWER", previous_ref="subject", ordinal=2))
        return (await classify(llm, context, resolve(context))).ordinal

    assert await ordinal_of("지금 미결정인 사람 몇 명이야?") is None
    assert await ordinal_of("두 지원자를 비교해봐") is None
    assert await ordinal_of("그중 두 번째 사람 강점은?") == 2
    assert await ordinal_of("2번째 지원자 경력은?") == 2
    assert await ordinal_of("마지막 사람 빼줘") == 2


async def test_clarified_comparison_goes_to_answer(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    # 실제 모델은 대상 없는 "둘 비교해줘"를 CLARIFY로 표시하고 되물을 말을 직접 쓴다. 대상 확인은 코드가 한다
    context = context_for(sample_applicants, sample_company, sample_posting, message="둘 비교해줘")
    llm = FakeLlm(RootRoute(kind="CLARIFY", compare=True, clarify="비교할 두 지원자를 알려주세요."))

    decided = await classify(llm, context, resolve(context))

    assert decided.kind == "ANSWER"
    assert precheck(decided, context) is None


async def test_among_them_refers_to_result(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    async def ref_of(message: str) -> str:
        context = context_for(sample_applicants, sample_company, sample_posting, message=message)
        llm = FakeLlm(RootRoute(kind="ANSWER", previous_ref="subject"))
        return (await classify(llm, context, resolve(context))).previous_ref

    assert await ref_of("그중 첫 번째 사람 강점은?") == "result"
    assert await ref_of("방금 찾은 사람들 비교해줘") == "result"
    assert await ref_of("아까 그 사람 강점은?") == "subject"


def test_decided_filter_needs_flag_and_word() -> None:
    passed = RootRoute(kind="FIND", decision="PASS")
    failed = RootRoute(kind="FIND", decision="FAIL")
    pending = RootRoute(kind="FIND", decision="PENDING")

    assert decided_filter(passed, "지금 합격 처리된 지원자들 중 금융 경험 있는 사람 골라줘") is Decision.PASS
    assert decided_filter(passed, "합격자 중에 Kafka 써 본 사람 있어?") is Decision.PASS
    assert decided_filter(failed, "불합격한 사람 중 다시 볼 만한 사람 찾아줘") is Decision.FAIL
    assert decided_filter(failed, "탈락한 지원자 중 금융 경험자") is Decision.FAIL
    assert decided_filter(pending, "아직 결정 안 한 사람 중 금융 경험자 찾아줘") is Decision.PENDING
    assert decided_filter(pending, "미결정 지원자 중 Spring 경험자") is Decision.PENDING


def test_decided_filter_ignores_flag_without_decided_words() -> None:
    passed = RootRoute(kind="FIND", decision="PASS")

    assert decided_filter(passed, "합격 가능성이 높은 사람 찾아줘") is None
    assert decided_filter(passed, "불합격한 사람 중 금융 경험자") is None
    assert decided_filter(RootRoute(kind="FIND"), "합격한 사람 중 금융 경험자") is None
    assert decided_filter(RootRoute(kind="ANSWER", decision="PASS"), "합격한 사람 중 누가 금융 경험 있어?") is None


def test_locked_stage_allows_find_among_decided(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(
        sample_applicants, sample_company, sample_posting, message="합격한 사람 중 금융 경험 있는 사람 찾아줘"
    ).model_copy(update={"selectable": False})

    assert precheck(RootRoute(kind="FIND", decision="PASS", concepts=["금융"]), context) is None
    assert precheck(RootRoute(kind="FIND", concepts=["금융"]), context) == ChatPlan.answer(Intent.CLARIFY, LOCKED)


async def test_reason_for_made_questions_is_not_making_questions(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    # 실제 모델은 "방금 만든 질문은 왜 만든 거야?"도 면접 질문 만들기로 표시해 질문을 다시 만들었다
    async def makes_questions(message: str) -> bool:
        context = context_for(sample_applicants, sample_company, sample_posting, StageType.INTERVIEW, message=message)
        llm = FakeLlm(RootRoute(kind="ANSWER", interview_questions=True))
        return (await classify(llm, context, resolve(context))).interview_questions

    assert not await makes_questions("방금 만든 질문은 왜 만든 거야?")
    assert not await makes_questions("아까 만든 질문 왜 그렇게 만들었어?")
    assert not await makes_questions("그 질문을 넣은 이유가 뭐야?")
    assert await makes_questions("@정유민 서류 기준으로 기술 심화 질문 만들어줘")
    assert await makes_questions("이유를 묻는 질문 2개 추가해줘")
    assert await makes_questions("좀 더 기술적으로 다시 해줘")
