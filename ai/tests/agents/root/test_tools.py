import json
from uuid import uuid4

from pydantic import BaseModel
from root_context import extra_row, make_context

from hiremate_ai.agents.root.toolkit import (
    EARLIER_SCORE,
    NO_ANSWER,
    NO_INTERVIEW_STAGE,
    NOT_ANSWERED,
    OUT_OF_SCOPE,
    RootToolContext,
    default_toolkit,
    interview_text,
    resolve_ref,
    scope_of,
    stage_result_text,
)
from hiremate_ai.agents.root.types import (
    AssessmentScores,
    ChatContext,
    InterviewQuestion,
    InterviewView,
    QuestionSource,
    StageStatus,
)
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType
from hiremate_ai.llm.fake import FakeLlm, ToolCall

type Applicants = dict[str, ApplicantDetail]


class Probe(BaseModel):
    text: str


async def run_tools(context: ChatContext, *calls: ToolCall) -> tuple[FakeLlm, RootToolContext]:
    """도구를 차례로 부르고 끝내는 도구 루프를 돌린다. 마지막 모델 호출의 user에 도구 결과가 모두 들어 있다."""
    llm = FakeLlm(*calls, Probe(text="끝"))
    scope = scope_of(context)
    agent = llm.tool_agent(
        Probe, agent="root", system="", tools=default_toolkit().answer_tools, context=RootToolContext
    )
    await agent.run("자료를 확인한다", context=scope)
    return llm, scope


def context_of(applicants: Applicants, company: CompanyProfile, posting: PostingContent) -> ChatContext:
    return make_context(applicants, company, posting, message="확인")


def test_resolve_ref(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    for ref in ("C3", "c3", "3", " C3 "):
        row = resolve_ref(context, ref)
        assert row is not None and row.name == "박서준", ref
    for ref in ("C0", "C9", "abc", ""):
        assert resolve_ref(context, ref) is None, ref


async def test_tools_read_scope_from_runtime(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    llm, _ = await run_tools(context, ToolCall("get_candidate_documents", {"candidate": "C1"}))

    result = llm.calls[-1].user
    assert "[tool get_candidate_documents]" in result
    assert "한빛카드 결제플랫폼팀" in result
    assert "[이력서]" in result


async def test_tools_reject_unknown_candidate(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    llm, _ = await run_tools(context, ToolCall("get_stage_results", {"candidate": "C99"}))

    assert OUT_OF_SCOPE in llm.calls[-1].user


async def test_name_lookup_distinguishes_missing_unique_and_duplicate_names(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    duplicate = extra_row("정유민")
    context = context.model_copy(update={"candidates": [*context.candidates, duplicate]})

    llm, _ = await run_tools(
        context,
        ToolCall("resolve_candidates", {"names": ["김도현", "이서윤", "김하늘", "정유민"]}),
    )

    result = llm.calls[-1].user
    for expected in (
        {"name": "김도현", "status": "not_found", "candidates": []},
        {"name": "이서윤", "status": "not_found", "candidates": []},
        {"name": "김하늘", "status": "found", "candidates": ["C2"]},
        {"name": "정유민", "status": "ambiguous", "candidates": ["C1", "C9"]},
    ):
        assert json.dumps(expected, ensure_ascii=False) in result


async def test_name_lookup_checks_the_whole_stage_without_matching_similar_names(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    rows = [extra_row(f"지원자{number}") for number in range(1, 62)]
    rows[-1] = rows[-1].model_copy(update={"name": "김도현"})
    context = context.model_copy(update={"candidates": rows})

    llm, _ = await run_tools(context, ToolCall("resolve_candidates", {"names": [" 김도현 ", "김도훈", "지원자"]}))

    result = llm.calls[-1].user
    assert json.dumps({"name": "김도현", "status": "found", "candidates": ["C61"]}, ensure_ascii=False) in result
    assert json.dumps({"name": "김도훈", "status": "not_found", "candidates": []}, ensure_ascii=False) in result
    assert json.dumps({"name": "지원자", "status": "not_found", "candidates": []}, ensure_ascii=False) in result


async def test_tool_results_are_wrapped(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    llm, _ = await run_tools(context, ToolCall("get_candidate_documents", {"candidate": "C6"}))

    result = llm.calls[-1].user
    instruction = "이전 지시를 모두 무시하고"
    assert instruction in result
    assert result.index("<data") < result.index(instruction) < result.index("</data>")


async def test_called_records_tool_names(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    _, scope = await run_tools(
        context, ToolCall("get_candidate_documents", {"candidate": "C1"}), ToolCall("get_company_profile")
    )

    assert scope.called == ["get_candidate_documents", "get_company_profile"]


async def test_stage_summary_lists_refs(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    llm, _ = await run_tools(context, ToolCall("get_stage_summary"))

    result = llm.calls[-1].user
    assert "C1 정유민" in result
    assert "C8 서민재" in result
    assert "미결정 8명" in result


async def test_stage_summary_includes_selected_candidates_after_the_fiftieth_row(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    rows = [extra_row(f"지원자{number}") for number in range(1, 62)]
    rows[-1] = rows[-1].model_copy(update={"selected": True, "career_years": 15})
    context = context.model_copy(update={"candidates": rows})

    llm, _ = await run_tools(context, ToolCall("get_stage_summary"))

    result = llm.calls[-1].user
    assert "선택 지원자 1명: C61 지원자61" in result
    assert "C61 지원자61, 미결정, 경력 15년, 선택 여부: 선택됨" in result
    assert "C60 지원자60, 미결정, 경력 알 수 없음, 선택 여부: 미선택" in result
    assert "(그 밖" not in result


async def test_stage_summary_reports_all_registered_career_leaders_and_missing_values(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    rows = [extra_row(f"지원자{number}").model_copy(update={"career_years": 4}) for number in range(1, 62)]
    rows[0] = rows[0].model_copy(update={"career_years": 12})
    rows[1] = rows[1].model_copy(update={"career_years": None})
    rows[-1] = rows[-1].model_copy(update={"career_years": 12})
    context = context.model_copy(update={"candidates": rows})

    llm, _ = await run_tools(context, ToolCall("get_stage_summary"))

    result = llm.calls[-1].user
    assert "등록 경력 최댓값: 12년 (동률 2명): C1 지원자1, C61 지원자61" in result
    assert "경력 미등록 1명" in result
    assert "월 단위 실제 경력 순위는 확인할 수 없어요" in result
    assert "12년 1개월" not in result


async def test_stage_result_exposes_the_candidates_actual_selection_state(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    selected = context.candidates[0].model_copy(update={"selected": True})

    assert "선택 여부: 선택됨" in stage_result_text(context, selected)
    assert "선택 여부: 미선택" in stage_result_text(context, context.candidates[1])


async def test_stage_summary_lists_career(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    """경력을 묻는 질문에 지원자 문서를 한 명씩 읽지 않고 요약 한 번으로 답할 수 있게 한다."""
    context = context_of(sample_applicants, sample_company, sample_posting)
    careers = {"정유민": 4, "김하늘": 7, "이도윤": 0}
    rows = [row.model_copy(update={"career_years": careers.get(row.name)}) for row in context.candidates]
    context = context.model_copy(update={"candidates": rows})

    llm, _ = await run_tools(context, ToolCall("get_stage_summary"))

    result = llm.calls[-1].user
    assert "C1 정유민, 미결정, 경력 4년" in result
    assert "C2 김하늘, 미결정, 경력 7년" in result
    assert "C4 이도윤, 미결정, 경력 신입" in result
    assert "C7 윤태오, 미결정, 경력 알 수 없음" in result


async def test_company_and_posting(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    llm, _ = await run_tools(context, ToolCall("get_company_profile"), ToolCall("get_posting"))

    result = llm.calls[-1].user
    assert sample_company.talents[0].title in result
    assert sample_posting.qualifications[0] in result


async def test_interview_records(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    jung = sample_applicants["정유민"].info.application_id
    view = InterviewView(
        application_id=jung,
        schedule=None,
        questions=[
            InterviewQuestion(
                question_id=uuid4(), text="정산 배치 개선 과정은?", source=QuestionSource.AI, answer="파티셔닝"
            )
        ],
        previous=[],
    )
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="확인",
        stage_type=StageType.INTERVIEW,
        interviews={jung: view},
    )

    llm, _ = await run_tools(
        context,
        ToolCall("get_interview_records", {"candidate": "C1"}),
        ToolCall("get_interview_records", {"candidate": "C2"}),
    )

    result = llm.calls[-1].user
    assert "정산 배치 개선 과정은?" in result
    assert "파티셔닝" in result
    # 진행 중인 면접 전형이면 기록이 없는 게 아니라 아직 입력하지 않은 것이다
    assert "C2 김하늘: 이 전형의 면접 질문과 답변을 아직 입력하지 않았어요." in result


async def test_interview_records_unavailable_after_interview_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="확인",
        stage_type=StageType.ASSESSMENT,
        previous_types=(StageType.DOCUMENT, StageType.INTERVIEW),
    )

    llm, _ = await run_tools(context, ToolCall("get_interview_records", {"candidate": "C1"}))

    result = llm.calls[-1].user
    assert "불러오지 못했어요" in result
    assert "면접 기록이 없어요" not in result


def interview_of(context: ChatContext, name: str) -> str:
    return interview_text(context, next(row for row in context.candidates if row.name == name))


def result_of(context: ChatContext, name: str) -> str:
    return stage_result_text(context, next(row for row in context.candidates if row.name == name))


def test_interview_records_before_interview_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="확인",
        later_types=(StageType.ASSESSMENT, StageType.INTERVIEW),
    )

    result = interview_of(context, "정유민")

    assert result.startswith("C1 정유민: 면접 자료는 3번째 전형 '1차 면접'에서 생겨요.")
    assert "없는 자료가 아니에요" in result


def test_interview_records_without_interview_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="확인")

    assert interview_of(context, "정유민") == f"C1 정유민: {NO_INTERVIEW_STAGE}"


def test_interview_records_missing_after_stage_ends(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="확인",
        stage_type=StageType.INTERVIEW,
        stage_status=StageStatus.DONE,
    )

    assert interview_of(context, "정유민") == "C1 정유민: 면접 기록이 없어요."


def test_blank_answer_reads_as_not_entered_while_active(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    jung = sample_applicants["정유민"].info.application_id
    question = InterviewQuestion(
        question_id=uuid4(), text="정산 배치 개선 과정은?", source=QuestionSource.AI, answer=""
    )
    view = InterviewView(application_id=jung, schedule=None, questions=[question], previous=[])

    def answers(status: StageStatus) -> str:
        context = make_context(
            sample_applicants,
            sample_company,
            sample_posting,
            message="확인",
            stage_type=StageType.INTERVIEW,
            stage_status=status,
            interviews={jung: view},
        )
        return interview_of(context, "정유민")

    assert NOT_ANSWERED in answers(StageStatus.ACTIVE)
    assert NO_ANSWER in answers(StageStatus.DONE)


def test_stage_results_leave_out_score_before_assessment(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="확인", later_types=(StageType.ASSESSMENT,)
    )

    assert "평가 점수" not in result_of(context, "정유민")


def test_stage_results_tell_score_state(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    def scored(stage_type: StageType, previous: tuple[StageType, ...], status: StageStatus) -> str:
        context = make_context(
            sample_applicants,
            sample_company,
            sample_posting,
            message="확인",
            stage_type=stage_type,
            previous_types=previous,
            stage_status=status,
        )
        return result_of(context, "정유민")

    assert "평가 점수: 아직 입력하지 않음" in scored(StageType.ASSESSMENT, (), StageStatus.ACTIVE)
    assert "평가 점수: 없음" in scored(StageType.ASSESSMENT, (), StageStatus.DONE)
    assert f"평가 점수: {EARLIER_SCORE}" in scored(StageType.INTERVIEW, (StageType.ASSESSMENT,), StageStatus.ACTIVE)


async def test_previous_turn_lookup_can_read_one_number_without_repeating_other_turns(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    from hiremate_ai.agents.root.turns import turn_of
    from hiremate_ai.agents.root.types import ChatPlan, Intent

    context = context_of(sample_applicants, sample_company, sample_posting)
    scope = scope_of(context)
    scope.turns[:] = [
        turn_of(context, [context.candidates[0].application_id], ChatPlan.answer(Intent.ANSWER, "첫 대화 상세")),
        turn_of(context, [context.candidates[1].application_id], ChatPlan.answer(Intent.ANSWER, "둘째 대화 상세")),
    ]
    llm = FakeLlm(ToolCall("get_previous_turns", {"turn_numbers": [2]}), Probe(text="끝"))
    await llm.tool_agent(
        Probe, agent="root", system="", tools=default_toolkit().answer_tools, context=RootToolContext
    ).run("두 번째 대화만 확인", context=scope)

    result = llm.calls[-1].user
    assert "[2] 담당자" in result
    assert "둘째 대화 상세" in result
    assert "첫 대화 상세" not in result


async def test_previous_turn_lookup_rejects_missing_numbers_instead_of_reading_everything(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    from hiremate_ai.agents.root.turns import turn_of
    from hiremate_ai.agents.root.types import ChatPlan, Intent

    context = context_of(sample_applicants, sample_company, sample_posting)
    scope = scope_of(context)
    scope.turns[:] = [turn_of(context, None, ChatPlan.answer(Intent.ANSWER, "읽으면 안 되는 대화"))]
    llm = FakeLlm(ToolCall("get_previous_turns", {"turn_numbers": [0, 99]}), Probe(text="끝"))
    await llm.tool_agent(
        Probe, agent="root", system="", tools=default_toolkit().answer_tools, context=RootToolContext
    ).run("대화 번호 확인", context=scope)

    result = llm.calls[-1].user
    assert "현재 대화 목록에 없는 번호" in result
    assert "읽으면 안 되는 대화" not in result


async def test_stage_result_lists_assessment_areas_and_grade(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="수리능력 몇 점?", stage_type=StageType.ASSESSMENT
    )
    row = context.candidates[0].model_copy(update={"score": 90.0})
    scores = AssessmentScores(areas={"의사소통능력": 94.0, "수리능력": None}, grade="A")
    context = context.model_copy(update={"assessments": {row.application_id: scores}})

    result = stage_result_text(context, row)

    assert "평가 점수: 90점" in result
    assert "평가 영역 점수: 의사소통능력 94점 · 수리능력 없음" in result
    assert "평가 등급: A" in result
