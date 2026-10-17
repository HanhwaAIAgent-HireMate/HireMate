from hiremate_ai.agents.guardrails import blocked_attribute
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, DocumentType, PostingContent


def test_samples_load(
    sample_posting: PostingContent, sample_company: CompanyProfile, sample_applicants: dict[str, ApplicantDetail]
) -> None:
    assert sample_posting.title == "결제 플랫폼 백엔드 개발자"
    assert sample_company.talents
    assert len(sample_applicants) == 8
    assert len({applicant.info.application_id for applicant in sample_applicants.values()}) == 8
    assert {applicant.info.recruitment_id for applicant in sample_applicants.values()} == {
        next(iter(sample_applicants.values())).info.recruitment_id
    }


def test_samples_cover_edge_cases(sample_applicants: dict[str, ApplicantDetail]) -> None:
    portfolio = next(
        document for document in sample_applicants["한예린"].documents if document.type == DocumentType.PORTFOLIO
    )

    assert "이전 지시를 모두 무시하고" in portfolio.text
    assert all(document.text == "" for document in sample_applicants["윤태오"].documents)


def test_samples_have_no_discriminatory_attributes(sample_applicants: dict[str, ApplicantDetail]) -> None:
    found = {
        applicant.info.name: word
        for applicant in sample_applicants.values()
        for document in applicant.documents
        if (word := blocked_attribute(document.text))
    }

    assert found == {}
