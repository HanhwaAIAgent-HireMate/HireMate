import json
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from root_context import make_context, root_reply
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.analysis.application.extract import ExtractedFacts, extraction_recipe
from hiremate_ai.agents.analysis.application.review import ClaimReview, ReviewJudgement
from hiremate_ai.agents.analysis.interview import analyze_interview
from hiremate_ai.agents.analysis.interview.store import interview_recipe
from hiremate_ai.agents.analysis.interview.types import (
    AnsweredQuestion,
    FindingDraft,
    InterviewAnalysisInput,
    InterviewDraft,
)
from hiremate_ai.agents.root.commands import ClarifyCommand, RootReply
from hiremate_ai.agents.root.graph import RootThread, run_plan
from hiremate_ai.agents.root.toolkit import OUT_OF_SCOPE, AgentEvidence, RootToolContext, default_toolkit
from hiremate_ai.agents.root.types import ChatContext, Intent, InterviewQuestion, InterviewView, QuestionSource
from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, InterviewerMemo, PostingContent, StageType
from hiremate_ai.db.analysis_artifact import AnalysisArtifactRecord
from hiremate_ai.db.analysis_store import DbAnalysisArtifacts
from hiremate_ai.db.profile import Verification
from hiremate_ai.llm.fake import FakeLlm, FakeReply, LlmCall, ToolCall

type Applicants = dict[str, ApplicantDetail]

DOCUMENT = "MySQL 정산 테이블을 파티셔닝해 월말 정산 배치 시간을 40% 줄였습니다."
ANSWER = "파티셔닝 기준을 월 단위로 정하고 성능을 측정했습니다."
STATEMENT = "정산 배치 시간을 줄였어요."
INTERVIEW_STATEMENT = "파티셔닝 기준을 구체적으로 설명했어요."


@pytest.mark.parametrize("with_focus", [True, False])
async def test_explicit_memo_request_passes_only_verified_candidate_note(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent, with_focus: bool
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    application_id = context.candidates[0].application_id
    memo = InterviewerMemo(
        stage_id=context.stage_id,
        stage_name=context.stage_name,
        text="파티셔닝 기준을 선택한 대안 비교는 추가 확인이 필요함",
    )
    context = context.model_copy(
        update={"message": "정유민 면접 메모 참고해서 질문 1개 추가해줘", "interviewer_memos": {application_id: [memo]}}
    )
    final = reply(questions=True, status="CHECK", source="면접관메모", sentence=memo.text)
    if not with_focus:
        final.args["focus"] = {}
    llm = FakeLlm(
        ToolCall("resolve_candidates", {"names": [context.candidates[0].name]}),
        ToolCall("get_interviewer_memos", {"candidate": "C1"}),
        ToolCall("get_interview_records", {"candidate": "C1"}),
        final,
    )
    plan = await run_plan(llm, context)
    assert plan.question_memos == {application_id: memo}
    assert plan.sources == ["면접관메모"]
    assert plan.items[0].status == "CHECK"
    assert "면접관메모" in llm.calls[2].user


def interview_context(applicants: Applicants, company: CompanyProfile, posting: PostingContent) -> ChatContext:
    applicant = applicants["정유민"]
    application_id = applicant.info.application_id
    return make_context(
        applicants,
        company,
        posting,
        message="서류와 면접 답변을 함께 검토하고 다음 질문을 준비해줘",
        stage_type=StageType.INTERVIEW,
        previous_types=[StageType.DOCUMENT],
        interviews={
            application_id: InterviewView(
                application_id=application_id,
                schedule=None,
                questions=[
                    InterviewQuestion(
                        question_id=uuid4(), text="파티셔닝 기준은 무엇인가요?", source=QuestionSource.AI, answer=ANSWER
                    )
                ],
                previous=[],
            )
        },
    ).model_copy(update={"documents": {application_id: [applicant.documents[0]]}})


def extraction(*, actor: str = "SELF") -> ExtractedFacts:
    return ExtractedFacts.model_validate(
        {"facts": [{"kind": "ACHIEVEMENT", "statement": STATEMENT, "actor": actor, "evidence": [DOCUMENT]}]}
    )


def review(*, supported: bool = True) -> ReviewJudgement:
    return ReviewJudgement(reviews=[ClaimReview(id="F1", verdict="SUPPORTED" if supported else "OVERSTATED")])


def interview_draft(*, confirmed: bool = True) -> InterviewDraft:
    return InterviewDraft(
        findings=[
            FindingDraft(kind="CONFIRMED" if confirmed else "UNCONFIRMED", content=INTERVIEW_STATEMENT, evidence=ANSWER)
        ]
    )


def reply(*, questions: bool = False, status: str = "OK", source: str = "이력서", sentence: str = DOCUMENT) -> ToolCall:
    text = INTERVIEW_STATEMENT if source == "면접 기록" else STATEMENT
    command: dict[str, object] = {"kind": "questions" if questions else "answer", "candidates": ["C1"]}
    if questions:
        command["focus"] = {"C1": text}
    return root_reply(
        {
            "message": "확인한 내용을 정리했어요.",
            "command": command,
            "items": [
                {
                    "candidate": "C1",
                    "label": "확인할 점",
                    "text": text,
                    "status": status,
                    "evidence": [{"sentence": sentence, "source": source}],
                }
            ],
        },
    )


async def test_root_passes_application_result_to_interview_agent_and_requests_questions(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    context = context.model_copy(update={"message": "정유민의 서류와 면접 답변을 함께 검토하고 다음 질문을 준비해줘"})
    final = reply(questions=True, source="면접 기록", sentence=ANSWER)
    final.args["items"].insert(0, reply().args["items"][0])
    llm = FakeLlm(
        ToolCall("resolve_candidates", {"names": ["정유민"]}),
        ToolCall("consult_application", {"candidate": "C1"}),
        extraction(),
        review(),
        ToolCall("consult_interview", {"candidate": "C1", "previous_results": ["D1"]}),
        interview_draft(),
        final,
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.ANSWER
    assert plan.question_targets == [context.candidates[0].application_id]
    assert STATEMENT in plan.question_focus[context.candidates[0].application_id]
    assert INTERVIEW_STATEMENT in plan.question_focus[context.candidates[0].application_id]
    assert plan.sources == ["이력서", "면접 기록"]
    assert plan.agents == ["Application Agent", "Interview Agent"]
    assert [call.agent for call in llm.calls] == [
        "root",
        "root",
        "application",
        "application",
        "root",
        "interview",
        "root",
    ]
    assert STATEMENT in llm.calls[5].user and DOCUMENT in llm.calls[5].user
    assert "specialist-reference" in llm.calls[5].user
    assert plan.targets == [] and plan.edit is None


async def test_application_consultation_is_actually_available_to_the_root(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)

    def answer(call: LlmCall) -> ToolCall:
        consulted = '"result": "D1"' in call.user
        return root_reply(
            RootReply(message="분석 결과를 받았어요." if consulted else "분석 결과가 없어요.", command=ClarifyCommand())
        )

    llm = FakeLlm(
        ToolCall("consult_application", {"candidate": "C1"}),
        lambda call: extraction() if call.agent == "application" else answer(call),
        review(),
        answer,
    )

    plan = await run_plan(llm, context)

    assert plan.message == "분석 결과를 받았어요."
    assert [call.agent for call in llm.calls] == ["root", "application", "application", "root"]


@pytest.mark.parametrize("candidate", ["C999", str(uuid4())])
async def test_specialist_tools_reject_candidates_outside_the_current_catalog(
    candidate: str, sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm(
        ToolCall("consult_application", {"candidate": candidate}),
        root_reply(RootReply(message="지원자를 다시 골라 주세요.", command=ClarifyCommand())),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.CLARIFY
    assert OUT_OF_SCOPE in llm.calls[-1].user
    assert all(call.agent == "root" for call in llm.calls)


@pytest.mark.parametrize("candidate,previous", [("C2", "D1"), ("C1", "D999")])
async def test_interview_cannot_receive_another_candidates_or_unknown_result(
    candidate: str,
    previous: str,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm(
        ToolCall("consult_application", {"candidate": "C1"}),
        extraction(),
        review(),
        ToolCall("consult_interview", {"candidate": candidate, "previous_results": [previous]}),
        root_reply(RootReply(message="전달할 결과를 다시 골라 주세요.", command=ClarifyCommand())),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.CLARIFY
    assert "이 지원자" in llm.calls[-1].user
    assert all(call.agent != "interview" for call in llm.calls)


@pytest.mark.parametrize("actor,supported", [("TEAM", True), ("SELF", False)])
async def test_unconfirmed_application_claims_cannot_be_promoted_by_the_root(
    actor: str,
    supported: bool,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm(
        ToolCall("consult_application", {"candidate": "C1"}),
        extraction(actor=actor),
        review(supported=supported),
        reply(),
        reply(status="CHECK"),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.ANSWER
    assert [item.status for item in plan.items] == ["CHECK"]
    assert plan.agents == ["Application Agent"]
    assert "검증" in llm.calls[-1].user


async def test_unconfirmed_interview_claims_cannot_be_promoted_by_the_root(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm(
        ToolCall("consult_interview", {"candidate": "C1"}),
        interview_draft(confirmed=False),
        reply(source="면접 기록", sentence=ANSWER),
        reply(source="면접 기록", sentence=ANSWER, status="CHECK"),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.ANSWER
    assert [item.status for item in plan.items] == ["CHECK"]
    assert plan.agents == ["Interview Agent"]


async def test_stored_longer_evidence_cannot_override_a_specialists_unconfirmed_result(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)

    async def stored(scope: RootToolContext, application_ids: Sequence[UUID]) -> dict[UUID, list[AgentEvidence]]:
        return {
            context.candidates[0].application_id: [
                AgentEvidence(
                    sentence=DOCUMENT + " 이후 운영도 담당했습니다.",
                    source="이력서 경력",
                    agent="application",
                    verification=Verification.EVIDENCED,
                )
            ]
        }

    llm = FakeLlm(
        ToolCall("consult_application", {"candidate": "C1"}),
        extraction(),
        review(supported=False),
        reply(),
        reply(status="CHECK"),
    )

    plan = await run_plan(llm, context, replace(default_toolkit(), evidence=stored))

    assert [item.status for item in plan.items] == ["CHECK"]


@pytest.mark.parametrize("actor,supported", [("TEAM", True), ("SELF", False)])
@pytest.mark.parametrize("keep_document", [True, False])
async def test_unrelated_company_citations_cannot_confirm_a_specialists_doubtful_claim(
    actor: str,
    supported: bool,
    keep_document: bool,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    unsupported = reply()
    citations = unsupported.args["items"][0]["evidence"]
    if not keep_document:
        citations.clear()
    citations.append({"sentence": sample_company.intro, "source": "회사 소개"})
    llm = FakeLlm(
        ToolCall("consult_application", {"candidate": "C1"}),
        extraction(actor=actor),
        review(supported=supported),
        unsupported,
        reply(status="CHECK"),
    )

    plan = await run_plan(llm, context)

    assert [item.status for item in plan.items] == ["CHECK"]


async def test_blocked_question_conditions_keep_the_blocked_plan(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    final = reply(questions=True)
    final.args["focus"] = {"C1": "여성 지원자만 면접 질문을 만들어요."}
    llm = FakeLlm(final)

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.BLOCKED
    assert plan.items == [] and plan.question_targets == []


@pytest.mark.parametrize("missing", ["documents", "interview", "wrong_stage", "mismatched_view"])
async def test_specialists_do_not_invent_inputs_when_material_is_missing(
    missing: str, sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    candidate_id = context.candidates[0].application_id
    tool = "consult_interview"
    if missing == "documents":
        context.documents[candidate_id] = []
        tool = "consult_application"
    elif missing == "interview":
        context.interviews.clear()
    elif missing == "wrong_stage":
        context = context.model_copy(update={"stage_type": StageType.DOCUMENT})
    else:
        context.interviews[candidate_id] = context.interviews[candidate_id].model_copy(
            update={"application_id": uuid4()}
        )
    llm = FakeLlm(
        ToolCall(tool, {"candidate": "C1"}),
        root_reply(RootReply(message="원문 자료를 확인해 주세요.", command=ClarifyCommand())),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.CLARIFY
    assert all(call.agent == "root" for call in llm.calls)
    assert "Error" not in llm.calls[-1].user


async def test_consulting_the_same_application_twice_reuses_the_request_result(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm(
        ToolCall("consult_application", {"candidate": "C1"}),
        extraction(),
        review(),
        ToolCall("consult_application", {"candidate": "C1"}),
        reply(),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.ANSWER
    assert [call.agent for call in llm.calls] == ["root", "application", "application", "root", "root"]


async def test_specialist_calls_share_the_roots_model_budget(
    monkeypatch: pytest.MonkeyPatch,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    monkeypatch.setattr(settings, "llm_agent_max_calls", 3)
    llm = FakeLlm(
        ToolCall("consult_application", {"candidate": "C1"}),
        extraction(),
        root_reply(RootReply(message="서류 검토가 예산 안에 끝나지 않았어요.", command=ClarifyCommand())),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.CLARIFY
    assert len(llm.calls) == 3
    assert plan.question_targets == [] and plan.targets == []
    assert [call.agent for call in llm.calls] == ["root", "application", "root"]
    assert "서류 근거" in plan.message and "완료하지 못" in plan.message


async def test_specialist_material_and_results_are_not_kept_in_conversation_checkpoints(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    document = context.documents[context.candidates[0].application_id][0]
    context.documents[context.candidates[0].application_id][0] = document.model_copy(
        update={"text": document.text + "\nPRIVATE-MATERIAL-SENTINEL"}
    )
    saver = InMemorySaver()
    thread = RootThread(id="delegation-test", company_id=context.company.company_id, stage_id=context.stage_id)
    llm = FakeLlm(ToolCall("consult_application", {"candidate": "C1"}), extraction(), review(), reply())

    await run_plan(llm, context, saver=saver, thread=thread)

    snapshots = [snapshot async for snapshot in saver.alist({"configurable": {"thread_id": thread.id}})]
    saved = json.dumps([snapshot.checkpoint for snapshot in snapshots], ensure_ascii=False, default=str)
    assert STATEMENT in saved
    assert "PRIVATE-MATERIAL-SENTINEL" not in saved
    assert DOCUMENT not in saved
    assert '"D1"' not in saved


async def test_root_reuses_independently_saved_extraction_but_still_reviews_all_claims(
    db_session: AsyncSession,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    document = context.documents[context.candidates[0].application_id][0]
    store = artifact_store(db_session)
    recipe = extraction_recipe(FakeLlm())
    assert recipe is not None
    await store.save_extraction(
        company_id=context.company.company_id,
        recruitment_id=context.recruitment_id,
        application_id=context.candidates[0].application_id,
        document=document,
        recipe_hash=recipe,
        extracted=extraction(),
    )
    before = await db_session.scalar(select(func.count()).select_from(AnalysisArtifactRecord))
    toolkit = replace(default_toolkit(), artifacts=store)
    for _ in range(2):
        llm = FakeLlm(ToolCall("consult_application", {"candidate": "C1"}), review(), reply())
        plan = await run_plan(llm, context, toolkit)
        assert plan.intent is Intent.ANSWER
        assert [call.agent for call in llm.calls] == ["root", "application", "root"]
        assert DOCUMENT in llm.calls[1].user
    assert await db_session.scalar(select(func.count()).select_from(AnalysisArtifactRecord)) == before


async def test_explicit_fresh_review_bypasses_independent_extraction_reuse(
    db_session: AsyncSession,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    store = artifact_store(db_session)
    recipe = extraction_recipe(FakeLlm())
    assert recipe is not None
    await store.save_extraction(
        company_id=context.company.company_id,
        recruitment_id=context.recruitment_id,
        application_id=context.candidates[0].application_id,
        document=context.documents[context.candidates[0].application_id][0],
        recipe_hash=recipe,
        extracted=extraction(),
    )
    llm = FakeLlm(
        ToolCall("consult_application", {"candidate": "C1", "force_review": True}),
        extraction(),
        review(),
        reply(),
    )
    plan = await run_plan(llm, context, replace(default_toolkit(), artifacts=store))
    assert plan.intent is Intent.ANSWER
    assert [call.agent for call in llm.calls] == ["root", "application", "application", "root"]


def artifact_store(session: AsyncSession) -> DbAnalysisArtifacts:
    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        yield session

    return DbAnalysisArtifacts(sessions)


async def test_three_documents_leave_a_final_answer_when_interview_review_hits_the_budget(
    monkeypatch: pytest.MonkeyPatch,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    application_id = context.candidates[0].application_id
    document = context.documents[application_id][0]
    context.documents[application_id] = [document.model_copy(update={"file_id": uuid4()}) for _ in range(3)]
    monkeypatch.setattr(settings, "llm_agent_max_calls", 8)
    final = reply()
    final.args["message"] = "서류와 면접을 모두 검토 완료했어요."
    llm = FakeLlm(
        ToolCall("resolve_candidates", {"names": [context.candidates[0].name]}),
        ToolCall("consult_application", {"candidate": "C1"}),
        extraction(),
        extraction(),
        extraction(),
        review(),
        ToolCall("consult_interview", {"candidate": "C1", "previous_results": ["D1"]}),
        final,
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.ANSWER
    assert len(llm.calls) == 8
    assert not any(call.agent == "interview" for call in llm.calls)
    assert len(plan.items) == 1 and plan.items[0].text == STATEMENT
    assert "면접" in plan.message and "완료하지 못" in plan.message
    assert "모두 검토 완료" not in plan.message
    assert plan.targets == [] and plan.question_targets == []


@pytest.mark.parametrize("force_review,with_reference", [(False, False), (True, False), (False, True)])
async def test_root_reuses_independent_interview_only_for_matching_unreferenced_review(
    db_session: AsyncSession,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    force_review: bool,
    with_reference: bool,
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    application_id = context.candidates[0].application_id
    view = context.interviews[application_id]
    data = InterviewAnalysisInput(
        company_id=context.company.company_id,
        recruitment_id=context.recruitment_id,
        application_id=application_id,
        stage_id=context.stage_id,
        stage_name=context.stage_name,
        questions=[AnsweredQuestion(text=q.text, answer=q.answer) for q in view.questions],
        previous=[],
    )
    store = artifact_store(db_session)
    analysis = await analyze_interview(data, FakeLlm(interview_draft()))
    recipe = interview_recipe(FakeLlm())
    assert recipe is not None
    await store.save_interview(data, analysis, recipe_hash=recipe)
    before = await db_session.scalar(select(func.count()).select_from(AnalysisArtifactRecord))
    responses: list[FakeReply] = []
    if with_reference:
        responses.extend([ToolCall("consult_application", {"candidate": "C1"}), extraction(), review()])
    responses.append(
        ToolCall(
            "consult_interview",
            {
                "candidate": "C1",
                "force_review": force_review,
                "previous_results": ["D1"] if with_reference else [],
            },
        )
    )
    if force_review or with_reference:
        responses.append(interview_draft())
    responses.append(reply(source="면접 기록", sentence=ANSWER))
    llm = FakeLlm(*responses)

    plan = await run_plan(llm, context, replace(default_toolkit(), artifacts=store))

    assert plan.intent is Intent.ANSWER
    assert any(call.agent == "interview" for call in llm.calls) is (force_review or with_reference)
    assert plan.items[0].text == INTERVIEW_STATEMENT
    assert await db_session.scalar(select(func.count()).select_from(AnalysisArtifactRecord)) == before


async def test_three_cached_documents_and_interview_finish_within_eight_calls(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    application_id = context.candidates[0].application_id
    document = context.documents[application_id][0]
    documents = [document.model_copy(update={"file_id": uuid4()}) for _ in range(3)]
    context.documents[application_id] = documents
    monkeypatch.setattr(settings, "llm_agent_max_calls", 8)
    store = artifact_store(db_session)
    recipe = extraction_recipe(FakeLlm())
    assert recipe is not None
    for cached_document in documents:
        await store.save_extraction(
            company_id=context.company.company_id,
            recruitment_id=context.recruitment_id,
            application_id=application_id,
            document=cached_document,
            recipe_hash=recipe,
            extracted=extraction(),
        )
    final = reply(source="면접 기록", sentence=ANSWER)
    final.args["items"].insert(0, reply().args["items"][0])
    final.args["message"] = "서류와 면접을 함께 검토했어요."
    llm = FakeLlm(
        ToolCall("resolve_candidates", {"names": [context.candidates[0].name]}),
        ToolCall("consult_application", {"candidate": "C1"}),
        review(),
        ToolCall("consult_interview", {"candidate": "C1", "previous_results": ["D1"]}),
        interview_draft(),
        final,
    )

    plan = await run_plan(llm, context, replace(default_toolkit(), artifacts=store))

    assert plan.intent is Intent.ANSWER
    assert [call.agent for call in llm.calls] == ["root", "root", "application", "root", "interview", "root"]
    assert len(plan.items) == 2
    assert plan.message == "서류와 면접을 함께 검토했어요."
    assert plan.agents == ["Application Agent", "Interview Agent"]
    assert plan.sources == ["이력서", "면접 기록"]
    assert await db_session.scalar(select(func.count()).select_from(AnalysisArtifactRecord)) == 3
