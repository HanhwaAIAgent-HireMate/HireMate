import json
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from root_context import make_context

from hiremate_ai.agents.root.agent import root_prompt, run_agent
from hiremate_ai.agents.root.answer import AnswerEvidence, AnswerItem
from hiremate_ai.agents.root.commands import (
    AnswerCommand,
    ClarifyCommand,
    EditCommand,
    FindCommand,
    QuestionsCommand,
    RootReply,
)
from hiremate_ai.agents.root.find import RecheckItem, RecheckResult
from hiremate_ai.agents.root.graph import RootThread, build_root_graph, run_plan
from hiremate_ai.agents.root.memory import forget_stage, get_saver
from hiremate_ai.agents.root.toolkit import default_toolkit
from hiremate_ai.agents.root.turns import Turn, turn_of
from hiremate_ai.agents.root.types import ChatContext, ChatItem, ChatPlan, Decision, EditAction, Intent
from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType
from hiremate_ai.llm.client import get_llm
from hiremate_ai.llm.fake import FakeLlm, FakeReply, LlmCall, ToolCall
from hiremate_ai.main import app

type Applicants = dict[str, ApplicantDetail]


@pytest.fixture
def context(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> ChatContext:
    return make_context(sample_applicants, sample_company, sample_posting, message="비워줘")


@pytest.fixture
def interview(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> ChatContext:
    return make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="@정유민 면접 질문 만들어줘",
        mentions=["정유민"],
        stage_type=StageType.INTERVIEW,
        previous_types=(StageType.DOCUMENT,),
    )


def ids(context: ChatContext, *names: str) -> list[UUID]:
    by_name = {row.name: row.application_id for row in context.candidates}
    return [by_name[name] for name in names]


def ask(
    context: ChatContext, message: str, *, checked: tuple[str, ...] = (), mentions: tuple[str, ...] = ()
) -> ChatContext:
    return context.model_copy(
        update={"message": message, "checked": ids(context, *checked), "mentions": ids(context, *mentions)}
    )


def screen_of(call: LlmCall) -> dict[str, Any]:
    screen: dict[str, Any] = json.loads(call.user.split('<data kind="screen">', 1)[1].split("</data>", 1)[0])
    return screen


def answer(*candidates: str, message: str = "세부 근거는 추가 확인이 필요해요.") -> RootReply:
    return RootReply(
        message=message,
        command=AnswerCommand(candidates=list(candidates)),
        items=[
            AnswerItem(candidate=ref, label="확인할 점", text="추가 확인이 필요해요.", status="CHECK")
            for ref in candidates
        ],
    )


def edit(action: EditAction, *candidates: str) -> RootReply:
    return RootReply(message="선택 요청을 처리했어요.", command=EditCommand(action=action, candidates=list(candidates)))


def questions(focus: str) -> RootReply:
    return RootReply(
        message="면접 질문의 확인할 점을 정리했어요.",
        command=QuestionsCommand(candidates=["C1"], focus={"C1": focus}),
        items=[AnswerItem(candidate="C1", label="확인할 점", text=focus, status="CHECK")],
    )


FINANCE_FOUND = RecheckResult(results=[RecheckItem(candidate_no=no, met=True, sentence_nos=[1]) for no in (1, 2, 6)])


def search(*, concept: str = "금융 도메인 경험", mode: str = "REPLACE") -> list[FakeReply]:
    replies: list[FakeReply] = [ToolCall("search_candidates", {"query": {"concepts": [concept], "mode": mode}})]
    if concept == "금융 도메인 경험":
        replies.append(FINANCE_FOUND)
    replies.append(RootReply(message="검색 결과예요.", command=FindCommand(result="S1")))
    return replies


def thread_of(context: ChatContext, member: UUID | None = None) -> RootThread:
    return RootThread(
        id=f"{context.company.company_id}:{context.stage_id}:{member or uuid4()}",
        company_id=context.company.company_id,
        stage_id=context.stage_id,
    )


async def saved_values(saver: InMemorySaver, thread: RootThread) -> dict[str, Any]:
    saved = await saver.aget_tuple({"configurable": {"thread_id": thread.id}})
    assert saved is not None
    values: dict[str, Any] = saved.checkpoint["channel_values"]
    return values


async def saved_turns(saver: InMemorySaver, thread: RootThread) -> list[Turn]:
    turns: list[Turn] = (await saved_values(saver, thread))["turns"]
    return turns


def confirm_plan(saver: InMemorySaver, thread: RootThread, message: str, previous: ChatPlan, plan: ChatPlan) -> bool:
    llm = FakeLlm()
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_saver] = lambda: saver
    try:
        response = TestClient(app).post(
            "/agents/root/applied",
            json={
                "applied": {
                    "threadId": thread.id,
                    "message": message,
                    "previous": previous.model_dump(mode="json"),
                    "plan": plan.model_dump(mode="json"),
                }
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert llm.calls == []
    applied: bool = response.json()["applied"]
    return applied


async def test_applied_partial_search_updates_history_and_the_next_result(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    question = "금융 경험 있는 사람 찾아줘"
    previous = await run_plan(FakeLlm(*search()), ask(context, question), saver=saver, thread=thread)
    accepted = previous.targets[:1]
    final = previous.model_copy(
        update={"targets": accepted, "items": previous.items[:1], "message": "검증을 통과한 1명을 선택했어요."}
    )

    assert confirm_plan(saver, thread, question, previous, final)

    values = await saved_values(saver, thread)
    assert values["turns"][-1]["plan"] == final.model_dump(mode="json")
    assert values["turns"][-1]["targets"] == [str(value) for value in accepted]
    assert values["result"] == values["subject"] == [str(value) for value in accepted]
    llm = FakeLlm(answer("C1"))
    await run_plan(llm, ask(context, "그중 첫 번째 사람은?"), saver=saver, thread=thread)
    assert screen_of(llm.calls[0])["이전 결과"] == ["C1"]
    assert screen_of(llm.calls[0])["직전 대상"] == ["C1"]


async def test_applied_empty_search_restores_the_subject_before_the_proposed_plan(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    await run_plan(FakeLlm(answer("C3")), ask(context, "박서준 확인해줘"), saver=saver, thread=thread)
    question = "금융 경험 있는 사람 찾아줘"
    previous = await run_plan(FakeLlm(*search()), ask(context, question), saver=saver, thread=thread)
    final = ChatPlan.answer(Intent.ANSWER, "현재 반영할 수 있는 지원자가 없어요.")

    assert confirm_plan(saver, thread, question, previous, final)

    values = await saved_values(saver, thread)
    assert values["turns"][-1]["targets"] == []
    assert values["result"] == []
    assert values["subject"] == [str(ids(context, "박서준")[0])]


async def test_applied_does_not_create_a_missing_thread(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    plan = ChatPlan.answer(Intent.ANSWER, "검토 결과예요.")

    assert not confirm_plan(saver, thread, "질문", plan, plan)
    assert [saved async for saved in saver.alist(None)] == []


@pytest.mark.parametrize("mismatch", ["message", "previous"])
async def test_applied_requires_the_original_question_and_plan(context: ChatContext, mismatch: str) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    previous = await run_plan(FakeLlm(edit(EditAction.ADD, "C1")), context, saver=saver, thread=thread)
    before = await saved_values(saver, thread)
    question = "다른 질문" if mismatch == "message" else context.message
    original = previous.model_copy(update={"message": "다른 계획"}) if mismatch == "previous" else previous

    assert not confirm_plan(saver, thread, question, original, previous)
    assert await saved_values(saver, thread) == before


@pytest.mark.parametrize("field", ["targets", "items", "question_targets", "question_focus"])
async def test_applied_rejects_candidates_outside_the_original_plan(context: ChatContext, field: str) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    previous = await run_plan(FakeLlm(edit(EditAction.ADD, "C1")), context, saver=saver, thread=thread)
    outsider = ids(context, "김하늘")[0]
    extra: object = [outsider]
    if field == "items":
        extra = [ChatItem(application_id=outsider, label="대상", text="추가 대상", status="OK")]
    if field == "question_focus":
        extra = {outsider: "확인할 점"}
    final = previous.model_copy(update={field: extra})
    before = await saved_values(saver, thread)

    assert not confirm_plan(saver, thread, context.message, previous, final)
    assert await saved_values(saver, thread) == before


async def test_late_applied_updates_its_turn_without_replacing_newer_result_or_subject(interview: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(interview)
    question = "금융 경험 있는 사람 찾아줘"
    previous = await run_plan(FakeLlm(*search()), ask(interview, question), saver=saver, thread=thread)
    next_question = RootReply(message="질문을 요청했어요.", command=QuestionsCommand(candidates=["C3"]))
    await run_plan(
        FakeLlm(ToolCall("resolve_candidates", {"names": ["박서준"]}), next_question),
        ask(interview, "박서준 면접 질문 만들어줘"),
        saver=saver,
        thread=thread,
    )
    final = previous.model_copy(update={"targets": previous.targets[:1], "items": previous.items[:1]})

    assert confirm_plan(saver, thread, question, previous, final)

    values = await saved_values(saver, thread)
    assert values["turns"][0]["plan"] == final.model_dump(mode="json")
    assert values["result"] == values["subject"] == [str(ids(interview, "박서준")[0])]


async def test_late_applied_corrects_the_result_carried_through_a_clarification(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    question = "금융 경험 있는 사람 찾아줘"
    previous = await run_plan(FakeLlm(*search()), ask(context, question), saver=saver, thread=thread)
    clarify = RootReply(message="어떤 내용을 확인할까요?", command=ClarifyCommand())
    await run_plan(FakeLlm(clarify), ask(context, "확인해줘"), saver=saver, thread=thread)
    final = previous.model_copy(update={"targets": previous.targets[:1], "items": previous.items[:1]})

    assert confirm_plan(saver, thread, question, previous, final)

    values = await saved_values(saver, thread)
    assert values["turns"][-1]["intent"] == "CLARIFY"
    assert values["result"] == values["subject"] == [str(previous.targets[0])]


@pytest.mark.parametrize("action", [EditAction.CLEAR, EditAction.RESTORE])
async def test_applied_can_record_backend_resolved_clear_and_restore_targets(
    context: ChatContext, action: EditAction
) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    previous = await run_plan(FakeLlm(edit(action)), context, saver=saver, thread=thread)
    final = previous.model_copy(update={"targets": ids(context, "김하늘"), "message": "실제 1명을 반영했어요."})

    assert confirm_plan(saver, thread, context.message, previous, final)

    values = await saved_values(saver, thread)
    assert values["subject"] == [str(ids(context, "김하늘")[0])]
    assert await forget_stage(saver, str(context.stage_id)) == 1


async def test_applied_is_idempotent_and_does_not_overwrite_an_already_confirmed_plan(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    previous = await run_plan(FakeLlm(edit(EditAction.ADD, "C1", "C2")), context, saver=saver, thread=thread)
    final = previous.model_copy(update={"targets": previous.targets[:1], "message": "실제 1명을 넣었어요."})

    assert confirm_plan(saver, thread, context.message, previous, final)
    checkpoints = len(saver.storage[thread.id][""])
    assert confirm_plan(saver, thread, context.message, previous, final)
    assert len(saver.storage[thread.id][""]) == checkpoints
    assert not confirm_plan(saver, thread, context.message, previous, final.model_copy(update={"message": "다른 답"}))
    assert (await saved_turns(saver, thread))[-1]["plan"] == final.model_dump(mode="json")


async def test_applied_rejects_ambiguous_identical_pending_turns(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    previous = await run_plan(FakeLlm(edit(EditAction.ADD, "C1")), context, saver=saver, thread=thread)
    await run_plan(FakeLlm(edit(EditAction.ADD, "C1")), context, saver=saver, thread=thread)
    final = previous.model_copy(update={"message": "실제 반영 결과"})
    before = await saved_values(saver, thread)

    assert not confirm_plan(saver, thread, context.message, previous, final)
    assert await saved_values(saver, thread) == before


@pytest.mark.parametrize("action", [EditAction.ADD, EditAction.REMOVE])
async def test_applied_repeated_question_corrects_the_new_pending_turn(
    context: ChatContext, action: EditAction
) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    question = "정유민 넣어줘" if action is EditAction.ADD else "정유민 빼줘"
    previous = await run_plan(FakeLlm(edit(action, "C1")), ask(context, question), saver=saver, thread=thread)
    first = (
        previous.model_copy(update={"message": "선택 지원자에 1명을 새로 넣었어요."})
        if action is EditAction.ADD
        else previous
    )
    assert confirm_plan(saver, thread, question, previous, first)
    repeated = await run_plan(FakeLlm(edit(action, "C1")), ask(context, question), saver=saver, thread=thread)
    assert repeated == previous
    message = (
        "요청한 1명은 이미 선택 지원자에 있어요."
        if action is EditAction.ADD
        else "요청한 1명은 현재 선택 지원자에 없어요."
    )
    final = repeated.model_copy(update={"targets": [], "message": message})

    assert confirm_plan(saver, thread, question, repeated, final)

    turns = await saved_turns(saver, thread)
    assert [turn["answer"] for turn in turns] == [first.message, final.message]


async def test_applied_preserves_a_result_carried_from_legacy_retained_turns(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    found = await run_plan(FakeLlm(*search()), ask(context, "금융 경험자 찾아줘"), saver=saver, thread=thread)
    clarify = RootReply(message="어떤 내용을 확인할까요?", command=ClarifyCommand())
    await run_plan(FakeLlm(clarify), ask(context, "확인해줘"), saver=saver, thread=thread)
    values = await saved_values(saver, thread)
    legacy = values["turns"][-1].copy()
    for field in ("mode", "result_before", "subject_before"):
        legacy.pop(field, None)
    graph = build_root_graph(FakeLlm(), checkpointer=saver)
    await graph.aupdate_state({"configurable": {"thread_id": thread.id}}, {"turns": [legacy]}, as_node="record")
    question = "정유민 빼줘"
    previous = await run_plan(
        FakeLlm(edit(EditAction.REMOVE, "C1")), ask(context, question), saver=saver, thread=thread
    )
    final = previous.model_copy(update={"targets": [], "message": "요청한 1명은 현재 선택 지원자에 없어요."})

    assert confirm_plan(saver, thread, question, previous, final)

    values = await saved_values(saver, thread)
    assert values["result"] == [str(application_id) for application_id in found.targets]
    assert values["subject"] == [str(application_id) for application_id in found.targets]


async def test_second_turn_runs_full_graph(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    llm = FakeLlm(edit(EditAction.CLEAR), edit(EditAction.RESTORE))

    cleared = await run_plan(llm, context, saver=saver, thread=thread)
    restored = await run_plan(llm, ask(context, "되돌려줘"), saver=saver, thread=thread)

    assert (cleared.edit, restored.edit) == (EditAction.CLEAR, EditAction.RESTORE)
    turns = await saved_turns(saver, thread)
    assert [turn["message"] for turn in turns] == ["비워줘", "되돌려줘"]
    assert turns[1]["intent"] == Intent.EDIT.value
    assert "비워줘" in llm.calls[1].user.split("앞 대화", 1)[1]


async def test_turns_keep_last_n(context: ChatContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "root_memory_turns", 3)
    saver, thread = InMemorySaver(), thread_of(context)
    for _ in range(5):
        await run_plan(FakeLlm(edit(EditAction.CLEAR)), context, saver=saver, thread=thread)
    assert len(await saved_turns(saver, thread)) == 3


async def test_threads_are_separate(context: ChatContext) -> None:
    saver = InMemorySaver()
    mine, theirs = thread_of(context), thread_of(context)
    for thread in (mine, theirs, theirs):
        await run_plan(FakeLlm(edit(EditAction.CLEAR)), context, saver=saver, thread=thread)
    assert len(await saved_turns(saver, mine)) == 1
    assert len(await saved_turns(saver, theirs)) == 2


async def test_turn_records_subject_and_answer(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    await run_plan(
        FakeLlm(answer("C2", message="추가 확인할 점이에요.")),
        ask(context, "@김하늘 강점은?", mentions=("김하늘",)),
        saver=saver,
        thread=thread,
    )
    turn = (await saved_turns(saver, thread))[0]
    kim = str(ids(context, "김하늘")[0])
    assert turn["targets"] == [kim]
    assert turn["answer"] == "추가 확인할 점이에요."
    assert turn["items"] == [{"application_id": kim, "label": "확인할 점", "text": "추가 확인이 필요해요."}]
    assert turn["total"] == 8


async def test_state_has_no_documents(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    await run_plan(
        FakeLlm(answer("C1")), ask(context, "@정유민 강점은?", mentions=("정유민",)), saver=saver, thread=thread
    )
    saved = await saver.aget_tuple({"configurable": {"thread_id": thread.id}})
    assert saved is not None
    stored = repr(saved.checkpoint["channel_values"])
    assert "Kafka" not in stored and "한빛카드 결제플랫폼팀" not in stored
    assert saved.metadata.get("stage_id") == str(context.stage_id)


async def test_tool_loop_is_not_saved(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    llm = FakeLlm(ToolCall("get_candidate_documents", {"candidate": "C1"}), answer("C1"))
    await run_plan(llm, ask(context, "지원자 자료를 확인해줘"), saver=saver, thread=thread)
    namespaces = {*saver.storage[thread.id], *(key[1] for key in saver.writes), *(key[1] for key in saver.blobs)}
    assert namespaces == {""}
    assert "Kafka" not in repr([saver.storage, saver.writes, saver.blobs])
    assert "Kafka" in llm.calls[-1].user


async def test_ordinal_from_previous_result(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    llm = FakeLlm(*search(), answer("C2"))
    first = await run_plan(llm, ask(context, "금융 경험 있는 사람 찾아줘"), saver=saver, thread=thread)
    plan = await run_plan(llm, ask(context, "그중 두 번째 사람 강점은?"), saver=saver, thread=thread)
    assert first.targets[1] == ids(context, "김하늘")[0]
    assert plan.items[0].application_id == first.targets[1]
    assert "이전 결과" in llm.calls[-1].user
    assert "금융 경험 있는 사람 찾아줘" in llm.calls[-1].user.split("앞 대화", 1)[1]


async def test_subject_from_previous_turn(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    llm = FakeLlm(answer("C2"), edit(EditAction.REMOVE, "C2"))
    await run_plan(llm, ask(context, "@김하늘 강점은?", mentions=("김하늘",)), saver=saver, thread=thread)
    plan = await run_plan(llm, ask(context, "아까 그 사람 빼줘"), saver=saver, thread=thread)
    assert (plan.edit, plan.targets) == (EditAction.REMOVE, ids(context, "김하늘"))
    assert "직전 대상" in llm.calls[-1].user
    assert "@김하늘 강점은?" in llm.calls[-1].user.split("앞 대화", 1)[1]


async def test_missing_previous_result_can_be_clarified_by_model(context: ChatContext) -> None:
    llm = FakeLlm(RootReply(message="앞에서 찾은 지원자가 없어요. 누구를 말씀하세요?", command=ClarifyCommand()))
    plan = await run_plan(
        llm, ask(context, "그중 두 번째 사람 강점은?"), saver=InMemorySaver(), thread=thread_of(context)
    )
    assert plan.intent is Intent.CLARIFY and plan.targets == []
    assert screen_of(llm.calls[0])["이전 결과"] is None
    assert screen_of(llm.calls[0])["직전 대상"] == []


async def test_stage_count_after_subject_uses_model_selected_scope(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    count = RootReply(
        message="미결정은 8명이에요.",
        command=AnswerCommand(),
        items=[
            AnswerItem(
                label="인원",
                text="미결정 지원자 8명",
                status="OK",
                evidence=[AnswerEvidence(sentence="미결정 8명", source="전형 결과")],
            )
        ],
    )
    llm = FakeLlm(answer("C2"), ToolCall("get_stage_summary"), count)
    await run_plan(llm, ask(context, "@김하늘 강점은?", mentions=("김하늘",)), saver=saver, thread=thread)

    plan = await run_plan(llm, ask(context, "미결정이 몇 명 남았어?"), saver=saver, thread=thread)

    assert (plan.intent, plan.message) == (Intent.ANSWER, "미결정은 8명이에요.")
    assert len(plan.items) == 1 and plan.items[0].application_id is None
    assert plan.sources == ["전형 결과"]
    assert "@김하늘 강점은?" in llm.calls[1].user.split("앞 대화", 1)[1]


async def test_stage_ranking_after_subject_reads_backend_evidence(context: ChatContext) -> None:
    context = context.model_copy(
        update={
            "candidates": [
                row.model_copy(update={"career_years": 7 if row.name == "김하늘" else 1}) for row in context.candidates
            ]
        }
    )
    saver, thread = InMemorySaver(), thread_of(context)
    ranking = RootReply(
        message="김하늘의 경력이 7년으로 가장 많아요.",
        command=AnswerCommand(candidates=["C2"]),
        items=[
            AnswerItem(
                candidate="C2",
                label="경력",
                text="경력 7년",
                status="OK",
                evidence=[AnswerEvidence(sentence="경력 7년", source="전형 결과")],
            )
        ],
    )
    llm = FakeLlm(answer("C1"), ToolCall("get_stage_summary"), ranking)
    await run_plan(llm, ask(context, "@정유민 강점은?", mentions=("정유민",)), saver=saver, thread=thread)

    plan = await run_plan(llm, ask(context, "경력이 가장 많은 사람은?"), saver=saver, thread=thread)

    assert plan.intent is Intent.ANSWER
    assert plan.message == ranking.message
    assert [(item.application_id, item.status) for item in plan.items] == [(ids(context, "김하늘")[0], "OK")]
    assert plan.sources == ["전형 결과"]
    assert screen_of(llm.calls[1])["직전 대상"] == ["C1"]
    assert (await saved_values(saver, thread))["subject"] == [str(ids(context, "김하늘")[0])]


async def test_remembered_candidate_must_be_in_stage(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    llm = FakeLlm(
        answer("C2"), RootReply(message="현재 전형에서 해당 지원자를 찾지 못했어요.", command=ClarifyCommand())
    )
    await run_plan(llm, ask(context, "@김하늘 강점은?", mentions=("김하늘",)), saver=saver, thread=thread)
    kim = ids(context, "김하늘")[0]
    later = ask(context, "아까 그 사람 빼줘").model_copy(
        update={"candidates": [row for row in context.candidates if row.application_id != kim]}
    )
    plan = await run_plan(llm, later, saver=saver, thread=thread)
    assert plan.intent is Intent.CLARIFY and plan.targets == []
    assert str(kim) not in llm.calls[-1].user
    assert screen_of(llm.calls[-1])["직전 대상"] == []


FOCUS = "정산 배치를 줄인 설계 판단을 기술 심화로 확인"


async def test_reason_question_reads_previous_turns(interview: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(interview)
    llm = FakeLlm(
        ToolCall("resolve_candidates", {"names": [], "source": "mentions"}),
        questions(FOCUS),
        ToolCall("get_previous_turns"),
        answer("C1", message="설계 판단을 확인하려고 만들었어요."),
    )
    await run_plan(llm, interview, saver=saver, thread=thread)
    plan = await run_plan(llm, ask(interview, "3번 질문은 왜 만든 거야?"), saver=saver, thread=thread)
    assert plan.message == "설계 판단을 확인하려고 만들었어요." and plan.question_targets == []
    assert FOCUS in llm.calls[-1].user
    assert "@정유민 면접 질문 만들어줘" in llm.calls[-1].user


async def test_refine_uses_previous_subject(interview: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(interview)
    llm = FakeLlm(
        ToolCall("resolve_candidates", {"names": [], "source": "mentions"}),
        questions(FOCUS),
        ToolCall("resolve_candidates", {"names": [], "source": "subject"}),
        questions("장애 대응을 더 기술적으로"),
    )
    await run_plan(llm, interview, saver=saver, thread=thread)
    plan = await run_plan(llm, ask(interview, "좀 더 기술적으로 다시 해줘"), saver=saver, thread=thread)
    jung = ids(interview, "정유민")[0]
    assert plan.question_targets == [jung]
    assert "장애 대응을 더 기술적으로" in plan.question_focus[jung]
    assert "좀 더 기술적으로 다시 해줘" in plan.question_focus[jung]
    assert FOCUS in llm.calls[-1].user


async def test_questions_become_ordered_result_for_followup(interview: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(interview)
    llm = FakeLlm(
        ToolCall("resolve_candidates", {"names": [], "source": "mentions"}),
        questions(FOCUS),
        answer("C1", message="이유를 정리했어요."),
    )
    await run_plan(llm, interview, saver=saver, thread=thread)
    await run_plan(llm, ask(interview, "방금 만든 질문은 왜 만든 거야?"), saver=saver, thread=thread)
    assert (await saved_values(saver, thread))["result"] == [str(ids(interview, "정유민")[0])]
    assert "이전 결과" in llm.calls[-1].user and FOCUS in llm.calls[-1].user


@pytest.mark.parametrize("source", ["subject", "result"])
async def test_contextual_question_followup_preserves_identity_with_a_same_name_candidate(
    interview: ChatContext, source: str
) -> None:
    original = interview.candidates[0].application_id
    duplicate = interview.candidates[0].model_copy(update={"application_id": uuid4()})
    interview = interview.model_copy(update={"candidates": [*interview.candidates, duplicate]})
    saver, thread = InMemorySaver(), thread_of(interview)
    llm = FakeLlm(
        ToolCall("resolve_candidates", {"names": [], "source": "mentions"}),
        questions(FOCUS),
        ToolCall("resolve_candidates", {"names": [], "source": source, "candidates": ["C1"]}),
        questions("장애 대응을 더 기술적으로"),
    )
    await run_plan(llm, interview, saver=saver, thread=thread)

    plan = await run_plan(llm, ask(interview, "그 사람 질문을 더 기술적으로 다시 만들어줘"), saver=saver, thread=thread)

    assert plan.intent is Intent.ANSWER
    assert plan.question_targets == [original]
    assert "장애 대응을 더 기술적으로" in plan.question_focus[original]
    assert (await saved_values(saver, thread))["subject"] == [str(original)]
    assert len(llm.calls) == 4


async def test_saved_state_keeps_only_json_values(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    plan = await run_plan(
        FakeLlm(edit(EditAction.REMOVE, "C2")),
        ask(context, "@김하늘 빼줘", mentions=("김하늘",)),
        saver=saver,
        thread=thread,
    )
    values = await saved_values(saver, thread)
    assert values.get("plan") is None and values.get("kind") in (None, "") and values.get("searches") is None
    assert plan.edit is EditAction.REMOVE


@pytest.mark.parametrize("followup", ["그중 두 번째 사람 강점은?", "그중 첫 번째 사람 강점은?"])
async def test_empty_latest_result_is_visible_to_model(context: ChatContext, followup: str) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    llm = FakeLlm(
        *search(),
        *search(concept="양자 컴퓨팅"),
        RootReply(message="최근 검색 결과가 비어 있어요.", command=ClarifyCommand()),
    )
    await run_plan(llm, ask(context, "금융 경험 있는 사람 찾아줘"), saver=saver, thread=thread)
    await run_plan(llm, ask(context, "양자 컴퓨팅 경험자 찾아줘"), saver=saver, thread=thread)
    assert (await saved_values(saver, thread))["result"] == []
    plan = await run_plan(llm, ask(context, followup), saver=saver, thread=thread)
    assert plan.intent is Intent.CLARIFY and plan.targets == []
    assert screen_of(llm.calls[-1])["이전 결과"] == []


async def test_model_can_compare_checked_candidates_after_a_search(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    llm = FakeLlm(*search(), answer("C3", "C4", message="두 사람을 비교했어요."))
    await run_plan(llm, ask(context, "금융 경험 있는 사람 찾아줘"), saver=saver, thread=thread)
    plan = await run_plan(llm, ask(context, "둘 비교해줘", checked=("박서준", "이도윤")), saver=saver, thread=thread)
    assert {item.application_id for item in plan.items} == set(ids(context, "박서준", "이도윤"))
    assert "체크" in llm.calls[-1].user and "이전 결과" in llm.calls[-1].user


async def test_model_can_choose_previous_subject_while_another_candidate_is_checked(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    llm = FakeLlm(answer("C2"), edit(EditAction.REMOVE, "C2"))
    await run_plan(llm, ask(context, "@김하늘 강점은?", mentions=("김하늘",)), saver=saver, thread=thread)
    plan = await run_plan(llm, ask(context, "아까 그 사람 빼줘", checked=("정유민",)), saver=saver, thread=thread)
    assert plan.targets == ids(context, "김하늘")
    assert "체크" in llm.calls[-1].user and "직전 대상" in llm.calls[-1].user


async def test_empty_narrow_keeps_result(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    llm = FakeLlm(*search(), *search(concept="양자 컴퓨팅", mode="NARROW"), answer("C2"))
    first = await run_plan(llm, ask(context, "금융 경험 있는 사람 찾아줘"), saver=saver, thread=thread)
    narrowed = await run_plan(llm, ask(context, "그중 양자 컴퓨팅 경험 있는 사람만"), saver=saver, thread=thread)
    assert (await saved_values(saver, thread))["result"] == [str(target) for target in first.targets]
    last = await run_plan(llm, ask(context, "그중 두 번째 사람 강점은?"), saver=saver, thread=thread)
    assert narrowed.intent is Intent.ANSWER and last.items[0].application_id == first.targets[1]


async def test_find_turn_records_only_found(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    llm = FakeLlm(answer("C2"), *search(concept="양자 컴퓨팅"), edit(EditAction.REMOVE, "C2"))
    await run_plan(llm, ask(context, "@김하늘 강점은?", mentions=("김하늘",)), saver=saver, thread=thread)
    await run_plan(llm, ask(context, "양자 컴퓨팅 경험자 찾아줘"), saver=saver, thread=thread)
    plan = await run_plan(llm, ask(context, "아까 그 사람 빼줘"), saver=saver, thread=thread)
    assert (await saved_turns(saver, thread))[1]["targets"] == []
    assert plan.targets == ids(context, "김하늘")


async def test_clear_with_checked_keeps_subject(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    llm = FakeLlm(answer("C2"), edit(EditAction.CLEAR), edit(EditAction.REMOVE, "C2"))
    await run_plan(llm, ask(context, "@김하늘 강점은?", mentions=("김하늘",)), saver=saver, thread=thread)
    await run_plan(llm, ask(context, "선택 비워줘", checked=("정유민",)), saver=saver, thread=thread)
    plan = await run_plan(llm, ask(context, "아까 그 사람 빼줘"), saver=saver, thread=thread)
    assert plan.targets == ids(context, "김하늘")


async def test_previous_subject_is_remapped_after_candidate_order_changes(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    llm = FakeLlm(answer("C2"), edit(EditAction.REMOVE, "C1"))
    await run_plan(llm, ask(context, "@김하늘 강점은?", mentions=("김하늘",)), saver=saver, thread=thread)
    rows = [context.candidates[1], context.candidates[0], *context.candidates[2:]]
    reordered = ask(context, "아까 그 사람 빼줘").model_copy(update={"candidates": rows})

    plan = await run_plan(llm, reordered, saver=saver, thread=thread)

    assert plan.targets == ids(context, "김하늘")
    assert screen_of(llm.calls[-1])["직전 대상"] == ["C1"]


async def test_clarified_screen_targets_survive_cleared_chips_and_candidate_reordering(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    llm = FakeLlm(
        RootReply(message="어떤 기준으로 검토할까요?", command=ClarifyCommand()),
        ToolCall("get_previous_turns"),
        answer("C1"),
    )
    await run_plan(
        llm,
        ask(context, "우리 회사와 잘 맞아?", mentions=("김하늘",), checked=("정유민",)),
        saver=saver,
        thread=thread,
    )
    rows = [context.candidates[1], context.candidates[0], *context.candidates[2:]]
    followup = ask(context, "등록한 인재상을 기준으로 봐줘").model_copy(update={"candidates": rows})

    await run_plan(llm, followup, saver=saver, thread=thread)

    read = llm.calls[-1].user.split('<data kind="tool" name="get_previous_turns">', 1)[1]
    assert "멘션한 지원자: C1 김하늘" in read
    assert "체크한 지원자: C2 정유민" in read
    history = json.loads(llm.calls[1].user.split('<data kind="history">', 1)[1].split("</data>", 1)[0])
    assert history[0]["멘션한 지원자"] == ["C1"]
    assert history[0]["체크한 지원자"] == ["C2"]
    assert screen_of(llm.calls[1])["멘션한 지원자"] == []
    assert screen_of(llm.calls[1])["체크한 지원자"] == []
    assert (await saved_turns(saver, thread))[0]["targets"] == []


async def test_previous_turns_omit_screen_targets_outside_the_current_stage(context: ChatContext) -> None:
    prior = turn_of(
        ask(context, "우리 회사와 잘 맞아?", mentions=("김하늘",), checked=("정유민",)),
        None,
        ChatPlan.answer(Intent.CLARIFY, "어떤 기준으로 검토할까요?"),
        "ANSWER",
    )
    kim = ids(context, "김하늘")[0]
    followup = ask(context, "등록한 인재상을 기준으로 봐줘").model_copy(
        update={"candidates": [row for row in context.candidates if row.application_id != kim]}
    )
    llm = FakeLlm(ToolCall("get_previous_turns"), answer("C1"))

    await run_agent(llm, followup, default_toolkit(), turns=[prior])

    read = llm.calls[-1].user.split('<data kind="tool" name="get_previous_turns">', 1)[1]
    assert "멘션한 지원자:" not in read
    assert "체크한 지원자: C1 정유민" in read
    assert "김하늘" not in read and str(kim) not in read


async def test_previous_turns_can_read_legacy_turns_without_screen_targets(context: ChatContext) -> None:
    prior = turn_of(ask(context, "기존 질문"), None, ChatPlan.answer(Intent.CLARIFY, "기존 답변"), "ANSWER")
    prior.pop("mentions", None)
    prior.pop("checked", None)
    llm = FakeLlm(ToolCall("get_previous_turns"), answer("C1"))

    await run_agent(llm, ask(context, "아까 무슨 말을 했지?"), default_toolkit(), turns=[prior])

    read = llm.calls[-1].user.split('<data kind="tool" name="get_previous_turns">', 1)[1]
    assert '담당자: "기존 질문"' in read
    assert "Root 답: 기존 답변" in read
    assert "멘션한 지원자:" not in read and "체크한 지원자:" not in read


def test_root_prompt_emits_screen_identity_facts_once(context: ChatContext) -> None:
    context = ask(context, "지원자 검토해줘", mentions=("정유민",))
    context = context.model_copy(
        update={"candidates": [row.model_copy(update={"selected": row.name == "박서준"}) for row in context.candidates]}
    )

    prompt = root_prompt(context, [], None, [])
    screen = json.loads(prompt.split('<data kind="screen">', 1)[1].split("</data>", 1)[0])

    # C1 is needed in its catalog row and the mention list, with no repeated mention sentence.
    assert prompt.count("C1") == 2
    assert screen["선택 지원자"] == ["C3"]
    assert all("선택 여부" not in row for row in screen["지원자"])


@pytest.mark.parametrize("result, expected", [(None, None), ([], []), (["김하늘", "정유민"], ["C2", "C1"])])
def test_root_prompt_preserves_distinct_scopes_and_full_catalog(
    context: ChatContext, result: list[str] | None, expected: list[str] | None
) -> None:
    context = ask(context, "그중 두 번째 사람 검토해줘", mentions=("정유민",), checked=("김하늘",))
    context = context.model_copy(
        update={
            "candidates": [
                row.model_copy(
                    update={
                        "selected": row.name == "박서준",
                        "decision": Decision.PASS if row.name == "이도윤" else Decision.PENDING,
                        "above_line": row.name != "한예린",
                    }
                )
                for row in context.candidates
            ]
        }
    )
    previous = None if result is None else [str(value) for value in ids(context, *result)]
    prompt = root_prompt(context, [], previous, [str(value) for value in ids(context, "이도윤")])
    screen = json.loads(prompt.split('<data kind="screen">', 1)[1].split("</data>", 1)[0])

    assert screen["멘션한 지원자"] == ["C1"]
    assert screen["체크한 지원자"] == ["C2"]
    assert screen["선택 지원자"] == ["C3"]
    assert screen["이전 결과"] == expected
    assert screen["직전 대상"] == ["C4"]
    assert screen["선택 변경 가능"] is True
    assert len(screen["지원자"]) == 8
    assert [row["번호"] for row in screen["지원자"]] == ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"]
    assert screen["지원자"][3]["결정"] == "PASS"
    assert screen["지원자"][5]["기준선 위"] is False
    assert [row["이름"] for row in screen["지원자"]] == [row.name for row in context.candidates]
    assert all(str(row.application_id) not in prompt for row in context.candidates)


def test_history_keeps_question_focus_once_and_references_it_from_the_matching_item(context: ChatContext) -> None:
    application_id = context.candidates[0].application_id
    plan = ChatPlan.answer(Intent.ANSWER, "질문을 확인할 점과 함께 정리했어요.").model_copy(
        update={
            "items": [ChatItem(application_id=application_id, label="확인할 점", text=FOCUS, status="CHECK")],
            "question_focus": {application_id: FOCUS},
        }
    )
    prior = turn_of(context, [application_id], plan, "ANSWER")

    prompt = root_prompt(context, [prior], None, [])
    history = json.loads(prompt.split('<data kind="history">', 1)[1].split("</data>", 1)[0])

    assert prompt.count(FOCUS) == 1
    assert history[0]["대화 번호"] == 1
    assert history[0]["확인할 점"]["C1"] == FOCUS
    assert history[0]["항목"][0]["text_ref"] == "확인할 점/C1"
    assert history[0]["항목"][0]["application_id"] == "C1"
    assert "text" not in history[0]["항목"][0]
