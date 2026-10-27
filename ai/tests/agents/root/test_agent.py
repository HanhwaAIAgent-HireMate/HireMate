import json
from typing import Any
from uuid import uuid4

import httpx
import pytest
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from root_context import make_context

from hiremate_ai.agents.root.agent import run_agent
from hiremate_ai.agents.root.commands import EditCommand, RootReply
from hiremate_ai.agents.root.find import RecheckItem, RecheckResult
from hiremate_ai.agents.root.graph import run_plan
from hiremate_ai.agents.root.toolkit import default_toolkit
from hiremate_ai.agents.root.types import Decision, EditAction, Intent
from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType
from hiremate_ai.llm.call_log import CallRecord
from hiremate_ai.llm.chat import ChatLlm
from hiremate_ai.llm.fake import FakeLlm, ToolCall

type Applicants = dict[str, ApplicantDetail]


async def test_portfolio_questions_can_handoff_after_identity_lookup_without_document_analysis(
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "llm_agent_max_calls", 2)
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="@한예린 포트폴리오에서 질문 여러개 생성해봐",
        mentions=["한예린"],
        stage_type=StageType.INTERVIEW,
        previous_types=[StageType.DOCUMENT],
    )
    target = next(row for row in context.candidates if row.name == "한예린")
    candidate = f"C{context.candidates.index(target) + 1}"
    llm = FakeLlm(
        ToolCall("resolve_candidates", {"names": [], "source": "mentions"}),
        ToolCall(
            "RootReply",
            {
                "kind": "questions",
                "message": "포트폴리오를 바탕으로 질문을 만들게요.",
                "candidates": [candidate],
                "items": [],
                "focus": {},
                "action": None,
                "result": None,
            },
        ),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.ANSWER
    assert plan.question_targets == [target.application_id]
    assert plan.question_focus == {} and plan.items == []
    assert len(llm.calls) == 2


@pytest.mark.parametrize("kind", ["clarify", "questions", "find"])
async def test_missing_named_question_targets_are_clarified_without_substitution(
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    monkeypatch.setattr(settings, "llm_agent_max_calls", 2)
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="@김도현 @이서윤 각각의 제출 서류에 맞는 질문 3개씩 만들어줘.",
        checked=["정유민"],
        selected=["김하늘"],
        stage_type=StageType.INTERVIEW,
    )
    llm = FakeLlm(
        ToolCall("resolve_candidates", {"names": ["김도현", "이서윤"]}),
        ToolCall(
            "RootReply",
            {
                "kind": kind,
                "message": "확인할게요.",
                "candidates": ["C1", "C2"] if kind == "questions" else [],
                "result": "S1" if kind == "find" else None,
            },
        ),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.CLARIFY
    assert "김도현" in plan.message and "이서윤" in plan.message
    assert "찾을 수 없" in plan.message
    assert not plan.question_targets and not plan.targets and plan.edit is None
    assert plan.items == []
    assert len(llm.calls) == 2


async def test_mixed_present_and_missing_names_do_not_generate_a_partial_question_request(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="정유민과 김도현의 질문을 각각 만들어줘",
        stage_type=StageType.INTERVIEW,
    )
    llm = FakeLlm(
        ToolCall("resolve_candidates", {"names": ["정유민", "김도현"]}),
        ToolCall("RootReply", {"kind": "questions", "message": "정유민 질문을 만들게요.", "candidates": ["C1"]}),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.CLARIFY and "김도현" in plan.message
    assert not plan.question_targets and not plan.targets


async def test_unique_named_targets_can_handoff_questions_without_document_reads(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="정유민과 김하늘의 제출 서류에 맞는 질문 3개씩 만들어줘",
        stage_type=StageType.INTERVIEW,
    )
    llm = FakeLlm(
        ToolCall("resolve_candidates", {"names": ["정유민", "김하늘"]}),
        ToolCall("RootReply", {"kind": "questions", "message": "질문을 만들게요.", "candidates": ["C1", "C2"]}),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.ANSWER
    assert plan.question_targets == [context.candidates[0].application_id, context.candidates[1].application_id]
    assert plan.question_focus == {} and plan.items == []
    assert len(llm.calls) == 2


async def test_missing_mention_id_is_clarified_before_any_model_call(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="이 지원자 질문 만들어줘")
    context = context.model_copy(update={"mentions": [uuid4()]})
    llm = FakeLlm()

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.CLARIFY
    assert "멘션" in plan.message and "찾을 수 없" in plan.message
    assert not plan.question_targets and not plan.targets
    assert llm.calls == []


async def test_plain_text_question_targets_require_name_resolution_before_handoff(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="@김도현 @이서윤 각각 질문 3개씩 만들어줘",
        checked=["정유민", "김하늘"],
        stage_type=StageType.INTERVIEW,
    )
    wrong = ToolCall("RootReply", {"kind": "questions", "message": "질문을 만들게요.", "candidates": ["C1", "C2"]})
    llm = FakeLlm(wrong, ToolCall("resolve_candidates", {"names": ["김도현", "이서윤"]}), wrong)

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.CLARIFY
    assert "김도현" in plan.message and "이서윤" in plan.message
    assert not plan.question_targets
    assert len(llm.calls) == 3
    assert "resolve_candidates" in llm.calls[1].user


async def test_duplicate_named_targets_are_not_resolved_to_the_first_match(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="정유민 질문 만들어줘",
        stage_type=StageType.INTERVIEW,
    )
    duplicate = context.candidates[0].model_copy(update={"application_id": uuid4()})
    context = context.model_copy(update={"candidates": [*context.candidates, duplicate]})
    llm = FakeLlm(
        ToolCall("resolve_candidates", {"names": ["정유민"]}),
        ToolCall("RootReply", {"kind": "questions", "message": "질문을 만들게요.", "candidates": ["C1"]}),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.CLARIFY
    assert "정유민" in plan.message and "동명이인" in plan.message
    assert not plan.question_targets


async def test_missing_name_lookup_keeps_its_recovery_message_when_the_model_budget_ends(
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "llm_agent_max_calls", 1)
    context = make_context(sample_applicants, sample_company, sample_posting, message="김도현 질문 만들어줘")
    llm = FakeLlm(ToolCall("resolve_candidates", {"names": ["김도현"]}))

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.CLARIFY
    assert "김도현" in plan.message and "찾을 수 없" in plan.message
    assert not plan.question_targets
    assert len(llm.calls) == 1


async def test_scoped_question_lookup_cannot_substitute_a_different_screen_source(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="체크한 사람 질문 만들어줘",
        checked=["정유민"],
        selected=["김하늘"],
        stage_type=StageType.INTERVIEW,
    )
    llm = FakeLlm(
        ToolCall("resolve_candidates", {"names": [], "source": "checked", "candidates": ["C2"]}),
        ToolCall("RootReply", {"kind": "questions", "message": "질문을 만들게요.", "candidates": ["C2"]}),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.CLARIFY
    assert "범위" in plan.message
    assert not plan.question_targets and not plan.targets


@pytest.mark.parametrize("source", ["subject", "result"])
@pytest.mark.parametrize("explicit_subset", [False, True])
async def test_question_context_with_a_missing_applicant_requires_an_explicit_valid_subset(
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    source: str,
    explicit_subset: bool,
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="그중 첫 번째 사람 질문 만들어줘" if explicit_subset else "그 두 사람 각각 질문 만들어줘",
        stage_type=StageType.INTERVIEW,
    )
    prior = [str(context.candidates[0].application_id), str(uuid4())]
    args: dict[str, Any] = {"names": [], "source": source}
    if explicit_subset:
        args["candidates"] = ["C1"]
    llm = FakeLlm(
        ToolCall("resolve_candidates", args),
        ToolCall("RootReply", {"kind": "questions", "message": "질문을 만들게요.", "candidates": ["C1"]}),
    )

    finished = await run_agent(
        llm,
        context,
        default_toolkit(),
        result=prior if source == "result" else None,
        subject=prior if source == "subject" else [],
    )

    plan = finished.plan
    if explicit_subset:
        assert plan.intent is Intent.ANSWER
        assert plan.question_targets == [context.candidates[0].application_id]
    else:
        assert plan.intent is Intent.CLARIFY
        assert "범위" in plan.message
        assert not plan.question_targets and not plan.targets


async def test_model_receives_required_search_conditions_and_answer_evidence(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    requests: list[dict[str, Any]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "chat-schema-test",
                "object": "chat.completion",
                "created": 0,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "final",
                                    "type": "function",
                                    "function": {
                                        "name": "RootReply",
                                        "arguments": json.dumps(
                                            {
                                                "kind": "clarify",
                                                "message": "어떤 지원자를 말씀하시나요?",
                                                "items": [],
                                                "candidates": [],
                                                "action": None,
                                                "result": None,
                                                "focus": {},
                                            }
                                        ),
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
            },
        )

    class Log:
        async def record(self, record: CallRecord) -> None:
            pass

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        model = ChatOpenAI(
            model="test-model", api_key=SecretStr("test"), base_url="http://llm.test/v1", http_async_client=http
        )
        llm = ChatLlm(model, Log(), model_name="test-model", method="json_schema", agent_max_calls=8)
        context = make_context(sample_applicants, sample_company, sample_posting, message="이 사람 어때?")
        plan = await run_plan(llm, context)

    assert plan.intent is Intent.CLARIFY
    schemas = {tool["function"]["name"]: tool["function"]["parameters"] for tool in requests[0]["tools"]}
    query = schemas["search_candidates"]["properties"]["query"]
    assert {"concepts", "min_score"} <= set(query.get("required", []))
    reply = schemas["RootReply"]
    assert {"kind", "message", "items", "candidates", "action", "result", "focus"} == set(reply["required"])
    assert "command" not in reply["properties"]
    item = reply["properties"]["items"]["items"]
    assert {"candidate", "evidence"} <= set(item["required"])


def test_flat_model_response_preserves_the_explicit_selection_command() -> None:
    reply = RootReply.model_validate(
        {
            "kind": "edit",
            "message": "선택에 넣을게.",
            "candidates": ["C3", "C4"],
            "action": "ADD",
            "items": [],
            "result": None,
            "focus": {},
        }
    )

    assert isinstance(reply.command, EditCommand)
    assert reply.command.action is EditAction.ADD
    assert reply.command.candidates == ["C3", "C4"]


@pytest.mark.parametrize("kind,extra", [("conversation", {"candidates": ["C1"]}), ("edit", {"result": "S1"})])
def test_flat_model_response_rejects_unused_command_fields(kind: str, extra: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="사용하지 않는"):
        RootReply.model_validate(
            {
                "kind": kind,
                "message": "처리할게.",
                "items": [],
                "candidates": [],
                "action": None,
                "result": None,
                "focus": {},
                **extra,
            }
        )


async def test_root_chooses_a_read_tool_and_returns_a_command_without_classification(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="현재 인원 알려줘")
    llm = FakeLlm(
        ToolCall("get_stage_summary"),
        ToolCall(
            "RootReply",
            {
                "message": "현재 지원자는 8명이에요.",
                "command": {"kind": "answer"},
                "items": [
                    {
                        "candidate": None,
                        "label": "인원",
                        "text": "현재 지원자 8명",
                        "status": "OK",
                        "evidence": [{"sentence": "지원자 8명", "source": "전형 결과"}],
                    }
                ],
            },
        ),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.ANSWER
    assert plan.message == "현재 지원자는 8명이에요."
    assert len(llm.calls) == 2
    assert all(call.output.__name__ == "RootReply" for call in llm.calls)
    assert "미결정 8명" in llm.calls[-1].user


async def test_search_result_cannot_be_replaced_with_an_answer_after_reading_briefs(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="결제 경험자를 찾아서 경험을 설명해줘"
    )
    sentence = "MySQL 정산 테이블을 파티셔닝해 월말 정산 배치 시간을 40% 줄였습니다."
    llm = FakeLlm(
        ToolCall("search_candidates", {"query": {"concepts": ["결제"]}, "pool": ["C1"]}),
        RecheckResult(results=[RecheckItem(candidate_no=1, met=True, sentence_nos=[1])]),
        ToolCall("get_candidate_briefs", {"candidates": ["C1"]}),
        ToolCall(
            "RootReply",
            {
                "message": "정유민 님의 정산 배치 개선 경험을 확인했어요.",
                "command": {"kind": "answer", "candidates": ["C1"]},
                "items": [
                    {
                        "candidate": "C1",
                        "label": "경험",
                        "text": "정산 배치 시간 40% 단축",
                        "status": "OK",
                        "evidence": [{"sentence": sentence, "source": "이력서"}],
                    }
                ],
            },
        ),
        ToolCall("RootReply", {"message": "검색 결과예요.", "command": {"kind": "find", "result": "S1"}}),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.FIND
    assert plan.targets == [context.candidates[0].application_id]
    assert plan.sources == ["이력서"]
    assert '"result": "S1"' in llm.calls[2].user
    assert sentence in llm.calls[-1].user
    assert [call.output.__name__ for call in llm.calls] == [
        "RootReply",
        "RecheckResult",
        "RootReply",
        "RootReply",
        "RootReply",
    ]


async def test_reading_summary_does_not_allow_an_answer_without_evidence_items(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="인원 알려줘")
    answer = ToolCall("RootReply", {"message": "현재 지원자는 100명이에요.", "command": {"kind": "answer"}})

    plan = await run_plan(FakeLlm(ToolCall("get_stage_summary"), answer, answer), context)

    assert plan.intent is Intent.CLARIFY
    assert "100명" not in plan.message


async def test_empty_search_cannot_be_replaced_with_a_candidate_answer(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="양자 컴퓨팅 경험자 찾아줘")
    llm = FakeLlm(
        ToolCall("search_candidates", {"query": {"concepts": ["양자 컴퓨팅"]}}),
        ToolCall("get_candidate_briefs", {"candidates": ["C1"]}),
        ToolCall(
            "RootReply",
            {
                "message": "정유민 님을 확인해 보세요.",
                "command": {"kind": "answer", "candidates": ["C1"]},
                "items": [{"candidate": "C1", "label": "확인", "text": "추가 확인이 필요해요.", "status": "CHECK"}],
            },
        ),
        ToolCall("RootReply", {"message": "검색 결과예요.", "command": {"kind": "find", "result": "S1"}}),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.ANSWER
    assert plan.items == []
    assert "찾지 못했어요" in plan.message
    assert len(llm.calls) == 4


async def test_empty_stage_answers_must_observe_the_stage_summary(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="인원 알려줘")
    answer = ToolCall("RootReply", {"message": "현재 지원자는 100명이에요.", "command": {"kind": "answer"}})

    plan = await run_plan(FakeLlm(answer, answer), context)

    assert plan.intent is Intent.CLARIFY
    assert "100명" not in plan.message


async def test_unsubstantiated_stage_items_cannot_bypass_summary_validation(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="인원 알려줘")
    answer = ToolCall(
        "RootReply",
        {
            "message": "지원자는 100명이에요.",
            "command": {"kind": "answer"},
            "items": [{"label": "인원", "text": "지원자 100명", "status": "OK"}],
        },
    )

    plan = await run_plan(FakeLlm(answer, answer), context)

    assert plan.intent is Intent.CLARIFY
    assert "100명" not in plan.message


async def test_question_confirmation_does_not_repeat_unverified_model_prose(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="면접 질문 만들어줘", stage_type=StageType.INTERVIEW
    )
    llm = FakeLlm(
        ToolCall("resolve_candidates", {"names": ["정유민"]}),
        ToolCall(
            "RootReply",
            {
                "message": "정유민은 증권사에서 20년 일했으니 질문을 만들어요.",
                "command": {"kind": "questions", "candidates": ["C1"]},
            },
        ),
    )

    plan = await run_plan(llm, context)

    assert plan.question_targets == [context.candidates[0].application_id]
    assert "증권사" not in plan.message
    assert "20년" not in plan.message


async def test_root_returns_the_models_explicit_edit_targets(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="앞에서 이야기한 분을 빼줘",
        checked=["김하늘"],
    )
    llm = FakeLlm(
        ToolCall(
            "RootReply",
            {"message": "선택에서 뺐어요.", "command": {"kind": "edit", "action": "REMOVE", "candidates": ["C1"]}},
        )
    )

    plan = await run_plan(llm, context)

    assert plan.edit is EditAction.REMOVE
    assert plan.targets == [sample_applicants["정유민"].info.application_id]


@pytest.mark.parametrize("decision", [Decision.PASS, Decision.FAIL])
async def test_noop_add_rechecks_decided_previous_subject_before_using_unrelated_selection(
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    decision: Decision,
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="스테이지에 올려줘",
        selected=["박서준", "이도윤"],
    )
    context = context.model_copy(
        update={
            "candidates": [
                row.model_copy(update={"decision": decision}) if index < 2 else row
                for index, row in enumerate(context.candidates)
            ]
        }
    )
    llm = FakeLlm(
        ToolCall(
            "RootReply",
            {"message": "선택에 넣었어요.", "command": {"kind": "edit", "action": "ADD", "candidates": ["C3", "C4"]}},
        ),
        ToolCall(
            "RootReply",
            {"message": "선택에 넣을게요.", "command": {"kind": "edit", "action": "ADD", "candidates": ["C1", "C2"]}},
        ),
    )

    result = await run_agent(
        llm,
        context,
        default_toolkit(),
        subject=[str(row.application_id) for row in context.candidates[:2]],
    )

    assert result.plan.intent is Intent.CLARIFY
    assert result.plan.targets == [] and result.plan.edit is None
    assert "정유민, 김하늘" in result.plan.message
    assert "이미" in result.plan.message
    assert "C1 정유민" in llm.calls[-1].user and "C2 김하늘" in llm.calls[-1].user
    assert "C3 박서준" in llm.calls[-1].user and "C4 이도윤" in llm.calls[-1].user


async def test_current_mentions_allow_an_explicit_idempotent_add_after_a_decided_subject(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="@박서준 다시 선택에 넣어줘",
        mentions=["박서준"],
        selected=["박서준"],
    )
    context = context.model_copy(
        update={
            "candidates": [
                context.candidates[0].model_copy(update={"decision": Decision.PASS}),
                *context.candidates[1:],
            ]
        }
    )
    llm = FakeLlm(
        ToolCall(
            "RootReply",
            {"message": "선택에 넣을게요.", "command": {"kind": "edit", "action": "ADD", "candidates": ["C3"]}},
        )
    )

    result = await run_agent(llm, context, default_toolkit(), subject=[str(context.candidates[0].application_id)])

    assert result.plan.intent is Intent.EDIT
    assert result.plan.targets == [context.candidates[2].application_id]


async def test_search_with_missing_conditions_is_repaired_before_a_result_is_created(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="직무역량 평가 점수 기준으로 80점 이상만 스테이지에 올려줘",
        stage_type=StageType.ASSESSMENT,
    )
    context = context.model_copy(
        update={
            "candidates": [
                row.model_copy(update={"score": score})
                for row, score in zip(context.candidates, [97, 91, 80, 79, 60, 50, 40, None], strict=True)
            ]
        }
    )
    llm = FakeLlm(
        ToolCall("search_candidates", {"query": {"mode": "REPLACE", "score_source": "assessment"}}),
        ToolCall("search_candidates", {"query": {"min_score": 80, "score_source": "assessment"}}),
        ToolCall(
            "RootReply", {"message": "조건에 맞는 지원자를 선택했어요.", "command": {"kind": "find", "result": "S1"}}
        ),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.FIND
    assert plan.targets == [row.application_id for row in context.candidates[:3]]
    assert len(llm.calls) == 3


async def test_search_results_cannot_be_replaced_with_arbitrary_edit_targets(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="서류 80점 이상만 선택해줘")
    context = context.model_copy(update={"document_scores": {context.candidates[0].application_id: 90}})
    llm = FakeLlm(
        ToolCall("search_candidates", {"query": {"min_score": 80, "score_source": "document"}}),
        ToolCall(
            "RootReply", {"message": "선택했어요.", "command": {"kind": "edit", "action": "ADD", "candidates": ["C2"]}}
        ),
        ToolCall("RootReply", {"message": "선택했어요.", "command": {"kind": "find", "result": "S1"}}),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.FIND
    assert plan.targets == [context.candidates[0].application_id]


@pytest.mark.parametrize("query", [{"use_talents": True}, {"posting_criteria": "preferred"}])
async def test_discriminatory_company_or_posting_criteria_are_blocked_before_search(
    query: dict[str, object],
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    from hiremate_ai.agents.guardrails import BLOCKED_REPLY

    company = sample_company.model_copy(
        update={
            "talents": [
                sample_company.talents[0].model_copy(update={"title": "여성 우대", "description": "여성 지원자 선호"})
            ]
        }
    )
    posting = sample_posting.model_copy(update={"preferred": ["여성 지원자 우대"]})
    context = make_context(sample_applicants, company, posting, message="그 기준에 맞는 분을 찾아줘")
    llm = FakeLlm(
        ToolCall("search_candidates", {"query": query}),
        ToolCall("RootReply", {"message": "찾았어요.", "command": {"kind": "find", "result": "S1"}}),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.BLOCKED
    assert plan.message == BLOCKED_REPLY
    assert all(call.output.__name__ == "RootReply" for call in llm.calls)
