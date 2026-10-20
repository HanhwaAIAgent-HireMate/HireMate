from uuid import uuid4

from root_context import extra_row, make_context

from hiremate_ai.agents.root.targets import checked, resolve
from hiremate_ai.agents.root.types import CandidateRow
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent

type Applicants = dict[str, ApplicantDetail]


def names(rows: list[CandidateRow]) -> list[str]:
    return [row.name for row in rows]


def test_mentions_and_names(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="@정유민 김하늘이랑 비교해줘", mentions=["정유민"]
    )

    targets = resolve(context)

    assert names(targets.rows) == ["정유민", "김하늘"]
    assert targets.ambiguous == []


def test_mention_wins_over_same_name(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="@정유민 빼줘",
        mentions=["정유민"],
        extra_rows=[extra_row("정유민")],
    )

    targets = resolve(context)

    assert [row.application_id for row in targets.rows] == [sample_applicants["정유민"].info.application_id]
    assert targets.ambiguous == []


def test_same_name_without_mention_is_ambiguous(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="정유민 빼줘", extra_rows=[extra_row("정유민")]
    )

    targets = resolve(context)

    assert targets.rows == []
    assert targets.ambiguous == ["정유민"]


def test_longer_name_wins(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="이도윤 추가해줘", extra_rows=[extra_row("이도")]
    )

    assert names(resolve(context).rows) == ["이도윤"]


def test_shorter_name_used_on_its_own_still_counts(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="이도윤이랑 이도 빼줘",
        extra_rows=[extra_row("이도")],
    )

    assert names(resolve(context).rows) == ["이도윤", "이도"]


def test_ignores_ids_outside_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    outside = uuid4()
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="빼줘",
        mentions=[outside],
        checked=[outside, "박서준"],
    )

    assert resolve(context).rows == []
    assert names(checked(context)) == ["박서준"]
