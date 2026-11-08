"""이력서 · 포트폴리오 정리: 모델이 짧게 옮긴 표를 코드가 원문에 맞춰 거르는지 본다."""

from uuid import uuid4

from hiremate_ai.agents.analysis.application.digest import (
    PortfolioDigest,
    ResumeDigest,
    portfolio_digest,
    resume_digest,
)
from hiremate_ai.contract import ApplicantDocument, DocumentType

RESUME = ApplicantDocument(
    type=DocumentType.RESUME,
    file_id=uuid4(),
    file_name="이력서.pdf",
    size=1,
    text=(
        "2022.03 ~ 2025.02 가상커머스 · 백엔드 개발\n결제 승인 API를 개발했습니다.\n"
        "오류율을 2%에서 0.3%로 줄였습니다.\nJava Spring Boot PostgreSQL\n정보처리기사 (2021.06)\n"
        "2015.03 ~ 2019.02 한빛대학교 컴퓨터공학과"
    ),
)


def test_resume_rows_need_source_evidence_and_unwritten_numbers_are_blanked() -> None:
    digest = resume_digest(
        RESUME,
        ResumeDigest.model_validate(
            {
                "careers": [
                    {
                        "period": "2022.03 ~ 2025.02",
                        "organization": "가상커머스",
                        "role": "백엔드 개발",
                        "duties": "결제 승인 API 개발",
                        "evidence": ["결제 승인 API를 개발했습니다."],
                    },
                    {"period": "2019 ~ 2021", "organization": "지어낸 회사", "evidence": ["없는 문장입니다."]},
                ],
                "experiences": [
                    {
                        "project": "결제 오류 개선",
                        "actions": "재시도 도입",
                        "result": "오류율 5% → 0.1%",
                        "evidence": ["오류율을 2%에서 0.3%로 줄였습니다."],
                    }
                ],
                "skills": ["Java", "Spring Boot", "Kotlin"],
                "certificates": ["정보처리기사 (2021.06)", "SQLD (2020.01)"],
            }
        ),
    )

    career, experience, skills = digest.sections
    assert [row.cells for row in career.rows] == [
        ["2022.03 ~ 2025.02", "가상커머스 · 백엔드 개발", "결제 승인 API 개발"]
    ]
    assert career.rows[0].quotes[0].sentence == "결제 승인 API를 개발했습니다."
    assert experience.rows[0].cells == ["결제 오류 개선", "재시도 도입", ""]
    assert skills.tags == ["Java", "Spring Boot"]
    assert skills.items == ["정보처리기사 (2021.06)"]


def test_blind_drops_education_rows() -> None:
    digest = resume_digest(
        RESUME,
        ResumeDigest.model_validate(
            {
                "careers": [
                    {
                        "period": "2015.03 ~ 2019.02",
                        "organization": "한빛대학교",
                        "role": "컴퓨터공학과",
                        "evidence": ["2015.03 ~ 2019.02 한빛대학교 컴퓨터공학과"],
                    }
                ]
            }
        ),
        blind=True,
    )

    assert digest.sections == []


def test_portfolio_projects_become_cards() -> None:
    document = ApplicantDocument(
        type=DocumentType.PORTFOLIO,
        file_id=uuid4(),
        file_name="포트폴리오.pdf",
        size=1,
        text=(
            "좌석 예매 동시성 처리\n동시 요청으로 중복 예매가 생겼습니다.\n"
            "Redis 락으로 막아 중복 예매가 37건에서 0건이 됐습니다."
        ),
    )
    digest = portfolio_digest(
        document,
        PortfolioDigest.model_validate(
            {
                "projects": [
                    {
                        "title": "좌석 예매 동시성 처리",
                        "problem": "동시 요청으로 중복 예매",
                        "solution": "Redis 락",
                        "skills": ["Redis", "Kafka"],
                        "result": "중복 예매 37건 → 0건",
                        "evidence": ["Redis 락으로 막아 중복 예매가 37건에서 0건이 됐습니다."],
                    }
                ]
            }
        ),
    )

    (section,) = digest.sections
    assert section.layout == "cards"
    assert section.columns == ["문제", "해결", "성과"]
    assert section.rows[0].title == "좌석 예매 동시성 처리"
    assert section.rows[0].cells[2] == "중복 예매 37건 → 0건"
    # 기술은 원문에 적힌 이름만 남는다
    assert section.rows[0].tags == ["Redis"]
