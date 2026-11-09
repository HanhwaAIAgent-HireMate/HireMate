"""이력서 · 포트폴리오를 담당자가 훑어보기 좋은 표로 정리한다 (서류 화면의 정리 보기). 판단 · 점수는 매기지 않는다.

이력서는 경력(기간 · 소속 · 역할 · 주요 업무) · 주요 경험(프로젝트 · 본인 수행 내용 · 기재된 성과) · 기술 · 자격으로,
포트폴리오는 프로젝트마다 문제 · 해결 · 기술 · 성과 카드로 정리한다. 모델이 짧게 옮긴 글은 코드가 원문에 맞춰 거른다.
- 행마다 원문에서 찾은 근거 문장이 하나는 있어야 한다 (없으면 지어낸 행일 수 있어 뺀다).
- 칸의 숫자는 원문에 있어야 한다 (없으면 그 칸을 비운다).
- 기술 · 자격(포트폴리오 프로젝트의 기술 포함)은 원문에 적힌 이름만 남긴다.
- 블라인드 채용이면 학력 · 출신 학교가 나오는 행과 항목을 뺀다.
"""

import re
from collections.abc import Sequence

from pydantic import BaseModel, Field

from hiremate_ai.agents.analysis.application.ask import ask
from hiremate_ai.agents.analysis.application.extract import quotes_in
from hiremate_ai.agents.analysis.application.types import DigestRow, DigestSection, DocumentDigest, Quote
from hiremate_ai.agents.guardrails import education_term
from hiremate_ai.contract import ApplicantDocument, DocumentType
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, document_block

_COMMON = """- 서류에 적힌 것만 옮긴다. 추측하거나 보태지 않는다. 판단 · 평가 · 점수는 쓰지 않는다.
- 칸은 명사형으로 짧게 쓴다 (30자 안팎). 숫자 · 기술 이름 · 회사 이름은 원문 그대로 쓴다.
- 해당하는 내용이 서류에 없으면 그 칸은 빈 문자열로 둔다.
- evidence는 그 행을 받치는 원문 문장 1~2개다 (원문 글자 그대로).
- 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 쓰지 않는다."""

# 이력서 · 포트폴리오 정리 규칙. 서류 읽기(reading)가 사실 추출 규칙과 함께 한 번에 묻는다
RESUME_RULES = f"""- careers: 재직 · 인턴 · 프리랜서 경력. 회사마다 한 행, 최근 것부터.
  period는 '2022.03 ~ 2025.02'처럼 원문 표기 그대로, organization은 회사 이름,
  role은 부서 · 직무 · 직급, duties는 맡은 일 한 줄이다.
- experiences: 프로젝트 · 주요 업무 경험. 경험마다 한 행. project는 이름, actions는 본인이 한 일(팀이 한 일은 빼고 본인
  역할만), result는 원문에 적힌 성과(수치가 있으면 '무엇 전 → 후' 그대로).
  성과가 없으면 비운다.
- skills: 기술 · 도구 이름. certificates: 자격증 · 어학 · 수상 한 줄씩 (이름과 연월).
{_COMMON}"""

PORTFOLIO_RULES = f"""- projects: 프로젝트마다 하나, 원문 순서대로. title은 프로젝트 이름(없으면 다룬 주제),
  problem은 해결하려던 문제, solution은 본인이 한 해결(팀이 한 일은 빼고 본인 역할만),
  skills는 그 프로젝트에 쓴 기술 · 도구 이름(원문 표기 그대로),
  result는 원문에 적힌 성과(수치가 있으면 '무엇 전 → 후' 그대로).
{_COMMON}"""

RESUME_SYSTEM = f"""너는 이력서 한 건을 담당자가 훑어보기 좋은 표로 정리한다.

{RESUME_RULES}

{UNTRUSTED_RULE}"""

PORTFOLIO_SYSTEM = f"""너는 포트폴리오 한 건을 프로젝트마다 카드로 정리한다.

{PORTFOLIO_RULES}

{UNTRUSTED_RULE}"""


class _Career(BaseModel):
    period: str = ""
    organization: str = ""
    role: str = ""
    duties: str = ""
    evidence: list[str] = Field(default=[], description="원문 문장 1~2개 (글자 그대로)")


class _Experience(BaseModel):
    project: str = ""
    actions: str = ""
    result: str = ""
    evidence: list[str] = Field(default=[], description="원문 문장 1~2개 (글자 그대로)")


class ResumeDigest(BaseModel):
    careers: list[_Career] = []
    experiences: list[_Experience] = []
    skills: list[str] = []
    certificates: list[str] = []


class _Project(BaseModel):
    title: str = ""
    problem: str = ""
    solution: str = ""
    skills: list[str] = []
    result: str = ""
    evidence: list[str] = Field(default=[], description="원문 문장 1~2개 (글자 그대로)")


class PortfolioDigest(BaseModel):
    projects: list[_Project] = []


CAREER_COLUMNS = ["기간", "소속 · 역할", "주요 업무"]
EXPERIENCE_COLUMNS = ["프로젝트", "본인 수행 내용", "기재된 성과"]
PROJECT_COLUMNS = ["문제", "해결", "성과"]
_NUMBER = re.compile(r"\d[\d,.]*")


async def digest_document(llm: LlmClient, document: ApplicantDocument, *, blind: bool = False) -> DocumentDigest:
    """이력서 · 포트폴리오 정리만 묻는다. 서류 읽기(reading)가 추출과 함께 묻다가 출력 한도에서 잘리면 쓴다."""
    if document.type == DocumentType.RESUME:
        resume = await ask(
            llm,
            ResumeDigest,
            system=RESUME_SYSTEM,
            user=f"{document_block(document)}\n\n위 이력서를 표로 정리해 줘.",
        )
        return resume_digest(document, resume, blind=blind)
    portfolio = await ask(
        llm,
        PortfolioDigest,
        system=PORTFOLIO_SYSTEM,
        user=f"{document_block(document)}\n\n위 포트폴리오를 프로젝트마다 정리해 줘.",
    )
    return portfolio_digest(document, portfolio, blind=blind)


def resume_digest(document: ApplicantDocument, resume: ResumeDigest, *, blind: bool = False) -> DocumentDigest:
    careers = [
        row
        for career in resume.careers
        if (
            row := _row(
                document,
                "",
                [
                    career.period,
                    " · ".join(part for part in (career.organization, career.role) if part.strip()),
                    career.duties,
                ],
                career.evidence,
                blind,
            )
        )
    ]
    experiences = [
        row
        for experience in resume.experiences
        if (
            row := _row(
                document, "", [experience.project, experience.actions, experience.result], experience.evidence, blind
            )
        )
    ]
    skills = list(dict.fromkeys(skill.strip() for skill in resume.skills if _written(skill, document)))
    certificates = [
        line.strip()
        for line in resume.certificates
        if _written(line.split("(")[0].split("—")[0], document) and not (blind and education_term(line))
    ]
    sections = []
    if careers:
        sections.append(DigestSection(title="경력", columns=CAREER_COLUMNS, rows=careers))
    if experiences:
        sections.append(DigestSection(title="주요 경험", columns=EXPERIENCE_COLUMNS, rows=experiences))
    if skills or certificates:
        sections.append(DigestSection(title="기술 · 자격", tags=skills, items=list(dict.fromkeys(certificates))))
    return DocumentDigest(document=document.type, sections=sections)


def portfolio_digest(document: ApplicantDocument, portfolio: PortfolioDigest, *, blind: bool = False) -> DocumentDigest:
    projects = [
        row
        for project in portfolio.projects
        if (
            row := _row(
                document,
                project.title,
                [project.problem, project.solution, project.result],
                project.evidence,
                blind,
                tags=[skill for skill in project.skills if _written(skill, document)],
            )
        )
    ]
    if not projects:
        return DocumentDigest(document=document.type)
    return DocumentDigest(
        document=document.type,
        sections=[DigestSection(title="프로젝트", layout="cards", columns=PROJECT_COLUMNS, rows=projects)],
    )


def _row(
    document: ApplicantDocument,
    title: str,
    cells: list[str],
    evidence: list[str],
    blind: bool,
    *,
    tags: Sequence[str] = (),
) -> DigestRow | None:
    """원문 근거가 있는 행만 만든다. 원문에 없는 숫자가 든 칸은 비운다."""
    quotes: list[Quote] = quotes_in([document], evidence)
    if not quotes:
        return None
    text = " ".join([title, *cells])
    if blind and (education_term(text) or any(education_term(quote.sentence) for quote in quotes)):
        return None
    source = _compact(document.text)
    cleaned = [" ".join(cell.split()) if _numbers_written(cell, source) else "" for cell in cells]
    title = " ".join(title.split()) if _numbers_written(title, source) else ""
    if not title and not any(cleaned):
        return None
    return DigestRow(
        title=title, cells=cleaned, tags=list(dict.fromkeys(tag.strip() for tag in tags)), quotes=quotes[:2]
    )


def _numbers_written(text: str, source: str) -> bool:
    return all(number.rstrip(",.") in source for number in _NUMBER.findall(text))


def _written(name: str, document: ApplicantDocument) -> bool:
    """이름(기술 · 자격)이 원문에 적혀 있는지. 공백 · 대소문자 차이는 무시한다."""
    needle = _compact(name).lower()
    return len(needle) >= 2 and needle in _compact(document.text).lower()


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)
