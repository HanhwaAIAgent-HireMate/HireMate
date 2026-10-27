from typing import Any, cast

import pytest
from root_context import extra_row, make_context, root_reply

from hiremate_ai.agents.guardrails import BLOCKED_REPLY
from hiremate_ai.agents.root.agent import NOT_FINISHED, root_prompt
from hiremate_ai.agents.root.graph import CHECKING, build_root_graph, run_plan, stream_plan
from hiremate_ai.agents.root.toolkit import OUT_OF_SCOPE
from hiremate_ai.agents.root.types import ChatItem, ChatPlan, ChatStatus, EditAction, Intent
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.fake import FakeLlm, LlmCall, ToolCall

type Applicants = dict[str, ApplicantDetail]


def reply(kind: str, **command: Any) -> ToolCall:
    return root_reply({"message": "요청을 확인했어요.", "command": {"kind": kind, **command}})


async def test_blocked_skips_model(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="30대 남자 찾아줘")
    llm = FakeLlm()

    assert await run_plan(llm, context) == ChatPlan.answer(Intent.BLOCKED, BLOCKED_REPLY)
    assert llm.calls == []


async def test_model_failure_returns_clarification(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    def broken(call: LlmCall) -> ToolCall:
        raise LlmOutputError("모델 출력을 확인하지 못했다")

    context = make_context(sample_applicants, sample_company, sample_posting, message="음")

    assert await run_plan(FakeLlm(broken), context) == ChatPlan.answer(Intent.CLARIFY, NOT_FINISHED)


async def test_decision_only_guides_the_user_to_the_screen(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="이 사람 합격시켜줘")

    plan = await run_plan(FakeLlm(reply("decision")), context)

    assert plan.intent is Intent.CLARIFY
    assert "화면" in plan.message
    assert plan.targets == [] and plan.question_targets == []


async def test_model_can_ask_to_disambiguate_same_names(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="정유민 빼줘", extra_rows=[extra_row("정유민")]
    )
    llm = FakeLlm(root_reply({"message": "어느 정유민 님인가요?", "command": {"kind": "clarify"}}))

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.CLARIFY
    assert plan.targets == []
    assert llm.calls[0].user.count('"이름": "정유민"') == 2


async def test_invalid_targets_are_repaired_without_applying_the_first_command(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="선택에서 빼줘")
    llm = FakeLlm(
        reply("edit", action="REMOVE", candidates=["C999"]), reply("edit", action="REMOVE", candidates=["C1"])
    )

    plan = await run_plan(llm, context)

    assert plan.edit is EditAction.REMOVE
    assert plan.targets == [context.candidates[0].application_id]
    assert "검증" in llm.calls[1].user


async def test_repeated_invalid_commands_do_not_escape_the_loop(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="선택에서 빼줘")
    llm = FakeLlm(
        reply("edit", action="REMOVE", candidates=["C999"]), reply("edit", action="REMOVE", candidates=["C999"])
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.CLARIFY
    assert plan.targets == []
    assert len(llm.calls) == 2


async def test_repeated_invalid_answers_emit_no_unverified_items(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="강점 알려줘")
    invented = root_reply(
        {
            "message": "증권사 경력이 10년이에요.",
            "command": {"kind": "answer", "candidates": ["C1"]},
            "items": [
                {
                    "candidate": "C1",
                    "label": "강점",
                    "text": "증권사 경력 10년",
                    "status": "OK",
                    "evidence": [{"sentence": "증권사에서 10년 일했습니다.", "source": "이력서"}],
                }
            ],
        },
    )

    events = [event async for event in stream_plan(FakeLlm(invented, invented), context)]

    assert all(name != "item" for name, _ in events)
    final = events[-1][1]
    assert isinstance(final, ChatPlan)
    assert "증권사" not in final.message


async def test_question_command_only_carries_validated_targets_and_focus(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="정유민 질문 만들어줘",
        stage_type=StageType.INTERVIEW,
    )
    llm = FakeLlm(
        ToolCall("resolve_candidates", {"names": ["정유민"]}),
        root_reply(
            {
                "message": "질문을 만들어요.",
                "command": {"kind": "questions", "candidates": ["C1"], "focus": {"C1": "본인 역할을 확인"}},
                "items": [{"candidate": "C1", "label": "확인할 점", "text": "본인 역할을 확인", "status": "CHECK"}],
            },
        ),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.ANSWER
    assert plan.question_targets == [context.candidates[0].application_id]
    assert "본인 역할" in plan.question_focus[context.candidates[0].application_id]
    assert plan.targets == []


async def test_checked_question_target_preserves_its_identity_with_a_same_name_candidate(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="체크한 지원자의 질문을 만들어줘",
        checked=["정유민"],
        extra_rows=[extra_row("정유민")],
        stage_type=StageType.INTERVIEW,
    )
    llm = FakeLlm(
        ToolCall("resolve_candidates", {"names": [], "source": "checked", "candidates": ["C1"]}),
        reply("questions", candidates=["C1"]),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.ANSWER
    assert plan.question_targets == context.checked
    assert plan.question_targets != [context.candidates[-1].application_id]
    assert plan.items == [] and plan.question_focus == {}
    assert len(llm.calls) == 2


async def test_graph_records_only_the_validated_plan(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="선택 비워줘")
    graph = build_root_graph(FakeLlm(reply("edit", action="CLEAR")))

    state = await graph.ainvoke({}, context=context)

    assert state["plan"] is None
    assert state["kind"] == ""
    assert state["mode"] is None
    assert state["turns"][-1]["plan"]["edit"] == "CLEAR"
    saved = str(state)
    assert "documents" not in saved and "tool_calls" not in saved and "searches" not in saved


async def test_stream_finishes_after_verified_items(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="경험 확인해줘")
    final = root_reply(
        {
            "message": "본인 역할은 확인이 필요해요.",
            "command": {"kind": "answer", "candidates": ["C1"]},
            "items": [
                {"candidate": "C1", "label": "확인할 점", "text": "본인 역할은 확인이 필요해요.", "status": "CHECK"}
            ],
        },
    )

    events = [event async for event in stream_plan(FakeLlm(final), context)]

    assert events[0] == ("status", ChatStatus(text=CHECKING))
    assert [name for name, _ in events].count("done") == 1
    assert events[-1][0] == "done"
    item = next(data for name, data in events if name == "item")
    assert isinstance(item, ChatItem) and item.status == "CHECK"
    completed = events[-1][1]
    assert isinstance(completed, ChatPlan)
    assert completed.items == [item]


async def test_graph_records_streamed_steps_and_seconds(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="선택 비워줘")
    graph = build_root_graph(FakeLlm(reply("edit", action="CLEAR")))

    statuses: list[str] = []
    state: dict[str, Any] = {}
    async for streamed in graph.astream({}, context=context, stream_mode=["custom", "values"]):
        mode, chunk = cast(tuple[str, Any], streamed)
        if mode == "custom" and chunk[0] == "status":
            statuses.append(chunk[1].text)
        elif mode == "values":
            state = chunk

    turn = state["turns"][-1]
    assert turn["steps"][0] == CHECKING
    assert turn["steps"] == [text for index, text in enumerate(statuses) if index == 0 or statuses[index - 1] != text]
    assert turn["seconds"] >= 0
    assert state["steps"] == []


async def test_blocked_turn_keeps_only_the_check_step(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="남자만 찾아줘")

    state = await build_root_graph(FakeLlm()).ainvoke({}, context=context)

    assert state["turns"][-1]["steps"] == [CHECKING]


async def test_stream_blocked_has_one_status_and_done(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="남자만 찾아줘")

    events = [event async for event in stream_plan(FakeLlm(), context)]

    assert [name for name, _ in events] == ["status", "done"]


def test_prompt_contains_full_screen_and_no_document_bodies(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="이전 대화 이어서",
        checked=["김하늘"],
        mentions=["정유민"],
        selected=["박서준"],
        extra_rows=[extra_row(f"지원자{index}") for index in range(60)],
    )

    prompt = root_prompt(context, [], [], [])

    assert '"번호": "C68"' in prompt
    assert '"멘션한 지원자": ["C1"]' in prompt
    assert '"체크한 지원자": ["C2"]' in prompt
    assert '"선택 지원자": ["C3"]' in prompt
    assert '"이전 결과": []' in prompt
    assert sample_applicants["정유민"].documents[0].text not in prompt


@pytest.mark.parametrize("candidates", [["C999"], ["C1", "C999"]])
async def test_bulk_read_rejects_the_entire_out_of_scope_batch(
    candidates: list[str], sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="자료 읽어줘")
    llm = FakeLlm(ToolCall("get_candidate_briefs", {"candidates": candidates}), reply("clarify"))

    await run_plan(llm, context)

    assert OUT_OF_SCOPE in llm.calls[-1].user
    assert sample_applicants["정유민"].documents[0].text not in llm.calls[-1].user
