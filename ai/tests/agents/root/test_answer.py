from root_context import make_context

from hiremate_ai.agents.root.answer import readable
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent

type Applicants = dict[str, ApplicantDetail]


def test_readable_replaces_candidate_numbers_with_names(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="요청")

    assert readable("C1 정유민과 C2를 비교했어요.", context) == "정유민과 김하늘를 비교했어요."


def test_readable_drops_number_in_parentheses_after_the_name(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="요청")

    assert (
        readable("서민재(C8)는 협업을 강조했어요. (C2)도 봤어요.", context)
        == "서민재는 협업을 강조했어요. (김하늘)도 봤어요."
    )


def test_readable_drops_evidence_numbers(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="요청")

    text = readable("C1 정유민 서류에서 E6 팀 성과 항목과 E4(본인 개선), 근거(E2, E3)를 확인해야 해요.", context)

    assert text == "정유민 서류에서 팀 성과 항목과 본인 개선, 근거를 확인해야 해요."


def test_readable_keeps_words_that_look_like_numbers(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="요청")

    assert readable("E2E 테스트와 E3 등급 체계", context) == "E2E 테스트와 등급 체계"
