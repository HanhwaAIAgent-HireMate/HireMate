"""Root Agent가 쓰는 도구 묶음.

앱은 지원자 프로필(프로필 · 검색 담당)과 ChatContext 문서를 함께 쓰는 profile_toolkit을 쓴다.
프로필은 분석을 마친 지원자만 있으므로 문서로 동작하는 도구를 같이 둔다. 테스트는 문서만 쓰는 default_toolkit을 쓴다.
"""

import re
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiremate_ai.agents.analysis.application.present import CATEGORY_LABEL
from hiremate_ai.agents.analysis.application.store import DbReviewStore
from hiremate_ai.agents.analysis.application.types import VERDICT_LABEL, Actor, ApplicationReview, Verdict
from hiremate_ai.agents.root.ledger import (
    COMPANY_SOURCE,
    INTERVIEW_SOURCE,
    MEMO_SOURCE,
    POSTING_SOURCE,
    RESULT_SOURCE,
    TURN_SOURCE,
    Cap,
    Ledger,
)
from hiremate_ai.agents.root.stages import StageData, not_yet, stage_data, stage_plan
from hiremate_ai.agents.root.turns import Turn, verified_turn_items
from hiremate_ai.agents.root.types import CandidateRow, ChatContext, Decision, InterviewQuestion, StageStatus
from hiremate_ai.contract import ApplicantDocument, StageType
from hiremate_ai.db.analysis_store import AnalysisArtifactReader, DbAnalysisArtifacts
from hiremate_ai.db.profile import ItemAgent, ItemCategory, Verification
from hiremate_ai.db.session import session_factory
from hiremate_ai.llm.prompt import data_block
from hiremate_ai.tools.candidates import CandidateMatch, CandidateSearch, SourcedSentence
from hiremate_ai.tools.profile_lookup import (
    Sessions,
    ordered_items,
    profile_front,
    read_profile,
)
from hiremate_ai.tools.profile_search import profile_search
from hiremate_ai.tools.scope import ToolScope


@dataclass(frozen=True)
class RootToolContext(ToolScope):
    """Root의 도구가 받는 범위. 임시 도구는 chat을 읽고, 다른 역할의 도구는 ToolScope 필드만 읽는다.

    called에는 도구 루프에서 부른 도구 이름이 쌓인다.
    """

    chat: ChatContext
    called: list[str] = field(default_factory=list)
    turns: list[Turn] = field(default_factory=list)  # 대화방의 앞 턴 기록 (대화 기억이 없으면 비어 있다)
    resolved_names: dict[str, list[str]] = field(default_factory=dict)  # 이번 요청에서 조회한 이름과 일치하는 C번호
    resolved_context: list[str] = field(default_factory=list)
    resolution_errors: list[str] = field(default_factory=list)
    previous_result: list[str] | None = None
    previous_subject: list[str] = field(default_factory=list)


def scope_of(context: ChatContext, turns: Sequence[Turn] = ()) -> RootToolContext:
    return RootToolContext(
        company_id=context.company.company_id,
        recruitment_id=context.recruitment_id,
        stage_id=context.stage_id,
        application_ids=frozenset(row.application_id for row in context.candidates),
        chat=context,
        turns=list(turns),
    )


# 조건 하나에 모으는 문장 수. 재확인이 이 가운데 근거를 고른다
SENTENCES_PER_CONCEPT = 3
_WORD = re.compile(r"[가-힣]{2,}|[A-Za-z][A-Za-z+#.]+")
_PARTICLE = re.compile(r"(이|가|을|를|은|는|도|만|의|과|와|에서|에|로|으로|이랑|랑)$")
_SENTENCE = re.compile(r"\n+|(?<=[.!?])\s+")
_STOP_WORDS = {
    "찾아줘",
    "찾아",
    "보여줘",
    "보여",
    "골라줘",
    "지원자",
    "사람",
    "그중",
    "중에서",
    "추가해줘",
    "추가",
    "해줘",
    "경험",
    "있는",
    "있어",
    "있나",
    "드러나는",
    "관련",
    "가진",
    "구체적으로",
    "적힌",
    "현재",
    "결과",
    "좋은",
    "지금",
    "우리",
    "회사",
    "중요하게",
    "보는",
    "요소",
    "도메인",
    "프로젝트",
    "지원서",
    "내용",
    "가장",
    "모두",
    "전체",
    "선택",
    "처리",
    "능력",
    "역량",
    "강조한",
    "강조",
    "해본",
    "해",
    "본",
}
_SYNONYMS = {
    "금융": [
        "금융",
        "은행",
        "카드",
        "페이",
        "증권",
        "보험",
        "결제",
        "정산",
        "뱅킹",
        "pg",
        "finance",
        "bank",
        "payment",
    ],
    "결제": ["결제", "정산", "payment", "settlement"],
    "대용량": ["대용량", "트래픽", "트랜잭션", "traffic", "transaction"],
    "협업": ["협업", "협력", "소통", "함께", "회고", "collaboration", "teamwork"],
    "리더": ["리더", "리드", "주도", "lead"],
}


def concept_terms(concept: str) -> list[str]:
    """조건 하나를 찾을 낱말들. 조사와 흔한 말을 빼고 같은 뜻의 낱말로 넓힌다."""
    terms: list[str] = []
    for match in _WORD.finditer(concept):
        word = _PARTICLE.sub("", match.group()).lower()
        if len(word) < 2 or word in _STOP_WORDS:
            continue
        terms += [term for term in _SYNONYMS.get(word, [word]) if term not in terms]
    return terms


async def keyword_search(scope: ToolScope, concepts: Sequence[str], pool: Sequence[UUID]) -> list[CandidateMatch]:
    """임시 검색: 제출 문서에서 조건 낱말이 든 문장을 조건마다 몇 개씩 찾는다. 넓게 모으고 판정은 재확인에 맡긴다."""
    if not isinstance(scope, RootToolContext):
        raise TypeError("keyword_search는 ChatContext가 든 RootToolContext로만 부른다")
    term_sets = [terms for terms in (concept_terms(concept) for concept in concepts) if terms]
    matches = []
    for application_id in pool:
        if application_id not in scope.application_ids:
            continue
        sentences = _sentences(scope.chat, application_id)
        found: list[SourcedSentence] = []
        hits = 0
        for terms in term_sets:
            hit = _best_sentences(sentences, terms)
            hits += bool(hit)
            found += [sourced for sourced in hit if sourced not in found]
        if found:
            matches.append(CandidateMatch(application_id=application_id, sentences=found, hits=hits))
    return sorted(matches, key=lambda match: -match.hits)


def merged_search(*searches: CandidateSearch) -> CandidateSearch:
    """검색 여럿을 조건마다 불러 지원자별로 합친다. 어느 검색에서든 걸린 조건을 맞은 조건으로 센다.

    조건마다 앞 검색의 문장부터 SENTENCES_PER_CONCEPT개까지 쓴다. 재확인에 넣는 문장 수는 검색 하나일 때와 같다.
    """

    async def search(scope: ToolScope, concepts: Sequence[str], pool: Sequence[UUID]) -> list[CandidateMatch]:
        sentences: dict[UUID, list[SourcedSentence]] = {}
        hits: dict[UUID, int] = {}
        for concept in concepts:
            found: dict[UUID, list[SourcedSentence]] = {}
            for each in searches:
                for match in await each(scope, [concept], pool):
                    picked = found.setdefault(match.application_id, [])
                    picked += [sourced for sourced in match.sentences if sourced not in picked]
            for application_id, picked in found.items():
                hits[application_id] = hits.get(application_id, 0) + 1
                kept = sentences.setdefault(application_id, [])
                kept += [sourced for sourced in picked[:SENTENCES_PER_CONCEPT] if sourced not in kept]
        matches = [
            CandidateMatch(
                application_id=application_id, sentences=sentences[application_id], hits=hits[application_id]
            )
            for application_id in dict.fromkeys(pool)
            if application_id in hits
        ]
        return sorted(matches, key=lambda match: -match.hits)

    return search


def _best_sentences(sentences: list[SourcedSentence], terms: list[str]) -> list[SourcedSentence]:
    """조건 낱말이 든 문장 가운데 낱말이 많이 든 순으로 몇 개.

    넓은 동의어가 엉뚱한 문장에 걸려도 진짜 근거가 남게 한다.
    """
    scored = []
    for index, sourced in enumerate(sentences):
        lower = sourced.sentence.lower()
        count = sum(term in lower for term in terms)
        if count:
            scored.append((-count, index, sourced))
    return [sourced for _, _, sourced in sorted(scored)[:SENTENCES_PER_CONCEPT]]


OUT_OF_SCOPE = (
    "조회 범위 밖의 지원자예요. 이름은 resolve_candidates로 확인하세요. "
    "일치하는 대상이 없거나 동명이인이면 clarify로 되묻고, 다른 지원자 번호로 바꾸지 마세요."
)
NO_DOCUMENTS = "읽을 수 있는 제출 문서 본문이 없어요."
NO_INTERVIEW_STAGE = "이 채용에는 면접 전형이 없어요."
EARLIER_SCORE = "앞 평가 전형의 점수는 이 전형에서 불러오지 않았어요. 점수가 없다는 뜻은 아니에요."
NO_ANSWER = "(답변 기록 없음)"
NOT_ANSWERED = "(답변 아직 입력하지 않음)"
_REF = re.compile(r"^\s*[Cc]?(\d+)\s*$")
_DECISIONS = {Decision.PENDING: "미결정", Decision.PASS: "합격", Decision.FAIL: "불합격"}
_STAGES = {StageType.DOCUMENT: "서류", StageType.ASSESSMENT: "평가", StageType.INTERVIEW: "면접"}


def candidate_ref(context: ChatContext, application_id: UUID) -> str:
    """도구와 답에서 지원자를 가리키는 번호. 전형 지원자 순서로 C1부터 매긴다."""
    for index, row in enumerate(context.candidates, start=1):
        if row.application_id == application_id:
            return f"C{index}"
    raise ValueError(f"현재 전형에 없는 지원자다: {application_id}")


def resolve_ref(context: ChatContext, ref: str) -> CandidateRow | None:
    """지원자 번호(C3, c3, 3)를 지원자로 바꾼다. 없는 번호면 None."""
    match = _REF.match(ref)
    if match is None:
        return None
    index = int(match.group(1))
    return context.candidates[index - 1] if 1 <= index <= len(context.candidates) else None


def stage_result_text(chat: ChatContext, row: CandidateRow) -> str:
    """평가 점수는 평가 전형에서만 기록된다. 아직 평가 전형을 진행하지 않았으면 줄을 넣지 않는다."""
    document = chat.document_scores.get(row.application_id)
    lines = [
        _who(chat, row),
        f"결정: {_DECISIONS[row.decision]}",
        f"선택 여부: {'선택됨' if row.selected else '미선택'}",
    ]
    match stage_data(chat, StageType.ASSESSMENT):
        case StageData.CURRENT:
            missing = "아직 입력하지 않음" if chat.stage_status is StageStatus.ACTIVE else "없음"
            lines.append(f"평가 점수: {f'{row.score:g}점' if row.score is not None else missing}")
            if (scores := chat.assessments.get(row.application_id)) is not None:
                areas = " · ".join(
                    f"{name} {'없음' if value is None else f'{value:g}점'}" for name, value in scores.areas.items()
                )
                lines += [f"평가 영역 점수: {areas}", f"평가 등급: {scores.grade or '없음'}"]
        case StageData.EARLIER:
            lines.append(f"평가 점수: {EARLIER_SCORE}")
    lines += [
        f"서류 점수: {f'{document:g}점' if document is not None else '없음'}",
        f"경력: {_career(row)}" + (f", 마지막 회사 {row.last_company}" if row.last_company else ""),
        f"서류 기준선: {'위' if row.above_line else '아래'}",
    ]
    return "\n".join(lines)


def candidate_summary_text(chat: ChatContext, row: CandidateRow) -> str:
    """전형 요약에 표시한 이 지원자의 공식 행. 근거 검증도 같은 지원자의 행만 쓴다."""
    score = f", 평가 {row.score:g}점" if row.score is not None else ""
    return (
        f"{_who(chat, row)}, {_DECISIONS[row.decision]}{score}, 경력 {_career(row)}, "
        f"선택 여부: {'선택됨' if row.selected else '미선택'}"
    )


def interview_text(chat: ChatContext, row: CandidateRow) -> str:
    """면접 기록과 그 상태. 생성 전(뒤 전형), 진행 중 미입력, 실제로 없음, 불러오지 못함을 나눠 말한다."""
    state = stage_data(chat, StageType.INTERVIEW)
    if state is StageData.NONE:
        return f"{_who(chat, row)}: {NO_INTERVIEW_STAGE}"
    if state is StageData.LATER:
        return f"{_who(chat, row)}: {not_yet(chat, StageType.INTERVIEW)}"
    active = state is StageData.CURRENT and chat.stage_status is StageStatus.ACTIVE
    view = chat.interviews.get(row.application_id)
    if view is None or not (view.questions or view.previous):
        if state is StageData.EARLIER:
            # 면접 기록은 면접 전형 화면에서만 받는다. 없다고 단정하지 않게 한다
            return f"{_who(chat, row)}: 이전 면접 기록은 이 전형에서 불러오지 못했어요. 기록이 없다는 뜻은 아니에요."
        if active:
            return f"{_who(chat, row)}: 이 전형의 면접 질문과 답변을 아직 입력하지 않았어요."
        return f"{_who(chat, row)}: 면접 기록이 없어요."
    sections = [_who(chat, row)]
    for previous in view.previous:
        sections.append(f"[{previous.stage_name}]\n" + _questions(previous.questions, NO_ANSWER))
    if view.questions:
        blank = NOT_ANSWERED if active else NO_ANSWER
        sections.append(f"[{chat.stage_name}]\n" + _questions(view.questions, blank))
    return "\n\n".join(sections)


def company_text(chat: ChatContext) -> str:
    company = chat.company
    talents = (
        "\n".join(f"- {talent.title}: {talent.description}" for talent in company.talents) or "- 등록된 인재상 없음"
    )
    return f"{company.name}\n소개: {company.intro}\n문화: {company.culture}\n인재상:\n{talents}"


def posting_text(chat: ChatContext) -> str:
    posting = chat.posting

    def listed(title: str, values: list[str]) -> str:
        return f"{title}:\n" + ("\n".join(f"- {value}" for value in values) or "- 없음")

    return "\n".join(
        [
            f"{posting.title} ({posting.job_category}, {posting.employment_type}, {posting.career})",
            listed("담당 업무", posting.duties),
            listed("자격 요건", posting.qualifications),
            listed("우대 사항", posting.preferred),
        ]
    )


def stage_summary_text(chat: ChatContext) -> str:
    """현재 범위 전체의 공식 집계와 목록. 답변의 전형 결과 근거도 같은 글로 검증한다."""
    counts = {decision: sum(row.decision is decision for row in chat.candidates) for decision in Decision}
    lines = [
        f"{chat.stage_name} ({_STAGES[chat.stage_type]}) 지원자 {len(chat.candidates)}명: "
        + ", ".join(f"{_DECISIONS[decision]} {count}명" for decision, count in counts.items()),
        f"전형 순서: {stage_plan(chat)}",
    ]
    selected = [row for row in chat.candidates if row.selected]
    lines.append(f"선택 지원자 {len(selected)}명: " + (", ".join(_who(chat, row) for row in selected) or "없음"))
    careers = [row.career_years for row in chat.candidates if row.career_years is not None]
    if careers:
        maximum = max(careers)
        leaders = [row for row in chat.candidates if row.career_years == maximum]
        lines.append(
            f"등록 경력 최댓값: {maximum}년 (동률 {len(leaders)}명): " + ", ".join(_who(chat, row) for row in leaders)
        )
    else:
        lines.append("등록 경력 최댓값: 확인 불가")
    lines.append(
        f"경력 미등록 {len(chat.candidates) - len(careers)}명. "
        "등록 경력은 정수 연 단위이며, 월 단위 실제 경력 순위는 확인할 수 없어요."
    )
    lines.extend(candidate_summary_text(chat, row) for row in chat.candidates)
    return "\n".join(lines)


@dataclass(frozen=True)
class AgentEvidence:
    """분석 Agent가 프로필 항목에 남긴 근거 문장. 원문 대조는 그 Agent가 저장할 때 마쳤다."""

    sentence: str
    source: str
    agent: str  # ItemAgent 값
    verification: str = Verification.EVIDENCED  # Verification 값


# 분석 Agent가 아직 확인되지 않았거나 자료끼리 어긋난다고 적은 항목. 근거 문장이 원문에 있어도 사실로 쓰지 않는다
DOUBTFUL: frozenset[str] = frozenset({Verification.UNCONFIRMED, Verification.CONFLICT})

type ProfileEvidence = Callable[[RootToolContext, Sequence[UUID]], Awaitable[dict[UUID, list[AgentEvidence]]]]

# 프로필 항목을 만든 분석 Agent. 그 항목의 근거를 답에 쓰면 답의 agents에 이 이름이 들어간다
AGENT_NAMES: dict[str, str] = {
    ItemAgent.APPLICATION: "Application Agent",
    ItemAgent.ASSESSMENT: "Assessment Agent",
    ItemAgent.INTERVIEW: "Interview Agent",
}


async def no_profile_evidence(
    scope: RootToolContext, application_ids: Sequence[UUID]
) -> dict[UUID, list[AgentEvidence]]:
    """프로필 없이 도는 묶음. 근거는 ChatContext 자료로만 확인한다."""
    return {}


def profile_evidence(sessions: Sessions) -> ProfileEvidence:
    """지원자들의 프로필 항목 가운데 근거 문장이 있는 것을 만든 Agent, 확인 상태와 함께 읽는다.

    범위 밖 지원자는 읽지 않는다.
    """

    async def evidence(scope: RootToolContext, application_ids: Sequence[UUID]) -> dict[UUID, list[AgentEvidence]]:
        found: dict[UUID, list[AgentEvidence]] = {}
        async with sessions() as session:
            for application_id in dict.fromkeys(application_ids):
                profile = await read_profile(session, scope, application_id)
                if profile is not None:
                    found[application_id] = [
                        AgentEvidence(
                            sentence=item.evidence, source=item.source, agent=item.agent, verification=item.verification
                        )
                        for item in profile.items
                        if item.evidence
                    ]
        return found

    return evidence


def recorded_matches(
    recorded: Mapping[UUID, Sequence[AgentEvidence]], application_id: UUID, sentence: str
) -> list[AgentEvidence]:
    """근거 문장이 든 이 지원자의 프로필 근거 전부. 공백 차이는 무시한다."""
    needle = "".join(sentence.split())
    if not needle:
        return []
    return [each for each in recorded.get(application_id, ()) if needle in "".join(each.sentence.split())]


def recorded_evidence(
    recorded: Mapping[UUID, Sequence[AgentEvidence]], application_id: UUID, sentence: str
) -> AgentEvidence | None:
    """근거 문장이 든 이 지원자의 프로필 근거. 공백 차이는 무시한다."""
    return next(iter(recorded_matches(recorded, application_id, sentence)), None)


def cited_agents(recorded: Mapping[UUID, Sequence[AgentEvidence]], cited: Iterable[tuple[UUID, str]]) -> list[str]:
    """(지원자, 근거 문장) 가운데 분석 Agent의 프로필 근거와 같은 문장을 낸 Agent 이름. 처음 나온 순서다."""
    names = []
    for application_id, sentence in cited:
        found = recorded_evidence(recorded, application_id, sentence)
        name = AGENT_NAMES.get(found.agent) if found else None
        if name and name not in names:
            names.append(name)
    return names


NO_PROFILE = "저장된 지원자 프로필이 없어요."
NO_REVIEW = "저장된 서류 분석이 없어요. 필요하면 review_documents로 검토하세요."
NO_MEMOS = "저장된 면접관 메모가 없어요."
_ACTOR_LABELS = {Actor.SELF: "본인", Actor.TEAM: "팀", Actor.UNCLEAR: "역할 불분명"}
_SURE: frozenset[str] = frozenset({Verification.EVIDENCED, Verification.CONFIRMED})


@dataclass(frozen=True)
class ProfileLine:
    """지원자 프로필 항목 한 줄. 분석 Agent가 저장한 값 그대로다."""

    category: str  # ItemCategory 값
    content: str
    evidence: str | None
    source: str
    verification: str  # Verification 값
    agent: str  # ItemAgent 값


@dataclass(frozen=True)
class ProfileView:
    front: str  # 분석 상태, 요약, 경력 · 마지막 회사 · 서류 점수
    lines: list[ProfileLine]


type ProfileReader = Callable[[RootToolContext, UUID], Awaitable[ProfileView | None]]
type ReviewReader = Callable[[RootToolContext, UUID], Awaitable[ApplicationReview | None]]


async def no_profile(scope: RootToolContext, application_id: UUID) -> ProfileView | None:
    """프로필 없이 도는 묶음."""
    return None


async def no_review(scope: RootToolContext, application_id: UUID) -> ApplicationReview | None:
    """서류 분석 원본 없이 도는 묶음."""
    return None


def db_profile_reader(sessions: Sessions) -> ProfileReader:
    """AI 워커의 분석 Agent들이 저장한 지원자 프로필을 읽는다. 범위 밖 지원자는 읽지 않는다."""

    async def read(scope: RootToolContext, application_id: UUID) -> ProfileView | None:
        async with sessions() as session:
            profile = await read_profile(session, scope, application_id)
            if profile is None:
                return None
            lines = [
                ProfileLine(item.category, item.content, item.evidence, item.source, item.verification, item.agent)
                for item in ordered_items(profile)
            ]
            return ProfileView(front=profile_front(profile), lines=lines)

    return read


def db_review_reader(sessions: Sessions) -> ReviewReader:
    """AI 워커의 서류 Agent가 저장한 가장 최근 분석 원본을 읽는다. 범위 밖 지원자는 읽지 않는다."""
    store = DbReviewStore(sessions)

    async def read(scope: RootToolContext, application_id: UUID) -> ApplicationReview | None:
        if application_id not in scope.application_ids:
            return None
        return await store.latest(application_id, company_id=scope.company_id, recruitment_id=scope.recruitment_id)

    return read


def _profile_cap(line: ProfileLine) -> Cap:
    return "OK" if line.verification in _SURE and line.category != ItemCategory.CHECK else "CHECK"


def _profile_refs(ledger: Ledger, row: CandidateRow, lines: Iterable[ProfileLine]) -> list[str]:
    return [
        ledger.line(
            ledger.add(
                row.application_id,
                line.content,
                quote=line.evidence,
                source=line.source,
                cap=_profile_cap(line),
                agent=AGENT_NAMES.get(line.agent),
            )
        )
        for line in lines
    ]


def profile_block(ledger: Ledger, chat: ChatContext, row: CandidateRow, view: ProfileView | None) -> str:
    """전형 결과 한 줄과 분석 Agent들이 정리한 프로필 항목. 항목마다 근거 번호를 붙인다."""
    result = " · ".join(stage_result_text(chat, row).splitlines()[1:])
    lines = [_who(chat, row), ledger.line(ledger.add(row.application_id, result, source=RESULT_SOURCE, cap="OK"))]
    if view is None:
        lines.append(NO_PROFILE)
    else:
        lines += [view.front] if view.front else []
        lines += _profile_refs(ledger, row, view.lines)
    return data_block("profile", "\n".join(lines))


def summary_line(chat: ChatContext, row: CandidateRow) -> str:
    """여러 명을 미리 넣을 때 쓰는 한 줄: 번호, 이름, 결정, 점수, 경력, 선택 여부와 분석 상태."""
    return f"{candidate_summary_text(chat, row)}, 분석 상태: {row.analysis_status.value}"


def application_block(ledger: Ledger, chat: ChatContext, row: CandidateRow, review: ApplicationReview | None) -> str:
    """서류 Agent가 저장한 분석 원본. 사실은 본인 · 팀 · 역할 불분명을 붙이고, 본인 사실만 OK로 올릴 수 있다."""
    if review is None:
        return f"{_who(chat, row)}: {NO_REVIEW}"
    agent = AGENT_NAMES[ItemAgent.APPLICATION]
    lines = [_who(chat, row)]

    def add(text: str, quote: str | None, source: str, cap: Cap) -> None:
        lines.append(
            ledger.line(ledger.add(row.application_id, text, quote=quote, source=source, cap=cap, agent=agent))
        )

    for fact in review.facts:
        first = fact.quotes[0] if fact.quotes else None
        cap: Cap = "OK" if fact.actor is Actor.SELF and fact.supported else "CHECK"
        source = first.document.label if first else "제출 문서"
        add(f"{_ACTOR_LABELS[fact.actor]} · {fact.statement}", first.sentence if first else None, source, cap)
    for period in review.periods:
        span = f"{period.start} ~ {period.end or '현재'}"
        text = f"경력 기간 · {period.company} {period.role} {span} ({period.months}개월)"
        add(text, period.quote.sentence, period.quote.document.label, "OK")
    for result in review.criteria:
        parts = [
            f"{label}: {', '.join(values)}"
            for label, values in (
                ("충족", result.satisfied_parts),
                ("미충족", result.unsatisfied_parts),
                ("확인 안 됨", result.unknown_parts),
            )
            if values
        ]
        text = f"{CATEGORY_LABEL[result.category]} {result.text}: {VERDICT_LABEL[result.verdict]}"
        text += f" ({'; '.join(parts)})" if parts else ""
        first = result.quotes[0] if result.quotes else None
        cap = "CHECK" if result.verdict is Verdict.UNKNOWN else "OK"
        add(text, first.sentence if first else None, first.document.label if first else POSTING_SOURCE, cap)
    for section in review.sections:
        first = section.quotes[0] if section.quotes else None
        add(
            f"{section.document.label} '{section.title}' 요약 · {section.summary}",
            first.sentence if first else None,
            section.document.label,
            "OK",
        )
    for note in [*review.holds, *review.checks]:
        add(note.text, None, note.source, "CHECK")
    return data_block("application", "\n".join(lines))


def interview_block(ledger: Ledger, chat: ChatContext, row: CandidateRow, view: ProfileView | None) -> str:
    """면접 질문과 답변 원문(확인 필요)과 면접 분석 Agent가 정리한 항목."""
    records = chat.interviews.get(row.application_id)
    answered = [
        (stage, question)
        for stage, questions in (
            *((previous.stage_name, previous.questions) for previous in (records.previous if records else [])),
            (chat.stage_name, records.questions if records else []),
        )
        for question in questions
        if question.answer.strip()
    ]
    if not answered:
        lines = [interview_text(chat, row)]
    else:
        lines = [_who(chat, row)]
        lines += [
            ledger.line(
                ledger.add(
                    row.application_id,
                    f"[{stage}] 질문: {question.text}",
                    quote=question.answer.strip(),
                    source=INTERVIEW_SOURCE,
                    cap="CHECK",
                )
            )
            for stage, question in answered
        ]
    if view is not None:
        lines += _profile_refs(ledger, row, [line for line in view.lines if line.agent == ItemAgent.INTERVIEW])
    return data_block("interview", "\n".join(lines))


def memo_block(ledger: Ledger, chat: ChatContext, row: CandidateRow) -> str:
    """담당자의 면접관 메모. 지원자의 발언이나 확인된 사실이 아니므로 언제나 확인 필요다."""
    memos = chat.interviewer_memos.get(row.application_id, [])
    if not memos:
        return f"{_who(chat, row)}: {NO_MEMOS}"
    lines = [_who(chat, row)]
    lines += [
        ledger.line(
            ledger.add(
                row.application_id, f"[{memo.stage_name}] {memo.text}", source=MEMO_SOURCE, cap="CHECK", memo=memo
            )
        )
        for memo in memos
    ]
    return data_block("memos", "\n".join(lines))


def stage_block(ledger: Ledger, chat: ChatContext) -> str:
    """전형 전체의 공식 집계와 지원자별 한 줄. 지원자 줄은 그 지원자의 근거다."""
    owners = {candidate_summary_text(chat, row): row.application_id for row in chat.candidates}
    lines = [
        ledger.line(ledger.add(owners.get(line), line, source=RESULT_SOURCE, cap="OK"))
        for line in stage_summary_text(chat).splitlines()
        if line.strip()
    ]
    return data_block("stage", "\n".join(lines))


def company_block(ledger: Ledger, chat: ChatContext) -> str:
    """회사 소개와 공고. 각 줄이 공통 근거다."""
    lines = [
        ledger.line(ledger.add(None, line.strip(), source=source, cap="OK"))
        for text, source in ((company_text(chat), COMPANY_SOURCE), (posting_text(chat), POSTING_SOURCE))
        for line in text.splitlines()
        if line.strip()
    ]
    return data_block("company", "\n".join(lines))


def turns_block(ledger: Ledger, chat: ChatContext, turns: Sequence[Turn]) -> str:
    """앞 대화의 질문, 답과 검증된 항목. 항목 상태는 그때 검증한 상태 그대로다. 범위 밖 지원자의 항목은 뺀다."""
    in_scope = {str(row.application_id): row.application_id for row in chat.candidates}
    lines: list[str] = []
    for turn in turns:
        lines += [f"질문: {turn['message']}", f"답: {turn['answer']}"]
        for item in verified_turn_items(turn):
            owner = item["application_id"]
            if owner is not None and owner not in in_scope:
                continue
            cap: Cap = "OK" if item.get("status") == "OK" else "CHECK"
            text = f"{item['label']}: {item['text']}"
            lines.append(ledger.line(ledger.add(in_scope[owner] if owner else None, text, source=TURN_SOURCE, cap=cap)))
    return data_block("history", "\n".join(lines)) if lines else ""


@dataclass(frozen=True)
class RootToolkit:
    """search와 judged는 찾기, evidence는 찾기 결과에 근거를 낸 분석 Agent 이름이 쓴다.

    profile과 review는 AI 워커가 미리 저장한 지원자 프로필과 서류 분석 원본을 읽는다.
    judged는 찾기 재확인의 판정 기억이다. 같은 입력이면 앞 판정을 다시 써 같은 질문에 같은 후보를 낸다.
    """

    search: CandidateSearch
    evidence: ProfileEvidence = no_profile_evidence
    judged: dict[str, dict[str, Any]] = field(default_factory=dict, compare=False)
    artifacts: AnalysisArtifactReader | None = None
    profile: ProfileReader = no_profile
    review: ReviewReader = no_review


def default_toolkit() -> RootToolkit:
    """ChatContext 문서만 쓰는 묶음. DB 없이 돈다."""
    return RootToolkit(search=keyword_search)


def profile_toolkit(sessions: async_sessionmaker[AsyncSession]) -> RootToolkit:
    """지원자 프로필을 함께 쓰는 묶음.

    찾기는 프로필 문장을 먼저 쓰고, 모자라거나 프로필이 없으면 제출 문서 문장으로 채운다.
    답 근거는 분석 Agent가 프로필에 남긴 근거와도 맞춰 본다 (평가 제출물처럼 ChatContext에 원문이 없는 자료).
    """
    search = merged_search(profile_search(sessions, terms=concept_terms), keyword_search)
    return RootToolkit(
        search=search,
        evidence=profile_evidence(sessions),
        artifacts=DbAnalysisArtifacts(sessions),
        profile=db_profile_reader(sessions),
        review=db_review_reader(sessions),
    )


@cache
def get_toolkit() -> RootToolkit:
    """FastAPI 의존성. ai DB의 지원자 프로필을 쓴다.

    프로세스에 하나만 만들어 찾기 재확인의 판정 기억을 요청끼리 같이 쓴다.
    DB 없이 찾기 · 분석을 거치는 테스트는 default_toolkit으로 바꿔 넣는다.
    """
    return profile_toolkit(session_factory())


ToolkitDep = Annotated[RootToolkit, Depends(get_toolkit)]


def _who(context: ChatContext, row: CandidateRow) -> str:
    return f"{candidate_ref(context, row.application_id)} {row.name}"


def _career(row: CandidateRow) -> str:
    return "알 수 없음" if row.career_years is None else "신입" if row.career_years == 0 else f"{row.career_years}년"


def _readable_documents(chat: ChatContext, row: CandidateRow) -> list[ApplicantDocument]:
    return [document for document in chat.documents.get(row.application_id, []) if document.text.strip()]


def _questions(questions: Sequence[InterviewQuestion], blank: str) -> str:
    return "\n".join(
        f"Q{number}. {question.text}\nA{number}. {question.answer.strip() or blank}"
        for number, question in enumerate(questions, start=1)
    )


def _sentences(context: ChatContext, application_id: UUID) -> list[SourcedSentence]:
    sentences = []
    for document in context.documents.get(application_id, []):
        for line in _SENTENCE.split(document.text):
            text = line.strip().lstrip("-• ").strip()
            if len(text) >= 4:
                sentences.append(SourcedSentence(sentence=text, source=document.type.label))
    return sentences
