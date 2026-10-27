from collections.abc import Sequence
from typing import Literal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from root_context import extra_row, make_context

from hiremate_ai.agents.root.answer import AnswerEvidence, AnswerItem
from hiremate_ai.agents.root.commands import (
    AnswerCommand,
    BlockedCommand,
    ClarifyCommand,
    DecisionCommand,
    EditCommand,
    FindCommand,
    QuestionsCommand,
    RootReply,
    compile_reply,
)
from hiremate_ai.agents.root.toolkit import default_toolkit
from hiremate_ai.agents.root.types import (
    ChatContext,
    ChatPlan,
    ChatStage,
    Decision,
    EditAction,
    Intent,
    SelectionMode,
    StageStatus,
)
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, DocumentType, PostingContent, StageType

type Applicants = dict[str, ApplicantDetail]
BATCH = "MySQL 정산 테이블을 파티셔닝해 월말 정산 배치 시간을 40% 줄였습니다."


@pytest.fixture
def context(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> ChatContext:
    return make_context(sample_applicants, sample_company, sample_posting, message="그 경험을 확인해줘")


def item(*, candidate: str = "C1", sentence: str = BATCH, status: Literal["OK", "CHECK"] = "OK") -> AnswerItem:
    return AnswerItem(
        candidate=candidate,
        label="강점",
        text="정산 배치 시간 단축" if status == "OK" else "본인 역할은 추가 확인이 필요해요.",
        status=status,
        evidence=[AnswerEvidence(sentence=sentence, source="이력서")] if sentence else [],
    )


async def answer(
    context: ChatContext,
    *,
    candidates: Sequence[str] = ("C1",),
    items: Sequence[AnswerItem] | None = None,
    message: str = "정산 배치 개선 경험을 확인했어요.",
) -> ChatPlan:
    return await compile_reply(
        RootReply(
            message=message,
            items=list(items) if items is not None else [item()],
            command=AnswerCommand(candidates=list(candidates)),
        ),
        context,
        default_toolkit(),
        {},
    )


def interview_context(context: ChatContext) -> ChatContext:
    return context.model_copy(
        update={
            "stage_type": StageType.INTERVIEW,
            "stages": [
                stage.model_copy(update={"type": StageType.INTERVIEW}) if stage.id == context.stage_id else stage
                for stage in context.stages
            ],
        }
    )


async def test_final_answer_keeps_only_verified_evidence(context: ChatContext) -> None:
    plan = await answer(context)

    assert plan.intent is Intent.ANSWER
    assert [(entry.application_id, entry.text, entry.status) for entry in plan.items] == [
        (context.candidates[0].application_id, "정산 배치 시간 단축", "OK")
    ]
    assert plan.sources == ["이력서"]
    assert plan.targets == [] and plan.question_targets == []


async def test_empty_candidate_is_normalized_for_a_stage_wide_item(context: ChatContext) -> None:
    raw = AnswerItem(
        candidate="",
        label="기업 소개",
        text="등록된 기업 소개예요.",
        status="OK",
        evidence=[AnswerEvidence(sentence=context.company.intro, source="회사 소개")],
    )

    plan = await answer(context, candidates=[], items=[raw], message="기업 소개를 확인했어요.")

    assert raw.candidate is None
    assert [(entry.application_id, entry.status) for entry in plan.items] == [(None, "OK")]
    assert plan.sources == ["회사 소개"]


@pytest.mark.parametrize("empty", [None, "null"])
async def test_flat_answer_accepts_only_absent_action_and_result(context: ChatContext, empty: str | None) -> None:
    reply = RootReply.model_validate(
        {
            "kind": "answer",
            "message": "경험을 확인했어요.",
            "items": [item().model_dump()],
            "candidates": ["C1"],
            "action": empty,
            "result": empty,
            "focus": {},
        }
    )

    plan = await compile_reply(reply, context, default_toolkit(), {})

    assert isinstance(reply.command, AnswerCommand)
    assert plan.intent is Intent.ANSWER
    assert [entry.application_id for entry in plan.items] == [context.candidates[0].application_id]
    assert plan.targets == []


@pytest.mark.parametrize("extra", [{"action": "CLEAR"}, {"result": "S1"}])
def test_flat_answer_rejects_real_unused_command_values(extra: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="사용하지 않는"):
        RootReply.model_validate({"kind": "answer", "message": "정리했어요.", "action": None, "result": None, **extra})


async def test_stage_count_quote_is_verified_without_a_candidate(context: ChatContext) -> None:
    aggregate = AnswerItem(
        candidate=None,
        label="결정 현황",
        text="현재 전형은 미결정 8명이에요.",
        status="OK",
        evidence=[
            AnswerEvidence(sentence="서류 전형 (서류) 지원자 8명: 미결정 8명, 합격 0명, 불합격 0명", source="전형 결과")
        ],
    )

    plan = await answer(context, candidates=[], items=[aggregate], message="현재 결정 현황이에요.")

    assert [(entry.application_id, entry.status) for entry in plan.items] == [(None, "OK")]
    assert plan.sources == ["전형 결과"]


async def test_stage_order_can_be_verified_from_the_current_stage_configuration(context: ChatContext) -> None:
    context = context.model_copy(
        update={
            "stages": [
                *context.stages,
                ChatStage(id=uuid4(), name="과제 평가", type=StageType.ASSESSMENT, status=StageStatus.PENDING),
                ChatStage(id=uuid4(), name="1차 면접", type=StageType.INTERVIEW, status=StageStatus.PENDING),
            ]
        }
    )
    stages = AnswerItem(
        candidate=None,
        label="전형 순서",
        text="현재 서류 전형 다음은 과제 평가이며, 세 번째가 1차 면접이에요.",
        status="OK",
        evidence=[
            AnswerEvidence(sentence="2. 과제 평가", source="전형 결과"),
            AnswerEvidence(sentence="3. 1차 면접", source="전형 결과"),
        ],
    )

    plan = await answer(context, candidates=[], items=[stages], message="등록된 전형 순서예요.")

    assert [(entry.application_id, entry.status) for entry in plan.items] == [(None, "OK")]
    assert plan.sources == ["전형 결과"]


async def test_selected_roster_uses_each_candidates_verified_selection_state(context: ChatContext) -> None:
    context = context.model_copy(
        update={
            "candidates": [
                row.model_copy(update={"selected": index < 2}) for index, row in enumerate(context.candidates)
            ]
        }
    )
    selected = [
        AnswerItem(
            candidate=f"C{index}",
            label="선택 여부",
            text=f"{name}이 선택되어 있어요.",
            status="OK",
            evidence=[AnswerEvidence(sentence="선택 여부: 선택됨", source="전형 결과")],
        )
        for index, name in [(1, "정유민"), (2, "김하늘")]
    ]

    plan = await answer(
        context, candidates=["C1", "C2"], items=selected, message="선택 지원자는 정유민과 김하늘이에요."
    )

    assert [(entry.application_id, entry.status) for entry in plan.items] == [
        (row.application_id, "OK") for row in context.candidates[:2]
    ]
    assert plan.sources == ["전형 결과"]
    assert "정유민" in plan.message and "김하늘" in plan.message


async def test_candidate_can_quote_its_own_compressed_stage_summary_row(context: ChatContext) -> None:
    context = context.model_copy(
        update={
            "candidates": [
                context.candidates[0].model_copy(update={"selected": True, "career_years": 12}),
                *context.candidates[1:],
            ]
        }
    )
    selected = AnswerItem(
        candidate="C1",
        label="선택 및 등록 경력",
        text="정유민은 선택된 지원자로, 등록 경력은 12년이에요.",
        status="OK",
        evidence=[AnswerEvidence(sentence="C1 정유민, 미결정, 경력 12년, 선택 여부: 선택됨", source="전형 결과")],
    )

    plan = await answer(context, items=[selected], message="선택 상태와 등록 경력을 확인했어요.")

    assert [(entry.application_id, entry.status) for entry in plan.items] == [
        (context.candidates[0].application_id, "OK")
    ]
    assert plan.sources == ["전형 결과"]


async def test_candidate_cannot_quote_another_candidates_stage_summary_row(context: ChatContext) -> None:
    context = context.model_copy(
        update={
            "candidates": [
                context.candidates[0].model_copy(update={"selected": True, "career_years": 12}),
                context.candidates[1].model_copy(update={"selected": True, "career_years": 12}),
                *context.candidates[2:],
            ]
        }
    )
    selected = AnswerItem(
        candidate="C1",
        label="선택 및 등록 경력",
        text="정유민의 등록 경력은 12년이에요.",
        status="OK",
        evidence=[AnswerEvidence(sentence="C2 김하늘, 미결정, 경력 12년, 선택 여부: 선택됨", source="전형 결과")],
    )

    with pytest.raises(ValueError, match="근거"):
        await answer(context, items=[selected], message="등록 경력을 확인했어요.")


async def test_stage_wide_roster_cannot_replace_candidate_linked_items(context: ChatContext) -> None:
    context = context.model_copy(
        update={
            "candidates": [
                row.model_copy(update={"selected": index < 2}) for index, row in enumerate(context.candidates)
            ]
        }
    )
    selected = AnswerItem(
        candidate=None,
        label="선택 명단",
        text="정유민과 김하늘이 선택되어 있어요.",
        status="OK",
        evidence=[AnswerEvidence(sentence="선택 지원자 2명: C1 정유민, C2 김하늘", source="전형 결과")],
    )

    with pytest.raises(ValueError, match="지원자"):
        await answer(context, candidates=[], items=[selected], message="선택 명단이에요.")


@pytest.mark.parametrize(
    "sentence,text",
    [
        ("선택 지원자 2명: C1 정유민, C3 박서준", "정유민과 박서준이 선택되어 있어요."),
        ("선택 지원자 2명: C1 정유민, C2 김하늘", "정유민과 박서준이 선택되어 있어요."),
    ],
)
async def test_stage_roster_rejects_forged_quotes_or_unquoted_candidates(
    context: ChatContext, sentence: str, text: str
) -> None:
    context = context.model_copy(
        update={
            "candidates": [
                row.model_copy(update={"selected": index < 2}) for index, row in enumerate(context.candidates)
            ]
        }
    )
    selected = AnswerItem(
        candidate=None,
        label="선택 명단",
        text=text,
        status="OK",
        evidence=[AnswerEvidence(sentence=sentence, source="전형 결과")],
    )

    with pytest.raises(ValueError, match="근거|지원자"):
        await answer(context, candidates=[], items=[selected], message="선택 명단이에요.")


@pytest.mark.parametrize(
    "sentence",
    [
        "여성 고객을 위한 결제 서비스에서 트랜잭션 시스템을 설계했습니다.",
        "Redis 캐시 키가 충돌하는 문제를 해결했습니다.",
    ],
)
async def test_quoted_technical_evidence_is_not_treated_as_a_selection_condition(
    context: ChatContext, sentence: str
) -> None:
    application_id = context.candidates[0].application_id
    original = context.documents[application_id][0]
    context = context.model_copy(
        update={"documents": {application_id: [original.model_copy(update={"text": sentence})]}}
    )

    plan = await answer(
        context,
        items=[item(sentence=sentence).model_copy(update={"text": "기술 경험을 확인했어요."})],
        message="기술 경험을 확인했어요.",
    )

    assert plan.intent is Intent.ANSWER
    assert plan.items[0].status == "OK"
    assert plan.sources == ["이력서"]


async def test_target_is_not_overridden_by_count_words_or_checked_state(context: ChatContext) -> None:
    context = context.model_copy(
        update={"message": "그 사람 현황 알려줘", "checked": [context.candidates[1].application_id]}
    )

    plan = await answer(context)

    assert [entry.application_id for entry in plan.items] == [context.candidates[0].application_id]


async def test_stage_answer_does_not_inherit_checked_targets(context: ChatContext) -> None:
    context = context.model_copy(update={"checked": [row.application_id for row in context.candidates[:2]]})

    plan = await answer(context, candidates=[], items=[], message="미결정은 8명이에요.")

    assert plan.message == "미결정은 8명이에요."
    assert plan.items == []


@pytest.mark.parametrize("candidates", [["C42"], ["C1", "C1"], ["C1", "1"]])
async def test_unknown_or_duplicate_candidate_is_rejected(context: ChatContext, candidates: list[str]) -> None:
    with pytest.raises(ValueError, match="지원자"):
        await answer(context, candidates=candidates)


@pytest.mark.parametrize("items", [[], [item(candidate="C2")], [item(candidate="C42")]])
async def test_target_requires_an_item_for_every_candidate(context: ChatContext, items: list[AnswerItem]) -> None:
    with pytest.raises(ValueError, match="지원자|항목"):
        await answer(context, items=items)


@pytest.mark.parametrize("sentence", ["", "10년 동안 증권사 시스템을 설계했습니다."])
async def test_unsupported_ok_is_rejected_instead_of_relabeling_the_claim(context: ChatContext, sentence: str) -> None:
    with pytest.raises(ValueError, match="근거"):
        await answer(context, items=[item(sentence=sentence)])


async def test_honest_check_needs_no_invented_evidence(context: ChatContext) -> None:
    plan = await answer(context, items=[item(sentence="", status="CHECK")])

    assert plan.items[0].status == "CHECK"
    assert plan.sources == []


@pytest.mark.parametrize(
    "message", ["정리했어요. (C1)}},", "상세 근거는 items를 참고하세요.", "<think>요약을 작성하자</think>", ""]
)
async def test_malformed_message_is_rejected(context: ChatContext, message: str) -> None:
    with pytest.raises(ValueError, match="문장|본문"):
        await answer(context, message=message)


async def test_technical_method_name_is_not_an_internal_field_leak(context: ChatContext) -> None:
    plan = await answer(context, message="dict.items() 사용 경험은 추가 확인이 필요해요.")

    assert plan.message == "dict.items() 사용 경험은 추가 확인이 필요해요."


async def test_later_stage_absence_is_not_a_shortfall(context: ChatContext) -> None:
    with pytest.raises(ValueError, match="전형"):
        await answer(context, message="면접 기록이 없어 확인이 필요해요.")
    with pytest.raises(ValueError, match="전형"):
        await answer(
            context,
            items=[AnswerItem(candidate="C1", label="확인", text="면접 기록이 없어 확인이 필요해요.", status="CHECK")],
        )


async def test_search_uses_the_recorded_plan_including_its_message(context: ChatContext) -> None:
    found = ChatPlan.answer(Intent.ANSWER, "조건에 맞는 지원자를 찾지 못했어요.")

    plan = await compile_reply(
        RootReply(message="모델이 새로 쓴 답", command=FindCommand(result="search-1")),
        context,
        default_toolkit(),
        {"search-1": found},
    )

    assert plan is found


async def test_unknown_search_result_is_rejected(context: ChatContext) -> None:
    with pytest.raises(ValueError, match="검색"):
        await compile_reply(
            RootReply(message="찾았어요.", command=FindCommand(result="search-42")), context, default_toolkit(), {}
        )


async def test_search_cannot_reference_a_candidate_outside_the_stage(context: ChatContext) -> None:
    found = ChatPlan.answer(Intent.FIND, "선택했어요.").model_copy(
        update={"mode": SelectionMode.REPLACE, "targets": [uuid4()]}
    )

    with pytest.raises(ValueError, match="전형 밖"):
        await compile_reply(
            RootReply(message="찾았어요.", command=FindCommand(result="search-1")),
            context,
            default_toolkit(),
            {"search-1": found},
        )


@pytest.mark.parametrize("action", list(EditAction))
async def test_locked_stage_rejects_edit_commands(context: ChatContext, action: EditAction) -> None:
    context = context.model_copy(update={"selectable": False})
    refs = [] if action in (EditAction.CLEAR, EditAction.RESTORE) else ["C1"]

    with pytest.raises(ValueError, match="확정|선택"):
        await compile_reply(
            RootReply(message="선택을 바꿨어요.", command=EditCommand(action=action, candidates=refs)),
            context,
            default_toolkit(),
            {},
        )


async def test_locked_stage_rejects_recorded_selection_change(context: ChatContext) -> None:
    context = context.model_copy(update={"selectable": False})
    found = ChatPlan.answer(Intent.FIND, "선택했어요.").model_copy(
        update={"mode": SelectionMode.REPLACE, "targets": [context.candidates[0].application_id]}
    )

    with pytest.raises(ValueError, match="확정|선택"):
        await compile_reply(
            RootReply(message="찾았어요.", command=FindCommand(result="search-1")),
            context,
            default_toolkit(),
            {"search-1": found},
        )


async def test_locked_stage_still_allows_readonly_search_answers(context: ChatContext) -> None:
    context = context.model_copy(update={"selectable": False})
    found = ChatPlan.answer(Intent.ANSWER, "합격한 지원자 중 1명이 조건에 맞아요.")

    plan = await compile_reply(
        RootReply(message="찾았어요.", command=FindCommand(result="search-1")),
        context,
        default_toolkit(),
        {"search-1": found},
    )

    assert plan is found


@pytest.mark.parametrize("action", [EditAction.CLEAR, EditAction.RESTORE])
async def test_clear_and_restore_reject_candidate_targets(context: ChatContext, action: EditAction) -> None:
    with pytest.raises(ValueError, match="대상"):
        await compile_reply(
            RootReply(message="선택을 바꿨어요.", command=EditCommand(action=action, candidates=["C1"])),
            context,
            default_toolkit(),
            {},
        )


async def test_edit_does_not_fall_back_to_mentions_or_checked(context: ChatContext) -> None:
    context = context.model_copy(
        update={"mentions": [context.candidates[0].application_id], "checked": [context.candidates[1].application_id]}
    )

    with pytest.raises(ValueError, match="대상"):
        await compile_reply(
            RootReply(message="뺐어요.", command=EditCommand(action=EditAction.REMOVE)), context, default_toolkit(), {}
        )


async def test_edit_keeps_eligible_targets_only(context: ChatContext) -> None:
    context = context.model_copy(
        update={
            "candidates": [
                context.candidates[0],
                context.candidates[1].model_copy(update={"decision": Decision.PASS}),
                *context.candidates[2:],
            ]
        }
    )

    plan = await compile_reply(
        RootReply(message="넣었어요.", command=EditCommand(action=EditAction.ADD, candidates=["C1", "C2"])),
        context,
        default_toolkit(),
        {},
    )

    assert plan.targets == [context.candidates[0].application_id]
    assert "이미 합격" in plan.message


async def test_questions_keep_explicit_targets_and_original_request(context: ChatContext) -> None:
    context = interview_context(context).model_copy(update={"message": "그 질문을 기술적으로 다시 만들어줘"})
    focus = item().text

    plan = await compile_reply(
        RootReply(
            message="질문을 만들어요.", items=[item()], command=QuestionsCommand(candidates=["C1"], focus={"C1": focus})
        ),
        context,
        default_toolkit(),
        {},
    )

    assert plan.intent is Intent.ANSWER
    assert plan.question_targets == [context.candidates[0].application_id]
    assert focus in plan.question_focus[context.candidates[0].application_id]
    assert context.message in plan.question_focus[context.candidates[0].application_id]
    assert plan.sources == ["이력서"] and plan.agents == ["Interview Agent"]


async def test_generic_questions_do_not_invent_reasons(context: ChatContext) -> None:
    context = interview_context(context)

    plan = await compile_reply(
        RootReply(message="제출 서류를 기준으로 질문을 만들어요.", command=QuestionsCommand(candidates=["C1", "C2"])),
        context,
        default_toolkit(),
        {},
    )

    assert plan.question_targets == [row.application_id for row in context.candidates[:2]]
    assert plan.question_focus == {} and plan.items == []


@pytest.mark.parametrize("candidates,focus", [([], {}), (["C42"], {}), (["C1"], {"C2": "설계 확인"})])
async def test_questions_require_current_targets_and_focus_subset(
    context: ChatContext, candidates: list[str], focus: dict[str, str]
) -> None:
    with pytest.raises(ValueError, match="지원자|대상"):
        await compile_reply(
            RootReply(message="질문을 만들어요.", command=QuestionsCommand(candidates=candidates, focus=focus)),
            interview_context(context),
            default_toolkit(),
            {},
        )


async def test_questions_require_an_interview_stage(context: ChatContext) -> None:
    with pytest.raises(ValueError, match="면접"):
        await compile_reply(
            RootReply(message="질문을 만들어요.", command=QuestionsCommand(candidates=["C1"])),
            context,
            default_toolkit(),
            {},
        )


async def test_questions_refuse_more_than_twenty_targets(context: ChatContext) -> None:
    rows = [extra_row(f"지원자{number}") for number in range(21)]
    context = interview_context(context).model_copy(update={"candidates": rows})

    with pytest.raises(ValueError, match="20명"):
        await compile_reply(
            RootReply(
                message="질문을 만들어요.",
                command=QuestionsCommand(candidates=[f"C{number}" for number in range(1, 22)]),
            ),
            context,
            default_toolkit(),
            {},
        )


async def test_discriminatory_followup_focus_is_blocked(context: ChatContext) -> None:
    plan = await compile_reply(
        RootReply(message="확인할게요.", command=QuestionsCommand(candidates=["C1"], focus={"C1": "나이로 거르기"})),
        interview_context(context),
        default_toolkit(),
        {},
    )

    assert plan.intent is Intent.BLOCKED
    assert plan.question_targets == []


async def test_blocked_command_uses_the_fixed_reply(context: ChatContext) -> None:
    plan = await compile_reply(
        RootReply(message="모델이 작성한 문장", command=BlockedCommand()), context, default_toolkit(), {}
    )

    assert plan.intent is Intent.BLOCKED
    assert "모델이 작성한" not in plan.message


async def test_decision_only_instructs_the_user_to_use_the_screen(context: ChatContext) -> None:
    plan = await compile_reply(
        RootReply(message="합격 처리했어요.", command=DecisionCommand()), context, default_toolkit(), {}
    )

    assert plan.intent is Intent.CLARIFY
    assert "화면" in plan.message
    assert plan.targets == [] and plan.question_targets == []


async def test_clarify_cannot_smuggle_unverified_items(context: ChatContext) -> None:
    with pytest.raises(ValueError, match="되묻기"):
        await compile_reply(
            RootReply(message="누구를 말씀하세요?", items=[item()], command=ClarifyCommand()),
            context,
            default_toolkit(),
            {},
        )


def test_command_schema_forbids_unrelated_action_parameters() -> None:
    with pytest.raises(ValidationError):
        RootReply.model_validate(
            {"message": "정리했어요.", "command": {"kind": "answer", "action": "REMOVE", "candidates": ["C1"]}}
        )


async def test_candidate_claim_cannot_bypass_validation_by_omitting_candidates(context: ChatContext) -> None:
    with pytest.raises(ValueError, match="지원자|항목"):
        await answer(context, candidates=[], items=[], message="정유민은 증권사에서 20년 일한 전문가입니다.")


@pytest.mark.parametrize("mention", ["C2", "김하늘"])
@pytest.mark.parametrize("candidates", [[], ["C1", "C3"]])
async def test_message_feedback_identifies_an_unsupported_negative_candidate_claim(
    context: ChatContext, mention: str, candidates: list[str]
) -> None:
    sentence = "PWA 프로젝트에서 오프라인 동작을 구현했습니다."
    documents = dict(context.documents)
    items = []
    for ref, row in [("C1", context.candidates[0]), ("C3", context.candidates[2])]:
        document = documents[row.application_id][0]
        documents[row.application_id] = [document.model_copy(update={"type": DocumentType.PORTFOLIO, "text": sentence})]
        items.append(
            AnswerItem(
                candidate=ref,
                label="포트폴리오",
                text="PWA 프로젝트 경험을 확인했어요.",
                status="OK",
                evidence=[AnswerEvidence(sentence=sentence, source="포트폴리오")],
            )
        )
    context = context.model_copy(update={"documents": documents})

    with pytest.raises(ValueError) as invalid:
        await answer(
            context,
            candidates=candidates,
            items=items,
            message=f"C1과 C3에게 PWA 프로젝트가 있어요. {mention}에게는 PWA 포트폴리오가 없어요.",
        )

    feedback = str(invalid.value)
    assert "지원자 C2의" in feedback
    assert "C1" not in feedback and "C3" not in feedback
    assert "candidates에 번호만 추가해도 해결되지 않아요" in feedback
    assert "근거를 확인한 items를 작성하거나" in feedback
    assert "언급을 삭제하세요" in feedback
    assert "확인하지 못한 내용을 없다고 단정하지 마세요" in feedback

    repaired = await answer(context, candidates=["C1", "C3"], items=items, message="C1과 C3의 경험을 확인했어요.")

    assert [entry.application_id for entry in repaired.items] == [
        context.candidates[0].application_id,
        context.candidates[2].application_id,
    ]
    assert all(entry.status == "OK" for entry in repaired.items)


async def test_question_focus_cannot_add_an_unverified_fact(context: ChatContext) -> None:
    with pytest.raises(ValueError, match="확인할 점|항목"):
        await compile_reply(
            RootReply(
                message="질문을 만들어요.",
                items=[item()],
                command=QuestionsCommand(candidates=["C1"], focus={"C1": "증권사에서 20년 일한 설계 판단"}),
            ),
            interview_context(context),
            default_toolkit(),
            {},
        )


async def test_focus_refers_to_the_original_item_before_display_formatting(context: ChatContext) -> None:
    raw = item().model_copy(update={"text": "C1의 파티셔닝 경험"})

    plan = await compile_reply(
        RootReply(
            message="질문을 만들어요.",
            items=[raw],
            command=QuestionsCommand(candidates=["C1"], focus={"C1": raw.text}),
        ),
        interview_context(context),
        default_toolkit(),
        {},
    )

    assert "정유민의 파티셔닝 경험" in plan.question_focus[context.candidates[0].application_id]
    assert "C1" not in plan.question_focus[context.candidates[0].application_id]


@pytest.mark.parametrize("text", ["C42의 파티셔닝 경험", "김하늘의 파티셔닝 경험"])
async def test_item_cannot_attach_one_candidates_evidence_to_another(context: ChatContext, text: str) -> None:
    with pytest.raises(ValueError, match="지원자"):
        await answer(context, items=[item().model_copy(update={"text": text})])


async def test_question_focus_can_cover_only_some_of_the_targets(context: ChatContext) -> None:
    plan = await compile_reply(
        RootReply(
            message="질문을 만들어요.",
            items=[item()],
            command=QuestionsCommand(candidates=["C1", "C2"], focus={"C1": item().text}),
        ),
        interview_context(context),
        default_toolkit(),
        {},
    )

    assert plan.question_targets == [row.application_id for row in context.candidates[:2]]
    assert set(plan.question_focus) == {context.candidates[0].application_id}
