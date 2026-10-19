"""Root Agent가 쓰는 도구 묶음. 프로필 · 검색 도구가 들어오기 전까지는 ChatContext 문서로 동작하는 임시 구현을 쓴다."""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import UUID

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

from hiremate_ai.agents.root.turns import Turn
from hiremate_ai.agents.root.types import CandidateRow, ChatContext, Decision, InterviewQuestion
from hiremate_ai.contract import StageType
from hiremate_ai.tools.candidates import CandidateMatch, CandidateSearch, SourcedSentence
from hiremate_ai.tools.scope import ToolScope


@dataclass(frozen=True)
class RootToolContext(ToolScope):
    """Root의 도구가 받는 범위. 임시 도구는 chat을 읽고, 다른 역할의 도구는 ToolScope 필드만 읽는다.

    called에는 도구 루프에서 부른 도구 이름이 쌓인다. 답의 agents를 채울 때 쓴다.
    """

    chat: ChatContext
    called: list[str] = field(default_factory=list)
    turns: list[Turn] = field(default_factory=list)  # 대화방의 앞 턴 기록 (대화 기억이 없으면 비어 있다)


@dataclass(frozen=True)
class RootToolkit:
    search: CandidateSearch
    answer_tools: Sequence[BaseTool] = ()


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


OUT_OF_SCOPE = "조회 범위 밖의 지원자예요. 지원자 번호(C1 같은)로 다시 불러 주세요."
_REF = re.compile(r"^\s*[Cc]?(\d+)\s*$")
_DECISIONS = {Decision.PENDING: "미결정", Decision.PASS: "합격", Decision.FAIL: "불합격"}
_STAGES = {StageType.DOCUMENT: "서류", StageType.ASSESSMENT: "평가", StageType.INTERVIEW: "면접"}
_SUMMARY_LIMIT = 50


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


@tool
async def get_candidate_documents(candidate: str, runtime: ToolRuntime[RootToolContext]) -> str:
    """지원자의 제출 문서(이력서, 자기소개서, 포트폴리오, 자격증) 본문을 읽는다. candidate는 지원자 번호(예: C1)다."""
    context = _used(runtime, "get_candidate_documents")
    row = resolve_ref(context.chat, candidate)
    if row is None:
        return OUT_OF_SCOPE
    documents = [document for document in context.chat.documents.get(row.application_id, []) if document.text.strip()]
    if not documents:
        return f"{_who(context.chat, row)}: 읽을 수 있는 제출 문서 본문이 없어요."
    return f"{_who(context.chat, row)}\n\n" + "\n\n".join(f"[{doc.type.label}]\n{doc.text}" for doc in documents)


@tool
async def get_stage_results(candidate: str, runtime: ToolRuntime[RootToolContext]) -> str:
    """지원자의 전형 결과(결정 상태, 평가 점수, 서류 점수, 경력, 서류 기준선)를 읽는다.

    candidate는 지원자 번호(예: C1)다.
    """
    context = _used(runtime, "get_stage_results")
    row = resolve_ref(context.chat, candidate)
    if row is None:
        return OUT_OF_SCOPE
    document = context.chat.document_scores.get(row.application_id)
    career = "알 수 없음" if row.career_years is None else "신입" if row.career_years == 0 else f"{row.career_years}년"
    lines = [
        _who(context.chat, row),
        f"결정: {_DECISIONS[row.decision]}",
        f"평가 점수: {f'{row.score:g}점' if row.score is not None else '없음'}",
        f"서류 점수: {f'{document}점' if document is not None else '없음'}",
        f"경력: {career}" + (f" · 마지막 회사 {row.last_company}" if row.last_company else ""),
        f"서류 기준선: {'위' if row.above_line else '아래'}",
    ]
    return "\n".join(lines)


@tool
async def get_interview_records(candidate: str, runtime: ToolRuntime[RootToolContext]) -> str:
    """지원자의 현재 · 이전 면접 질문과 기록된 답변을 읽는다. candidate는 지원자 번호(예: C1)다."""
    context = _used(runtime, "get_interview_records")
    row = resolve_ref(context.chat, candidate)
    if row is None:
        return OUT_OF_SCOPE
    view = context.chat.interviews.get(row.application_id)
    if view is None or not (view.questions or view.previous):
        chat = context.chat
        if chat.stage_type is not StageType.INTERVIEW and StageType.INTERVIEW in chat.previous_types:
            # 면접 기록은 면접 전형 화면에서만 받는다. 없다고 단정하지 않게 한다
            return f"{_who(chat, row)}: 이전 면접 기록은 이 전형에서 불러오지 못했어요. 기록이 없다는 뜻은 아니에요."
        return f"{_who(chat, row)}: 면접 기록이 없어요."
    sections = [_who(context.chat, row)]
    for previous in view.previous:
        sections.append(f"[{previous.stage_name}]\n" + _questions(previous.questions))
    if view.questions:
        sections.append(f"[{context.chat.stage_name}]\n" + _questions(view.questions))
    return "\n\n".join(sections)


@tool
async def get_company_profile(runtime: ToolRuntime[RootToolContext]) -> str:
    """회사 소개, 조직 문화, 인재상을 읽는다."""
    company = _used(runtime, "get_company_profile").chat.company
    talents = (
        "\n".join(f"- {talent.title}: {talent.description}" for talent in company.talents) or "- 등록된 인재상 없음"
    )
    return f"{company.name}\n소개: {company.intro}\n문화: {company.culture}\n인재상:\n{talents}"


@tool
async def get_posting(runtime: ToolRuntime[RootToolContext]) -> str:
    """채용 공고(직무, 담당 업무, 자격 요건, 우대 사항)를 읽는다."""
    posting = _used(runtime, "get_posting").chat.posting

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


@tool
async def get_stage_summary(runtime: ToolRuntime[RootToolContext]) -> str:
    """현재 전형의 인원과 결정 현황, 지원자 번호 · 이름 목록을 읽는다."""
    chat = _used(runtime, "get_stage_summary").chat
    counts = {decision: sum(row.decision is decision for row in chat.candidates) for decision in Decision}
    lines = [
        f"{chat.stage_name} ({_STAGES[chat.stage_type]}) 지원자 {len(chat.candidates)}명: "
        + ", ".join(f"{_DECISIONS[decision]} {count}명" for decision, count in counts.items())
    ]
    for index, row in enumerate(chat.candidates[:_SUMMARY_LIMIT], start=1):
        score = f" · 평가 {row.score:g}점" if row.score is not None else ""
        lines.append(f"C{index} {row.name} · {_DECISIONS[row.decision]}{score}")
    if len(chat.candidates) > _SUMMARY_LIMIT:
        lines.append(f"(그 밖 {len(chat.candidates) - _SUMMARY_LIMIT}명)")
    return "\n".join(lines)


@tool
async def get_previous_turns(runtime: ToolRuntime[RootToolContext]) -> str:
    """앞 대화 기록을 읽는다. 담당자 질문, Root 답, 다룬 지원자, 면접 질문을 만들 때 정리한 확인할 점과 이유가 있다.

    이전에 만든 질문의 이유나 앞에서 한 이야기를 물으면 이 기록으로 답한다.
    """
    context = _used(runtime, "get_previous_turns")
    if not context.turns:
        return "앞 대화 기록이 없어요."
    chat = context.chat
    by_id = {str(row.application_id): row for row in chat.candidates}

    def who(application_id: str | None) -> str:
        row = by_id.get(application_id or "")
        return _who(chat, row) if row else "지금 전형에 없는 지원자"

    sections = []
    for number, turn in enumerate(context.turns, start=1):
        lines = [f'[{number}] 담당자: "{turn["message"]}"', f"Root 답: {turn['answer']}"]
        if turn["targets"]:
            lines.append("다룬 지원자: " + ", ".join(who(target) for target in turn["targets"]))
        lines += [f"확인할 점 ({who(application_id)}): {focus}" for application_id, focus in turn["focus"].items()]
        lines += [f"항목 [{item['label']}] {item['text']} ({who(item['application_id'])})" for item in turn["items"]]
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


ANSWER_TOOLS: tuple[BaseTool, ...] = (
    get_candidate_documents,
    get_stage_results,
    get_interview_records,
    get_company_profile,
    get_posting,
    get_stage_summary,
    get_previous_turns,
)


def default_toolkit() -> RootToolkit:
    return RootToolkit(search=keyword_search, answer_tools=ANSWER_TOOLS)


def _used(runtime: ToolRuntime[RootToolContext], name: str) -> RootToolContext:
    runtime.context.called.append(name)
    return runtime.context


def _who(context: ChatContext, row: CandidateRow) -> str:
    return f"{candidate_ref(context, row.application_id)} {row.name}"


def _questions(questions: Sequence[InterviewQuestion]) -> str:
    return "\n".join(
        f"Q{number}. {question.text}\nA{number}. {question.answer.strip() or '(답변 기록 없음)'}"
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
