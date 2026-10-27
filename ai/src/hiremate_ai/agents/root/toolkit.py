"""Root Agent가 쓰는 도구 묶음.

앱은 지원자 프로필(프로필 · 검색 담당)과 ChatContext 문서를 함께 쓰는 profile_toolkit을 쓴다.
프로필은 분석을 마친 지원자만 있으므로 문서로 동작하는 도구를 같이 둔다. 테스트는 문서만 쓰는 default_toolkit을 쓴다.
"""

import json
import re
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import Depends
from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiremate_ai.agents.root.stages import StageData, not_yet, reached, stage_data, stage_plan
from hiremate_ai.agents.root.turns import Turn
from hiremate_ai.agents.root.types import CandidateRow, ChatContext, Decision, InterviewQuestion, StageStatus
from hiremate_ai.contract import ApplicantDocument, StageType
from hiremate_ai.db.analysis_store import AnalysisArtifactReader, DbAnalysisArtifacts
from hiremate_ai.db.profile import ItemAgent, Verification
from hiremate_ai.db.session import session_factory
from hiremate_ai.llm.prompt import data_block, documents_block
from hiremate_ai.tools.candidates import CandidateMatch, CandidateSearch, SourcedSentence
from hiremate_ai.tools.profile_lookup import Sessions, profile_text, profile_tool, read_profile
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


def documents_text(chat: ChatContext, row: CandidateRow) -> str:
    documents = _readable_documents(chat, row)
    if not documents:
        return f"{_who(chat, row)}: {NO_DOCUMENTS}"
    return f"{_who(chat, row)}\n\n" + "\n\n".join(f"[{doc.type.label}]\n{doc.text}" for doc in documents)


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


def previous_notes(chat: ChatContext, turns: Sequence[Turn], row: CandidateRow) -> str:
    """앞 대화에서 이 지원자에 대해 정리한 것: 면접 질문의 확인할 점과 답 항목. 없으면 빈 글자다."""
    application_id = str(row.application_id)
    sections = []
    for number, turn in enumerate(turns, start=1):
        lines = [f"확인할 점: {turn['focus'][application_id]}"] if application_id in turn["focus"] else []
        lines += [
            f"항목 [{item['label']}] {item['text']}"
            for item in turn["items"]
            if item["application_id"] == application_id
        ]
        if lines:
            sections.append("\n".join([f'[{number}] 담당자: "{turn["message"]}"', *lines]))
    return "\n\n".join(sections)


@tool
async def resolve_candidates(
    names: list[str],
    runtime: ToolRuntime[RootToolContext],
    source: Literal["names", "mentions", "checked", "selected", "result", "subject"] = "names",
    candidates: list[str] | None = None,
) -> str:
    """요청이 가리키는 이름들을 현재 전형 전체에서 정확히 조회한다. 앞뒤 공백만 제거한다.

    이름은 담당자의 요청과 맥락에서 정한다. 본문의 @이름도 멘션 ID가 없으면 이 도구로 확인한다.
    요청한 이름을 한 번에 모두 넣는다. not_found나 ambiguous가 있으면 대상을 되묻는다.
    비슷한 이름, 체크한 사람이나 이전 대화의 다른 사람으로 대신하지 않는다.
    질문 생성 대상을 확인하거나 이름 대신 화면과 대화의 대상을 확인해야 하면 source로 그 범위를
    고르고 names=[]로 조회한다. candidates를 주면 그 범위 안의 번호만 허용한다.
    조건 검색 범위가 화면의 체크, 선택 C번호로 명확하면 조회 없이 search_candidates의 pool에 직접 넣는다.
    본문에 별도로 지정한 이름은 names에서 빼지 않는다. 이름이 없다고 source의 다른 사람으로 바꾸지 않는다.
    """
    scope = _used(runtime, "resolve_candidates")
    results = []
    for name in dict.fromkeys(name.strip() for name in names if name.strip()):
        refs = [candidate_ref(scope.chat, row.application_id) for row in scope.chat.candidates if row.name == name]
        scope.resolved_names[name] = refs
        status = "not_found" if not refs else "found" if len(refs) == 1 else "ambiguous"
        results.append({"name": name, "status": status, "candidates": refs})
    if source != "names":
        ids = {
            "mentions": [str(value) for value in scope.chat.mentions],
            "checked": [str(value) for value in scope.chat.checked],
            "selected": [str(row.application_id) for row in scope.chat.candidates if row.selected],
            "result": scope.previous_result or [],
            "subject": scope.previous_subject,
        }[source]
        by_id = {
            str(row.application_id): candidate_ref(scope.chat, row.application_id) for row in scope.chat.candidates
        }
        allowed = [by_id[value] for value in ids if value in by_id]
        refs = list(dict.fromkeys(candidates if candidates is not None else allowed))
        incomplete = candidates is None and any(value not in by_id for value in ids)
        if incomplete or not refs or not set(refs) <= set(allowed):
            scope.resolution_errors.append("지정한 화면이나 이전 대화의 범위에서 질문 대상을 확인할 수 없어요.")
            results.append({"source": source, "status": "not_found", "candidates": []})
        else:
            scope.resolved_context.extend(ref for ref in refs if ref not in scope.resolved_context)
            results.append({"source": source, "status": "found", "candidates": refs})
    elif not results:
        scope.resolution_errors.append("질문을 만들 지원자가 명확하지 않아요.")
    return json.dumps(results, ensure_ascii=False)


@tool
async def get_candidate_documents(candidate: str, runtime: ToolRuntime[RootToolContext]) -> str:
    """지원자의 제출 문서(이력서, 자기소개서, 포트폴리오, 자격증) 본문을 읽는다. candidate는 지원자 번호(예: C1)다."""
    context = _used(runtime, "get_candidate_documents")
    row = resolve_ref(context.chat, candidate)
    return OUT_OF_SCOPE if row is None else documents_text(context.chat, row)


@tool
async def get_stage_results(candidate: str, runtime: ToolRuntime[RootToolContext]) -> str:
    """지원자의 전형 결과(결정 상태, 평가 점수, 서류 점수, 경력, 서류 기준선)를 읽는다.

    candidate는 지원자 번호(예: C1)다.
    """
    context = _used(runtime, "get_stage_results")
    row = resolve_ref(context.chat, candidate)
    return OUT_OF_SCOPE if row is None else stage_result_text(context.chat, row)


@tool
async def get_interview_records(candidate: str, runtime: ToolRuntime[RootToolContext]) -> str:
    """지원자의 현재 · 이전 면접 질문과 기록된 답변을 읽는다. candidate는 지원자 번호(예: C1)다."""
    context = _used(runtime, "get_interview_records")
    row = resolve_ref(context.chat, candidate)
    return OUT_OF_SCOPE if row is None else interview_text(context.chat, row)


@tool
async def get_company_profile(runtime: ToolRuntime[RootToolContext]) -> str:
    """회사 소개, 조직 문화, 인재상을 읽는다."""
    return company_text(_used(runtime, "get_company_profile").chat)


@tool
async def get_interviewer_memos(candidate: str, runtime: ToolRuntime[RootToolContext]) -> str:
    """담당자가 메모 참고를 요청했을 때 지원자의 현재·이전 면접관메모를 읽는다. 검증된 지원자 사실이 아니다."""
    context = _used(runtime, "get_interviewer_memos")
    row = resolve_ref(context.chat, candidate)
    if row is None:
        return OUT_OF_SCOPE
    memos = context.chat.interviewer_memos.get(row.application_id, [])
    return (
        "\n\n".join(f"[{memo.stage_name}] 출처: 면접관메모\n{memo.text}" for memo in memos)
        or "저장된 면접관메모가 없어요."
    )


@tool
async def get_posting(runtime: ToolRuntime[RootToolContext]) -> str:
    """채용 공고(직무, 담당 업무, 자격 요건, 우대 사항)를 읽는다."""
    return posting_text(_used(runtime, "get_posting").chat)


@tool
async def get_stage_summary(runtime: ToolRuntime[RootToolContext]) -> str:
    """현재 전형의 전체 지원자와 선택 명단, 결정 현황, 등록 경력 최댓값과 동률 대상을 읽는다."""
    return stage_summary_text(_used(runtime, "get_stage_summary").chat)


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


@tool
async def get_previous_turns(
    runtime: ToolRuntime[RootToolContext],
    turn_numbers: list[int] | None = None,
    candidates: list[str] | None = None,
) -> str:
    """앞 대화 기록을 읽는다. 담당자 질문, Root 답, 다룬 지원자, 면접 질문을 만들 때 정리한 확인할 점과 이유가 있다.

    질문할 때 멘션하거나 체크한 지원자는 그때의 화면 범위로 구별해 보여 준다.
    이전에 만든 질문의 이유나 앞에서 한 이야기를 물으면 이 기록으로 답한다.
    turn_numbers로 초기 대화 목록의 번호를, candidates로 현재 지원자 번호를 지정하면 해당 기록만 읽는다.
    둘 다 생략하면 전체를 읽는다. 같은 기록의 순서와 원문은 유지한다.
    """
    context = _used(runtime, "get_previous_turns")
    if not context.turns:
        return "앞 대화 기록이 없어요."
    chat = context.chat
    if turn_numbers is not None and any(number < 1 or number > len(context.turns) for number in turn_numbers):
        return "현재 대화 목록에 없는 번호가 있어요. 제공된 대화 번호를 확인해 주세요."
    selected_numbers = set(turn_numbers) if turn_numbers is not None else None
    rows = [resolve_ref(chat, ref) for ref in candidates] if candidates is not None else None
    if rows is not None and any(row is None for row in rows):
        return OUT_OF_SCOPE
    selected_ids = {str(row.application_id) for row in rows if row is not None} if rows is not None else None
    by_id = {str(row.application_id): row for row in chat.candidates}

    def who(application_id: str | None) -> str:
        row = by_id.get(application_id or "")
        return _who(chat, row) if row else "지금 전형에 없는 지원자"

    sections = []
    for number, turn in enumerate(context.turns, start=1):
        if selected_numbers is not None and number not in selected_numbers:
            continue
        turn_ids = {
            *turn["targets"],
            *turn.get("mentions", []),
            *turn.get("checked", []),
            *turn["focus"],
            *(item["application_id"] for item in turn["items"] if item["application_id"]),
        }
        if selected_ids is not None and not selected_ids.intersection(turn_ids):
            continue
        lines = [f'[{number}] 담당자: "{turn["message"]}"', f"Root 답: {turn['answer']}"]
        mentions = [who(value) for value in turn.get("mentions", []) if value in by_id]
        checked = [who(value) for value in turn.get("checked", []) if value in by_id]
        if mentions:
            lines.append("멘션한 지원자: " + ", ".join(mentions))
        if checked:
            lines.append("체크한 지원자: " + ", ".join(checked))
        if turn["targets"]:
            lines.append("다룬 지원자: " + ", ".join(who(target) for target in turn["targets"]))
        lines += [f"확인할 점 ({who(application_id)}): {focus}" for application_id, focus in turn["focus"].items()]
        lines += [f"항목 [{item['label']}] {item['text']} ({who(item['application_id'])})" for item in turn["items"]]
        sections.append("\n".join(lines))
    return "\n\n".join(sections) if sections else "선택한 범위의 앞 대화 기록이 없어요."


ANSWER_TOOLS: tuple[BaseTool, ...] = (
    resolve_candidates,
    get_candidate_documents,
    get_stage_results,
    get_interview_records,
    get_interviewer_memos,
    get_company_profile,
    get_posting,
    get_stage_summary,
    get_previous_turns,
)


async def context_brief(scope: RootToolContext, row: CandidateRow) -> str:
    """지원자 한 명의 자료 묶음: 제출 문서, 전형 결과, 면접 기록, 앞 대화에서 정리한 것.

    여러 명 분석이 미리 모아 넣는다. ChatContext로 만들고 도구와 같은 글을 쓴다.
    면접 기록은 면접 전형을 진행한 뒤에만 넣는다. 생기기 전인 기록을 부족한 자료로 읽지 않게 한다.
    지원자 자료는 <data> 블록으로 감싼다 (규칙 5).
    """
    chat = scope.chat
    documents = _readable_documents(chat, row)
    parts = [
        _who(chat, row),
        documents_block(documents) if documents else NO_DOCUMENTS,
        data_block("result", stage_result_text(chat, row)),
    ]
    if reached(chat, StageType.INTERVIEW):
        parts.append(data_block("interview", interview_text(chat, row)))
    notes = previous_notes(chat, scope.turns, row)
    if notes:
        parts.append(data_block("previous", notes))
    return "\n\n".join(parts)


type CandidateBrief = Callable[[RootToolContext, CandidateRow], Awaitable[str]]


def profile_brief(sessions: Sessions) -> CandidateBrief:
    """context_brief 뒤에 지원자 프로필(항목 · 근거 · 출처)을 붙인다. 프로필이 없으면 context_brief 그대로다."""

    async def brief(scope: RootToolContext, row: CandidateRow) -> str:
        async with sessions() as session:
            profile = await read_profile(session, scope, row.application_id)
            # 세션이 열려 있는 동안 글로 바꾼다 (닫힌 뒤에는 항목을 읽을 수 없다)
            profile_part = data_block("profile", profile_text(profile)) if profile else ""
        base = await context_brief(scope, row)
        return f"{base}\n\n{profile_part}" if profile_part else base

    return brief


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


@dataclass(frozen=True)
class RootToolkit:
    """search는 찾기, answer_tools는 도구 루프, brief는 여러 명 분석, evidence는 답 근거 확인이 쓴다.

    judged는 찾기 재확인의 판정 기억이다. 같은 입력이면 앞 판정을 다시 써 같은 질문에 같은 후보를 낸다.
    """

    search: CandidateSearch
    answer_tools: Sequence[BaseTool] = ()
    brief: CandidateBrief = context_brief
    evidence: ProfileEvidence = no_profile_evidence
    judged: dict[str, dict[str, Any]] = field(default_factory=dict, compare=False)
    artifacts: AnalysisArtifactReader | None = None


def default_toolkit() -> RootToolkit:
    """ChatContext 문서만 쓰는 묶음. DB 없이 돈다."""
    return RootToolkit(search=keyword_search, answer_tools=ANSWER_TOOLS, brief=context_brief)


def profile_toolkit(sessions: async_sessionmaker[AsyncSession]) -> RootToolkit:
    """지원자 프로필을 함께 쓰는 묶음.

    찾기는 프로필 문장을 먼저 쓰고, 모자라거나 프로필이 없으면 제출 문서 문장으로 채운다.
    답 근거는 분석 Agent가 프로필에 남긴 근거와도 맞춰 본다 (평가 제출물처럼 ChatContext에 원문이 없는 자료).
    """
    search = merged_search(profile_search(sessions, terms=concept_terms), keyword_search)
    answer_tools = (*ANSWER_TOOLS, profile_tool(sessions, resolve=_chat_ref))
    return RootToolkit(
        search=search,
        answer_tools=answer_tools,
        brief=profile_brief(sessions),
        evidence=profile_evidence(sessions),
        artifacts=DbAnalysisArtifacts(sessions),
    )


@cache
def get_toolkit() -> RootToolkit:
    """FastAPI 의존성. ai DB의 지원자 프로필을 쓴다.

    프로세스에 하나만 만들어 찾기 재확인의 판정 기억을 요청끼리 같이 쓴다.
    DB 없이 찾기 · 분석을 거치는 테스트는 default_toolkit으로 바꿔 넣는다.
    """
    return profile_toolkit(session_factory())


ToolkitDep = Annotated[RootToolkit, Depends(get_toolkit)]


def _chat_ref(scope: ToolScope, ref: str) -> UUID | None:
    """프로필 조회 도구가 받은 지원자 번호(C1)를 지원서 id로 바꾼다. 다른 도구와 같은 번호를 쓴다."""
    row = resolve_ref(scope.chat, ref) if isinstance(scope, RootToolContext) else None
    return row.application_id if row else None


def _used(runtime: ToolRuntime[RootToolContext], name: str) -> RootToolContext:
    runtime.context.called.append(name)
    return runtime.context


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
