from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from root_context import form_call, make_context

from hiremate_ai.agents.root.find import RecheckItem, RecheckResult
from hiremate_ai.agents.root.graph import RootThread, build_root_graph, run_plan
from hiremate_ai.agents.root.memory import get_saver
from hiremate_ai.agents.root.review import ClaimJudgement, ClaimVerdict
from hiremate_ai.agents.root.turns import Turn
from hiremate_ai.agents.root.types import ChatContext, ChatItem, ChatPlan, EditAction, Intent
from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType
from hiremate_ai.llm.client import get_llm
from hiremate_ai.llm.fake import FakeLlm, FakeReply, LlmCall, ToolCall
from hiremate_ai.main import app

type Applicants = dict[str, ApplicantDetail]

FOCUS = "정산 배치를 줄인 설계 판단을 기술 심화로 확인"


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


def plan_calls(llm: FakeLlm) -> list[LlmCall]:
    return [call for call in llm.calls if call.output.__name__ == "RootPlan"]


def supported(count: int) -> ClaimJudgement:
    return ClaimJudgement(
        verdicts=[ClaimVerdict(id=f"I{number}", verdict="SUPPORTED") for number in range(1, count + 1)]
        + [ClaimVerdict(id="M", verdict="SUPPORTED")]
    )


def answer(
    *candidates: str, message: str = "세부 근거는 추가 확인이 필요해요.", scope: dict[str, Any] | None = None
) -> list[FakeReply]:
    """계획(answer), 분석 루프의 답, 근거 검토 순서의 모델 응답. 항목은 근거 없이 확인 필요로 낸다."""
    items = [
        {"candidate": ref, "label": "확인할 점", "text": "추가 확인이 필요해요.", "status": "CHECK", "refs": []}
        for ref in candidates
    ]
    return [
        form_call("answer", scope=scope or {"sources": ["all"]}),
        form_call("answer", message=message, items=items),
        supported(len(candidates)),
    ]


def edit(action: EditAction, *names: str, sources: tuple[str, ...] = ()) -> ToolCall:
    scope: dict[str, Any] = {"names": list(names)} if names else {}
    if sources:
        scope["sources"] = list(sources)
    return form_call("edit", action=action.value, scope=scope)


def questions(focus: str) -> list[FakeReply]:
    return [
        form_call("questions", scope={"sources": ["mentions"]}, checks="documents", replace=False),
        form_call(
            "questions",
            message="면접 질문의 확인할 점을 정리했어요.",
            focus=[{"candidate": "C1", "text": focus, "refs": ["E1"]}],
        ),
    ]


def clarify(message: str = "어떤 내용을 확인할까요?") -> ToolCall:
    return form_call("clarify", message=message)


FINANCE_FOUND = RecheckResult(results=[RecheckItem(candidate_no=no, met=True, sentence_nos=[1]) for no in (1, 2, 6)])


def search(*, concept: str = "금융 도메인 경험", mode: str = "replace", within: bool = False) -> list[FakeReply]:
    query = {"mode": mode, "concepts": [concept], "min_score": None}
    replies: list[FakeReply] = [
        form_call("find", query=query, scope={"sources": ["result"]} if within else {}, remove=False)
    ]
    if concept == "금융 도메인 경험":
        replies.append(FINANCE_FOUND)
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
    llm = FakeLlm(*answer("C1", scope={"picks": ["C1"]}))
    await run_plan(llm, ask(context, "그중 첫 번째 사람은?"), saver=saver, thread=thread)
    screen = plan_calls(llm)[0].user
    assert "[이전 결과] 1. C1 정유민" in screen and "[직전 대상] C1 정유민" in screen


async def test_applied_empty_search_restores_the_subject_before_the_proposed_plan(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    await run_plan(FakeLlm(*answer("C3")), ask(context, "박서준 확인해줘"), saver=saver, thread=thread)
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
    previous = await run_plan(FakeLlm(edit(EditAction.ADD, "정유민")), context, saver=saver, thread=thread)
    before = await saved_values(saver, thread)
    question = "다른 질문" if mismatch == "message" else context.message
    original = previous.model_copy(update={"message": "다른 계획"}) if mismatch == "previous" else previous

    assert not confirm_plan(saver, thread, question, original, previous)
    assert await saved_values(saver, thread) == before


@pytest.mark.parametrize("field", ["targets", "items", "question_targets", "question_focus"])
async def test_applied_rejects_candidates_outside_the_original_plan(context: ChatContext, field: str) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    previous = await run_plan(FakeLlm(edit(EditAction.ADD, "정유민")), context, saver=saver, thread=thread)
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
    next_question = form_call("questions", scope={"names": ["박서준"]}, checks="none", replace=False)
    await run_plan(FakeLlm(next_question), ask(interview, "박서준 면접 질문 만들어줘"), saver=saver, thread=thread)
    final = previous.model_copy(update={"targets": previous.targets[:1], "items": previous.items[:1]})

    assert confirm_plan(saver, thread, question, previous, final)

    values = await saved_values(saver, thread)
    assert values["turns"][0]["plan"] == final.model_dump(mode="json")
    assert values["result"] == values["subject"] == [str(ids(interview, "박서준")[0])]


async def test_late_applied_corrects_the_result_carried_through_a_clarification(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    question = "금융 경험 있는 사람 찾아줘"
    previous = await run_plan(FakeLlm(*search()), ask(context, question), saver=saver, thread=thread)
    await run_plan(FakeLlm(clarify()), ask(context, "확인해줘"), saver=saver, thread=thread)
    final = previous.model_copy(update={"targets": previous.targets[:1], "items": previous.items[:1]})

    assert confirm_plan(saver, thread, question, previous, final)

    values = await saved_values(saver, thread)
    assert values["turns"][-1]["intent"] == "CLARIFY"
    assert values["result"] == values["subject"] == [str(previous.targets[0])]


async def test_applied_can_record_backend_resolved_clear_targets(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    previous = await run_plan(FakeLlm(edit(EditAction.CLEAR)), context, saver=saver, thread=thread)
    final = previous.model_copy(update={"targets": ids(context, "김하늘"), "message": "실제 1명을 반영했어요."})

    assert confirm_plan(saver, thread, context.message, previous, final)

    values = await saved_values(saver, thread)
    assert values["subject"] == [str(ids(context, "김하늘")[0])]


async def test_applied_is_idempotent_and_does_not_overwrite_an_already_confirmed_plan(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    previous = await run_plan(FakeLlm(edit(EditAction.ADD, "정유민", "김하늘")), context, saver=saver, thread=thread)
    final = previous.model_copy(update={"targets": previous.targets[:1], "message": "실제 1명을 넣었어요."})

    assert confirm_plan(saver, thread, context.message, previous, final)
    checkpoints = len(saver.storage[thread.id][""])
    assert confirm_plan(saver, thread, context.message, previous, final)
    assert len(saver.storage[thread.id][""]) == checkpoints
    assert not confirm_plan(saver, thread, context.message, previous, final.model_copy(update={"message": "다른 답"}))
    assert (await saved_turns(saver, thread))[-1]["plan"] == final.model_dump(mode="json")


async def test_applied_rejects_ambiguous_identical_pending_turns(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    previous = await run_plan(FakeLlm(edit(EditAction.ADD, "정유민")), context, saver=saver, thread=thread)
    await run_plan(FakeLlm(edit(EditAction.ADD, "정유민")), context, saver=saver, thread=thread)
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
    previous = await run_plan(FakeLlm(edit(action, "정유민")), ask(context, question), saver=saver, thread=thread)
    first = (
        previous.model_copy(update={"message": "선택 지원자에 1명을 새로 넣었어요."})
        if action is EditAction.ADD
        else previous
    )
    assert confirm_plan(saver, thread, question, previous, first)
    repeated = await run_plan(FakeLlm(edit(action, "정유민")), ask(context, question), saver=saver, thread=thread)
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
    await run_plan(FakeLlm(clarify()), ask(context, "확인해줘"), saver=saver, thread=thread)
    values = await saved_values(saver, thread)
    legacy = values["turns"][-1].copy()
    for field in ("mode", "result_before", "subject_before"):
        legacy.pop(field, None)
    graph = build_root_graph(FakeLlm(), checkpointer=saver)
    await graph.aupdate_state({"configurable": {"thread_id": thread.id}}, {"turns": [legacy]}, as_node="record")
    question = "정유민 빼줘"
    previous = await run_plan(
        FakeLlm(edit(EditAction.REMOVE, "정유민")), ask(context, question), saver=saver, thread=thread
    )
    final = previous.model_copy(update={"targets": [], "message": "요청한 1명은 현재 선택 지원자에 없어요."})

    assert confirm_plan(saver, thread, question, previous, final)

    values = await saved_values(saver, thread)
    assert values["result"] == [str(application_id) for application_id in found.targets]
    assert values["subject"] == [str(application_id) for application_id in found.targets]


async def test_second_turn_runs_full_graph(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    llm = FakeLlm(edit(EditAction.CLEAR), edit(EditAction.CLEAR))

    cleared = await run_plan(llm, context, saver=saver, thread=thread)
    again = await run_plan(llm, ask(context, "다시 비워줘"), saver=saver, thread=thread)

    assert (cleared.edit, again.edit) == (EditAction.CLEAR, EditAction.CLEAR)
    turns = await saved_turns(saver, thread)
    assert [turn["message"] for turn in turns] == ["비워줘", "다시 비워줘"]
    assert turns[1]["intent"] == Intent.EDIT.value
    assert "비워줘" in llm.calls[1].user.split('kind="history"', 1)[1]


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
        FakeLlm(*answer("C2", message="추가 확인할 점이에요.", scope={"sources": ["mentions"]})),
        ask(context, "@김하늘 강점은?", mentions=("김하늘",)),
        saver=saver,
        thread=thread,
    )
    turn = (await saved_turns(saver, thread))[0]
    kim = str(ids(context, "김하늘")[0])
    assert turn["targets"] == [kim]
    assert turn["answer"] == "추가 확인할 점이에요."
    assert turn["items"] == [
        {"application_id": kim, "label": "확인할 점", "text": "추가 확인이 필요해요.", "status": "CHECK"}
    ]
    assert turn["total"] == 8


async def test_state_has_no_documents(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    await run_plan(
        FakeLlm(*answer("C1", scope={"sources": ["mentions"]})),
        ask(context, "@정유민 강점은?", mentions=("정유민",)),
        saver=saver,
        thread=thread,
    )
    saved = await saver.aget_tuple({"configurable": {"thread_id": thread.id}})
    assert saved is not None
    stored = repr(saved.checkpoint["channel_values"])
    assert "Kafka" not in stored and "한빛카드 결제플랫폼팀" not in stored
    assert saved.metadata.get("stage_id") == str(context.stage_id)


async def test_request_values_are_not_saved(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    llm = FakeLlm(
        form_call("answer", scope={"sources": ["mentions"]}),
        ToolCall("read_candidates", {"candidates": ["C1"], "detail": "profile"}),
        *answer("C1")[1:],
    )
    await run_plan(llm, ask(context, "지원자 자료를 확인해줘", mentions=("정유민",)), saver=saver, thread=thread)
    namespaces = {*saver.storage[thread.id], *(key[1] for key in saver.writes), *(key[1] for key in saver.blobs)}
    assert namespaces == {""}
    stored = repr([saver.storage, saver.writes, saver.blobs])
    assert "[근거 확인]" not in stored and "E1" not in stored


async def test_ordinal_from_previous_result(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    llm = FakeLlm(*search(), *answer("C2", scope={"picks": ["C2"]}))
    first = await run_plan(llm, ask(context, "금융 경험 있는 사람 찾아줘"), saver=saver, thread=thread)
    plan = await run_plan(llm, ask(context, "그중 두 번째 사람 강점은?"), saver=saver, thread=thread)
    assert first.targets[1] == ids(context, "김하늘")[0]
    assert plan.items[0].application_id == first.targets[1]
    screen = plan_calls(llm)[-1].user
    assert "[이전 결과] 1. C1 정유민 2. C2 김하늘 3. C6 한예린" in screen
    assert "금융 경험 있는 사람 찾아줘" in screen.split('kind="history"', 1)[1]


async def test_subject_from_previous_turn(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    llm = FakeLlm(*answer("C2", scope={"sources": ["mentions"]}), edit(EditAction.REMOVE, sources=("subject",)))
    await run_plan(llm, ask(context, "@김하늘 강점은?", mentions=("김하늘",)), saver=saver, thread=thread)
    plan = await run_plan(llm, ask(context, "아까 그 사람 빼줘"), saver=saver, thread=thread)
    assert (plan.edit, plan.targets) == (EditAction.REMOVE, ids(context, "김하늘"))
    screen = plan_calls(llm)[-1].user
    assert "[직전 대상] C2 김하늘" in screen
    assert "@김하늘 강점은?" in screen.split('kind="history"', 1)[1]


async def test_saved_state_keeps_only_json_values(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    plan = await run_plan(
        FakeLlm(edit(EditAction.REMOVE, sources=("mentions",))),
        ask(context, "@김하늘 빼줘", mentions=("김하늘",)),
        saver=saver,
        thread=thread,
    )
    values = await saved_values(saver, thread)
    assert values.get("plan") is None and values.get("kind") in (None, "") and values.get("run") is None
    assert plan.edit is EditAction.REMOVE


async def test_empty_narrow_keeps_result(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    llm = FakeLlm(
        *search(),
        *search(concept="양자 컴퓨팅", mode="within_selected", within=True),
        *answer("C2", scope={"picks": ["C2"]}),
    )
    first = await run_plan(llm, ask(context, "금융 경험 있는 사람 찾아줘"), saver=saver, thread=thread)
    narrowed = await run_plan(llm, ask(context, "그중 양자 컴퓨팅 경험 있는 사람만"), saver=saver, thread=thread)
    assert (await saved_values(saver, thread))["result"] == [str(target) for target in first.targets]
    last = await run_plan(llm, ask(context, "그중 두 번째 사람 강점은?"), saver=saver, thread=thread)
    assert narrowed.intent is Intent.ANSWER and last.items[0].application_id == first.targets[1]


async def test_find_turn_records_only_found(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    llm = FakeLlm(
        *answer("C2", scope={"sources": ["mentions"]}),
        *search(concept="양자 컴퓨팅"),
        edit(EditAction.REMOVE, sources=("subject",)),
    )
    await run_plan(llm, ask(context, "@김하늘 강점은?", mentions=("김하늘",)), saver=saver, thread=thread)
    await run_plan(llm, ask(context, "양자 컴퓨팅 경험자 찾아줘"), saver=saver, thread=thread)
    plan = await run_plan(llm, ask(context, "아까 그 사람 빼줘"), saver=saver, thread=thread)
    assert (await saved_turns(saver, thread))[1]["targets"] == []
    assert plan.targets == ids(context, "김하늘")


async def test_clear_with_checked_keeps_subject(context: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(context)
    llm = FakeLlm(
        *answer("C2", scope={"sources": ["mentions"]}),
        edit(EditAction.CLEAR),
        edit(EditAction.REMOVE, sources=("subject",)),
    )
    await run_plan(llm, ask(context, "@김하늘 강점은?", mentions=("김하늘",)), saver=saver, thread=thread)
    await run_plan(llm, ask(context, "선택 비워줘", checked=("정유민",)), saver=saver, thread=thread)
    plan = await run_plan(llm, ask(context, "아까 그 사람 빼줘"), saver=saver, thread=thread)
    assert plan.targets == ids(context, "김하늘")


async def test_questions_become_ordered_result_for_followup(interview: ChatContext) -> None:
    saver, thread = InMemorySaver(), thread_of(interview)
    llm = FakeLlm(*questions(FOCUS), *answer("C1", message="이유를 정리했어요.", scope={"sources": ["result"]}))
    await run_plan(llm, interview, saver=saver, thread=thread)
    await run_plan(llm, ask(interview, "방금 만든 질문은 왜 만든 거야?"), saver=saver, thread=thread)
    assert (await saved_values(saver, thread))["result"] == [str(ids(interview, "정유민")[0])]
    assert "[이전 결과] 1. C1 정유민" in plan_calls(llm)[-1].user
    analysis = [call for call in llm.calls if call.output.__name__ == "AnalysisReply"][-1]
    assert FOCUS in analysis.user
