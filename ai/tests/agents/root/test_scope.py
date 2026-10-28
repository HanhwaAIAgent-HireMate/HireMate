from typing import Any

from root_context import extra_row, make_context

from hiremate_ai.agents.root.scope import (
    NO_CHECKED,
    NO_MENTIONS,
    NO_RESULT,
    NO_SELECTED,
    NO_SUBJECT,
    NOT_FOUND,
    Scope,
    expand_scope,
)
from hiremate_ai.agents.root.types import CandidateRow, ChatContext
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
