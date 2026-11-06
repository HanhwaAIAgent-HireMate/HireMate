from typing import Any
from uuid import uuid4

from root_context import extra_row, make_context

from hiremate_ai.agents.root.scope import (
    EMPTY_TAB,
    NO_CHECKED,
    NO_COMMON,
    NO_MENTIONS,
    NO_RESULT,
    NO_SELECTED,
    NO_SUBJECT,
    NOT_FOUND,
    UNKNOWN_TAB,
    Scope,
    expand_scope,
)
from hiremate_ai.agents.root.types import CandidateRow, ChatContext, ChatTab
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent

type Applicants = dict[str, ApplicantDetail]


def context_of(applicants: Applicants, company: CompanyProfile, posting: PostingContent, **kwargs: Any) -> ChatContext:
    return make_context(applicants, company, posting, message="요청", **kwargs)


def names(rows: list[CandidateRow] | str) -> list[str]:
    assert not isinstance(rows, str), rows
    return [row.name for row in rows]


def ids(applicants: Applicants, *people: str) -> list[str]:
    return [str(applicants[person].info.application_id) for person in people]


def test_sources_expand_in_order_without_duplicates(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(
        sample_applicants, sample_company, sample_posting, mentions=["정유민"], checked=["정유민", "김하늘"]
    )

    rows = expand_scope(Scope(sources=["mentions", "checked"]), context, None, [])

    assert names(rows) == ["정유민", "김하늘"]


def test_pick_from_previous_result(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    rows = expand_scope(Scope(picks=["C6"]), context, ids(sample_applicants, "김하늘", "한예린"), [])

    assert names(rows) == ["한예린"]


def test_result_and_subject_follow_saved_order(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    result = ids(sample_applicants, "한예린", "김하늘")
    subject = ids(sample_applicants, "서민재")

    rows = expand_scope(Scope(sources=["result", "subject"]), context, result, subject)

    assert names(rows) == ["한예린", "김하늘", "서민재"]


def test_selected_and_all(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, selected=["박서준"])

    assert names(expand_scope(Scope(sources=["selected"]), context, None, [])) == ["박서준"]
    assert len(names(expand_scope(Scope(sources=["all"]), context, None, []))) == len(context.candidates)


def test_homonym_asks_with_each_person(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, extra_rows=[extra_row("정유민")])

    asked = expand_scope(Scope(names=["정유민"]), context, None, [])

    assert isinstance(asked, str) and asked.startswith("정유민 님이 2명이에요(")
    assert asked.endswith("@로 한 명을 골라 주세요.")


def test_missing_name(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    assert expand_scope(Scope(names=["문가온"]), context, None, []) == NOT_FOUND.format(names="문가온")


def test_empty_sources_ask(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    assert expand_scope(Scope(sources=["mentions"]), context, None, []) == NO_MENTIONS
    assert expand_scope(Scope(sources=["checked"]), context, None, []) == NO_CHECKED
    assert expand_scope(Scope(sources=["selected"]), context, None, []) == NO_SELECTED
    assert expand_scope(Scope(sources=["subject"]), context, None, []) == NO_SUBJECT


def test_previous_result_none_or_empty_asks(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    assert expand_scope(Scope(sources=["result"]), context, None, []) == NO_RESULT
    assert expand_scope(Scope(sources=["result"]), context, [], []) == NO_RESULT


def with_tabs(context: ChatContext, applicants: Applicants, *tabs: tuple[str, list[str]]) -> ChatContext:
    """마지막 탭이 현재 탭이다."""
    made = [
        ChatTab(
            id=uuid4(),
            name=name,
            current=index == len(tabs) - 1,
            application_ids=[applicants[person].info.application_id for person in people],
        )
        for index, (name, people) in enumerate(tabs)
    ]
    return context.model_copy(update={"tabs": made})


def test_tabs_expand_to_people_selected_in_every_tab(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = with_tabs(
        context_of(sample_applicants, sample_company, sample_posting),
        sample_applicants,
        ("경력 5년 이상", ["한예린", "정유민", "김하늘", "박서준"]),
        ("경력 4년 이상", ["김하늘", "정유민", "한예린"]),
        ("시스템 연동", ["정유민", "서민재", "한예린"]),
        ("새 탭", []),
    )

    rows = expand_scope(Scope(tabs=["T1", "t2", "3"]), context, None, [])

    assert names(rows) == ["한예린", "정유민"]


def test_single_tab_is_its_selection(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = with_tabs(
        context_of(sample_applicants, sample_company, sample_posting),
        sample_applicants,
        ("Kafka", ["박서준", "최지우"]),
        ("새 탭", []),
    )

    assert names(expand_scope(Scope(tabs=["T1"]), context, None, [])) == ["박서준", "최지우"]


def test_tabs_ask_back_when_unknown_empty_or_disjoint(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = with_tabs(
        context_of(sample_applicants, sample_company, sample_posting),
        sample_applicants,
        ("Kafka", ["박서준"]),
        ("Go", ["최지우"]),
        ("새 탭", []),
    )

    assert expand_scope(Scope(tabs=["T9"]), context, None, []) == UNKNOWN_TAB
    assert expand_scope(Scope(tabs=["T1", "T3"]), context, None, []) == EMPTY_TAB.format(name="새 탭")
    assert expand_scope(Scope(tabs=["T1", "T2"]), context, None, []) == NO_COMMON.format(names="Kafka, Go")
