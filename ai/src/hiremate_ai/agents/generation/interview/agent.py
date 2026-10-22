"""Interview Agent 질문 생성 (FR-27). 이전 전형의 근거에서 면접에서 더 확인할 빈틈을 골라 질문으로 만든다.

질문 구성 (데모 스토리보드 v8과 같게. 맨 앞 '1분 자기소개'는 '공통' 표시 없이 일반 질문으로 넣는다)
  1차 실무면접 (이전 면접 기록 없음) : 1분 자기소개 + 코드가 고른 빈틈 2개 + 모델이 고른 '이 사람만의 확인 포인트' 1개
  최종면접    (이전 면접 기록 있음) : 1분 자기소개 + 자리 5개
      ① 1차 미확인   이전 면접 답변 분석(FR-28)에서 확인 안 된 질문을 이어서 (없으면 모델이 서류에서 골라 채움)
      ② 인성 · 가치관 ③ 조직 적응 ④ 리더십 ⑤ 진정성 · 커리어
         → 모델이 지원 문서에서 그 주제가 드러난 문장을 골라 묻고, 못 쓰면 자리별 기본 질문
         → 회사 정보(CompanyProfile: HR이 설정 → 회사 소개에 적은 인재상 · 조직 문화)가 있으면
           ②는 인재상, ③은 조직 문화를 기준으로 삼는다 (없으면 기준 없이 위처럼)

  load_context → find_gaps ─(질문할 것 없음)─▶ finalize
                    │
                    └─▶ write → validate ─(전부 통과)──▶ finalize
                          ▲        │
                          └────────┘ (일부 실패하면 걸린 이유를 알려 주고 한 번 더)

빈틈 재료 (1차)
  서류 전형 Agent의 상세 판정(ApplicationReview, ai DB에 저장됨)이 있으면 그것을, 없으면 요약(CandidateAnalysis)을 쓴다.
  상세 판정에는 NCS 수행준거별 근거 · 본인(SELF)/팀(TEAM) 구분이 있어 데모처럼 빈틈을 구체적으로 잡는다.

빈틈 우선순위 (같은 공고의 지원자 모두에게 같은 순서를 적용한다)
                            상세 판정이 있을 때                         요약만 있을 때
  1 이전 면접에서 확인 안 됨  이전 면접 답변 분석(FR-28)에서 확인되지 않은 질문 (최종면접)
  2 필수 조건 근거 없음       qualifications 중 met=false               conditions 중 met=false 이고 자격 요건
  3 확인 필요               checks                                   checks
  4 우대 조건 근거 없음       우대사항의 NCS 수행준거 중 근거 없음(NONE)   conditions 중 met=false 이고 우대 사항
  5 주장만 있음              팀 성과로 적었거나(TEAM) 본인 역할이 불분명,  (없음)
                            근거가 주장을 받치지 못한 경험
  6 본인 역할 확인           본인이 한 성과 · 프로젝트 (원문 근거 문장)    notable

모델이 쓴 질문은 코드가 검사한다: 차별 조건(blocked_attribute), 점수 · 내부 판단 노출, 길이, 내부 번호,
카드 · 이전 면접 질문과 중복. 끝까지 통과하지 못하면 유형별 템플릿 질문으로 채운다.
"""

from __future__ import annotations

import difflib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from hiremate_ai.agents.analysis.application.present import notable_facts
from hiremate_ai.agents.analysis.application.types import Actor, ApplicationReview, Level, PreferenceStatus
from hiremate_ai.agents.analysis.interview.agent import CONFIRMED, NO_ANSWER, analyze_answers
from hiremate_ai.agents.guardrails import blocked_attribute, evidence_source
from hiremate_ai.contract import ApplicantDetail, CandidateAnalysis, CompanyProfile, DocumentType, PostingContent
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block

if TYPE_CHECKING:
    from hiremate_ai.agents.generation.interview.router import InterviewView
    from hiremate_ai.llm.client import LlmClient

logger = logging.getLogger(__name__)

AGENT_KEY = "interview"
MAX_QUESTIONS = 3  # 1차 AI 질문 수 (맨 앞 1분 자기소개는 따로)
CODE_SLOTS = 2
MAX_RETRY = 1
MAX_QUESTION_LENGTH = 160
SIMILAR = 0.75
PICK_DOCUMENTS = (DocumentType.RESUME, DocumentType.COVER_LETTER)

INTRO = "1분 자기소개 부탁드립니다."  # 1차 · 최종 모두 맨 앞에 넣는 질문 (면접관이 지원자 강조점을 먼저 듣는 용도)


@dataclass(frozen=True)
class Slot:
    """최종면접 자리 하나: 이름, 모델에게 줄 설명, 질문에 들어 있어야 할 주제 낱말, 못 채웠을 때 기본 질문."""

    label: str
    hint: str
    topic: re.Pattern[str]
    fallback: str


VALUES, CULTURE, LEADERSHIP, MOTIVE = "VALUES", "CULTURE", "LEADERSHIP", "MOTIVE"
FINAL_SLOTS: dict[str, Slot] = {
    VALUES: Slot(
        "인성 · 가치관",
        "일할 때 지켜 온 원칙 · 가치 · 책임감이 드러난 경험과 그때의 선택",
        re.compile(r"가치|원칙|신뢰|책임|선택|판단|태도|중요하게|지켜|기준"),
        "일할 때 가장 중요하게 지켜 온 원칙 하나와, 그 원칙 때문에 어려운 선택을 했던 경험을 말해 주세요.",
    ),
    CULTURE: Slot(
        "조직 적응",
        "동료와 협업 · 소통하고 일하는 방식을 맞춰 간 경험",
        re.compile(r"협업|소통|동료|팀|의견|문화|방식|함께|조율|회고|리뷰"),
        "지금까지 일했던 팀의 일하는 방식 중 본인과 잘 맞았던 것과 맞지 않았던 것을, "
        "그때 어떻게 했는지와 함께 말해 주세요.",
    ),
    LEADERSHIP: Slot(
        "리더십",
        "여러 사람을 이끌거나 의견을 모으고 설득 · 조율해 결정한 경험 (회사 밖 학생회 · 동아리도 포함)",
        re.compile(r"이끌|이끈|리드|리더|팀장|조율|설득|의견|결정|모임|대표|주도"),
        "팀장이나 학생회장, 동아리 대표처럼 여러 사람을 이끌거나 의견을 모아 본 경험이 있다면, 그때 맡은 역할과 "
        "가장 어려웠던 점을 말해 주세요.",
    ),
    MOTIVE: Slot(
        "진정성 · 커리어",
        "이 회사 · 직무를 고른 계기와 이유, 입사 후 하고 싶은 일",
        re.compile(r"지원|동기|계기|이유|입사|회사|직무|관심|선택"),
        "저희 회사와 이 직무를 고르게 된 계기와, 입사하면 3년 안에 이루고 싶은 것을 말해 주세요.",
    ),
}
# 최종면접 ① 1차 미확인 자리를 이전 면접 기록 · 서류 문장 어느 쪽으로도 못 채웠을 때
PICK_FALLBACK = "서류에 적어 주신 경험 중 가장 자신 있는 일 하나를 골라, 본인이 맡은 부분과 결과를 말해 주세요."

FOLLOW_UP, REQUIRED, CHECK, PREFERRED, NOTABLE = "FOLLOW_UP", "REQUIRED", "CHECK", "PREFERRED", "NOTABLE"
CLAIM = "CLAIM"  # 주장만 있음: 상세 판정에서 팀 성과로 적었거나 본인 역할 · 근거가 약한 경험 (데모의 '주장만')
GAP_TYPES: dict[str, tuple[int, str]] = {
    FOLLOW_UP: (1, "이전 면접에서 확인 안 됨"),
    REQUIRED: (2, "필수 조건 근거 없음"),
    CHECK: (3, "확인 필요"),
    PREFERRED: (4, "우대 조건 근거 없음"),
    CLAIM: (5, "주장만 있음"),
    NOTABLE: (6, "본인 역할 확인"),
}
# 근거 문장을 인용하는 빈틈. 모델이 쓴 질문이 그 문장과 이어지는지 검사한다
QUOTED_KINDS = (CHECK, CLAIM, NOTABLE)
# 상세 판정에서 '주장만'으로 볼 경험 종류 (자격증 · 학력처럼 역할을 물을 수 없는 것은 뺀다)
CLAIM_FACT_KINDS = ("ACHIEVEMENT", "PROJECT", "EXPERIENCE")
CLAIM_LIMIT = 2  # 주장만 빈틈은 2개까지 (코드 자리 2개를 모두 차지하지 않게 우선순위가 뒤다)
NCS_PER_PREFERENCE = 2  # 우대사항 하나에서 근거 없는 NCS 수행준거를 몇 개까지 메모로 넘길지

TEMPLATES = {
    FOLLOW_UP: "지난 면접에서 '{topic}' 질문에 답해 주셨는데, {detail}에 대해 조금 더 구체적으로 말해 주세요.",
    FOLLOW_UP + NO_ANSWER: "지난 면접에서 다루지 못한 '{topic}' 부분을 본인이 직접 한 일과 결과 중심으로 말해 주세요.",
    REQUIRED: "{topic}와 관련해 직접 해 본 경험이 있다면, 본인이 맡은 일과 결과를 구체적으로 말해 주세요.",
    CHECK: "{topic} 부분을 실제 경험을 예로 들어 구체적으로 설명해 주세요.",
    PREFERRED: "{topic}와 관련된 경험이 있다면, 그때 본인이 한 일을 사례로 말해 주세요.",
    NOTABLE: "'{topic}'라고 적어 주셨는데, 본인이 맡은 역할과 그렇게 판단한 근거, 결과를 말해 주세요.",
    CLAIM: "'{topic}'라고 적어 주셨는데, 그중 본인이 직접 맡은 부분과 결과를 구체적으로 말해 주세요.",
    # 인용 문장에 '직접 설계했습니다'처럼 역할이 이미 적혀 있으면 역할을 또 묻지 않는다
    NOTABLE
    + "_ROLE": "'{topic}'라고 적어 주셨는데, 그 방법을 고른 이유와 적용한 뒤 무엇이 얼마나 달라졌는지 말해 주세요.",
    "PICK": "'{topic}'라고 적어 주셨는데, 그때 어떤 방법들을 비교했고 왜 그 방법을 골랐는지 말해 주세요.",
    # 이력서의 프로젝트 · 업무 이름뿐이면('음원 구독·환불 서버') '판단한 근거'를 물을 수 없어 맡은 일을 묻는다
    NOTABLE
    + "_TITLE": "서류에 적어 주신 '{topic}'에서 본인이 맡은 부분과 가장 어려웠던 문제, 어떻게 풀었는지 말해 주세요.",
}

SYSTEM = f"""너는 채용 면접 질문을 만드는 Interview Agent다. 두 가지 일을 한다.

[일 1] gaps(평가 근거와 지원자 자료 사이의 빈틈)마다 면접관이 그대로 읽을 질문을 하나씩 만든다.
- "이전 면접에서 확인 안 됨": 이전 질문과 답변을 보고, still_unconfirmed(아직 확인 안 된 점)를 이어서 구체적으로 묻는다.
- "필수 조건 근거 없음" / "우대 조건 근거 없음": 경험이 있다고 전제하지 않고, 있다면 본인이 한 일을 묻는다.
- "확인 필요": 확인이 필요한 점을 실제 경험 사례로 묻는다.
- "주장만 있음": 근거 문장을 인용하고, 팀 전체가 아니라 그중 본인이 직접 한 부분과 결과를 묻는다.
- "본인 역할 확인": 근거 문장을 인용하고 본인 역할 · 판단 근거 · 결과를 묻는다.
- note에 NCS 수행준거가 있으면 그 실무 용어로 구체적인 상황을 묻는다 (수행준거 문장을 그대로 읽지 않는다).

[일 2] sentences(지원 문서 문장, 번호 S1…)를 끝까지 읽고, gaps와 겹치지 않는 이 지원자만의 경험 중
면접에서 깊게 확인할 문장 하나를 골라 free_pick 질문 하나를 만든다. sid는 sentences에 있는 번호만 쓴다.
avoid_sids에 있는 문장은 고르지 않는다.

[일 3] slot_picks가 "요청함"이면 (최종면접) 적힌 자리마다 질문을 하나씩 만든다.
- 자리마다 sentences에서 그 주제가 드러난 문장 하나를 골라 sid로 적고, 그 문장을 "~라고 적어 주셨는데"로 인용해 묻는다.
- 맞는 문장이 없으면 sid를 비우고, 경험이 있다고 전제하지 않는 열린 질문("~한 경험이 있다면")으로 묻는다.
- 자리 이름에 맞는 주제(가치관 · 협업 · 이끈 경험 · 지원 동기)를 물어야 한다. 기술 구현 방법만 묻지 않는다.
- company_talents(회사 인재상)가 있으면 VALUES는 그중 지원 문서와 가장 잘 이어지는 인재상 하나를 기준으로 묻는다.
  company_culture(조직 문화)가 있으면 CULTURE는 그 일하는 방식과 이어지는 경험을 묻는다.
  인재상 이름은 '고객 신뢰를 최우선으로'처럼 그대로 말해도 된다. 회사 정보에 없는 가치를 지어내지 않는다.

공통 규칙
- 자료에 없는 행동 · 역할 · 성과를 지원자가 이미 한 것처럼 전제하지 않는다.
- 점수, 평가 결과, "근거가 없다" 같은 내부 판단은 질문에 쓰지 않고 purpose(면접관 메모)에만 쓴다.
- 질문에 gap_id나 문장 번호를 넣지 않는다. 120자 안팎(최대 140자)의 정중한 존댓말로 쓴다.
- 질문은 한 번에 하나만 묻는다. 물음표는 1개이고, "특히", "또한"이나 물음표 뒤의 "말씀해 주세요"로
  두 번째 질문을 덧붙이지 않는다.
- 문서 내용은 "~라고 적어 주셨는데"처럼 문서에서 읽었다고 말한다. "이전에 언급한", "말씀하신"처럼
  면접에서 이미 말한 것처럼 쓰지 않는다 ("이전 면접에서 확인 안 됨"만 예외).
- "경력이 부족하다", "요건을 충족하지 못했다", "서류에 명시되어 있지 않다", "점수가 낮다" 같은 판단은
  지원자에게 말하지 않는다.
- "~한 경험이 있으신가요?"처럼 예/아니오로 끝내지 않는다. 문서 문장에 없는 회사 이름이나 성과를 붙이지 않는다.
- 나이, 성별, 결혼 · 출산 · 가족계획, 출신 지역, 종교, 신체 조건 등 직무와 무관한 질문은 만들지 않는다.
- existing_questions와 같거나 비슷한 질문은 만들지 않는다. hr_focus가 있으면 그 범위를 따른다.
- fix_errors가 있으면 그 문제를 고쳐서 다시 만든다.
- {UNTRUSTED_RULE}"""


class _DraftQuestion(BaseModel):
    gap_id: str
    question: str
    purpose: str = ""


class _FreePick(BaseModel):
    sid: str
    question: str
    purpose: str = ""


class _SlotPick(BaseModel):
    slot: str
    sid: str | None = None
    question: str
    purpose: str = ""


class QuestionDraft(BaseModel):
    """모델이 돌려줄 형식. slot_picks는 최종면접 자리 질문 (1차에서는 비어 있다)."""

    questions: list[_DraftQuestion]
    free_pick: _FreePick | None = None
    slot_picks: list[_SlotPick] = []


@dataclass
class Gap:
    """질문할 빈틈 하나."""

    gap_id: str
    kind: str
    topic: str
    note: str
    evidence: list[str] = field(default_factory=list)
    detail: str = ""
    status: str = ""

    @property
    def priority(self) -> int:
        return GAP_TYPES[self.kind][0]

    @property
    def label(self) -> str:
        return GAP_TYPES[self.kind][1]


class State(TypedDict, total=False):
    """그래프 상태. LangGraph가 실행 중에 타입 힌트를 읽으므로, 순환 import가 생기는 두 칸은 Any로 둔다."""

    llm: Any  # LlmClient
    applicant: ApplicantDetail
    posting: PostingContent
    analysis: CandidateAnalysis
    review: Any  # ApplicationReview | None: 서류 전형 Agent의 상세 판정 (없으면 analysis 요약으로)
    interview: Any  # InterviewView (router.py에 있어 여기서 import하면 순환)
    focus: str
    final: bool  # 이전 면접 기록이 있으면 최종면접 (자리 5개 구성)
    company: CompanyProfile | None  # 회사 인재상 · 조직 문화 (없으면 None — 기준 없이 서류에서 찾음)
    slot_kept: dict[str, str]  # 최종면접 자리 → 통과한 질문
    follow_ups: list[Gap]
    existing: list[str]
    sentences: dict[str, str]
    gaps: list[Gap]
    spare: list[Gap]
    kept: dict[str, str]
    pick: str | None
    pick_sid: str | None
    errors: list[str]
    retry: int
    result: list[str]


_SPACES = re.compile(r"[\s\"'“”‘’.,!?·]+")
_INTERNAL = re.compile(r"\(?\b(?:G\d+|S\d+)\b\)?|\d+\s*점|점수|평가 결과|서류에 근거")
_SENTENCE = re.compile(r"\n+|(?<=[.!?])\s+")
# 학력 · 연락처 같은 인적 사항 줄은 질문 소재로 쓰지 않는다 (규칙 6의 취지)
_PERSONAL = re.compile(r"학교|대학|학력|생년|연락처|이메일|주소|전화")


def _normalize(text: str) -> str:
    return _SPACES.sub("", unicodedata.normalize("NFKC", text))


def _short(text: str, limit: int = 40) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _template_pieces() -> list[str]:
    """템플릿 질문의 고정 문장 조각 ("본인이 맡은 역할과 … 말해 주세요" 등). 길이가 긴 것부터."""
    pieces: set[str] = set()
    for template in TEMPLATES.values():
        for piece in re.split(r"\{\w+\}", template):
            piece = _normalize(piece)
            if len(piece) >= 4:
                pieces.add(piece)
    return sorted(pieces, key=len, reverse=True)


def _core(text: str) -> str:
    """중복 검사용 핵심 내용: 템플릿의 고정 조각을 지운 나머지.

    고정 조각까지 비교하면 주제가 다른 두 템플릿 질문도 '비슷함'으로 잘못 걸러진다.
    """
    text = _normalize(text)
    for piece in _template_pieces():
        text = text.replace(piece, "")
    return text


def _similar(a: str, b: str) -> bool:
    core_a, core_b = _core(a), _core(b)
    if len(core_a) >= 6 and len(core_b) >= 6:  # 핵심 내용이 충분히 남으면 핵심끼리 비교
        return difflib.SequenceMatcher(None, core_a, core_b).ratio() >= SIMILAR
    return difflib.SequenceMatcher(None, _normalize(a), _normalize(b)).ratio() >= SIMILAR


# ---------------------------------------------------------------- 노드
async def load_context(state: State) -> dict[str, Any]:
    """이전 면접 답변을 분석(FR-28)해 확인 안 된 질문을 모으고, 중복 검사용 질문과 지원 문서 문장을 준비한다."""
    interview = state["interview"]
    follow_ups: list[Gap] = []
    existing = [question.text for question in interview.questions]
    for previous in interview.previous:
        existing.extend(question.text for question in previous.questions)
        # 1분 자기소개는 확인할 경험을 묻는 질문이 아니라서 답변 분석 · 이어서 묻기에서 뺀다
        #   (빼지 않으면 최종면접 1차 미확인 자리에 "지난 면접에서 '1분 자기소개…' 질문에 답해 주셨는데…"가 나옴)
        asked = [question for question in previous.questions if "자기소개" not in question.text]
        if not any(question.answer.strip() for question in asked):
            continue
        findings = await analyze_answers(state["llm"], asked)
        for question, finding in zip(asked, findings, strict=True):
            if finding.status == CONFIRMED:
                continue
            follow_ups.append(
                Gap(
                    gap_id="",
                    kind=FOLLOW_UP,
                    topic=_short(question.text, 30),
                    note=f"{previous.stage_name} 답변 분석: {finding.status} — 아직 확인 안 된 점: "
                    + ", ".join(finding.unconfirmed),
                    evidence=[f"[{previous.stage_name} 질문] {question.text}", f"[답변] {question.answer or '(없음)'}"],
                    detail=finding.unconfirmed[0] if finding.unconfirmed else "본인 역할과 결과",
                    status=finding.status,
                )
            )
    sentences: dict[str, str] = {}
    for document in state["applicant"].documents:
        if document.type not in PICK_DOCUMENTS:
            continue
        for line in _SENTENCE.split(document.text):
            line = line.strip(" -·•\t")
            if (
                len(line) >= 8
                and not _PERSONAL.search(line)
                and not _document_header(line, state["applicant"].info.name)
            ):
                sentences[f"S{len(sentences) + 1}"] = line
    return {
        "final": bool(interview.previous),
        "slot_kept": {},
        "follow_ups": follow_ups,
        "existing": existing,
        "sentences": sentences,
        "kept": {},
        "pick": None,
        "pick_sid": None,
        "errors": [],
        "retry": 0,
    }


def find_gaps(state: State) -> dict[str, Any]:
    """빈틈을 코드로 고른다. 모든 지원자에게 같은 기준 · 같은 순서를 적용하기 위해서다.

    최종면접은 ① 1차 미확인 자리 하나만 코드가 고른다 (이전 면접에서 확인 안 된 질문 중 맨 앞).
    나머지 자리(인성 · 조직 적응 · 리더십 · 진정성)는 write에서 모델이 서류 문장을 골라 채운다.
    """
    if state.get("final"):
        gaps: list[Gap] = []
        for gap in state["follow_ups"][:1]:
            gap.gap_id = "G1"
            gaps.append(gap)
        return {"gaps": gaps, "spare": []}
    review = state.get("review")
    if review is not None and review.readable:
        candidates = list(state["follow_ups"]) + review_gaps(review)
    else:
        candidates = list(state["follow_ups"]) + summary_gaps(state["posting"], state["analysis"])

    focus = state.get("focus") or ""
    if "확인 안" in focus or "아직" in focus:
        candidates = [gap for gap in candidates if gap.kind in (FOLLOW_UP, REQUIRED, CHECK, CLAIM)]
    candidates.sort(key=lambda gap: gap.priority)  # 같은 순위는 만든 순서 유지
    gaps = []
    spare: list[Gap] = []
    seen: set[str] = set()
    for gap in candidates:
        if gap.evidence and all(_document_header(text, state["applicant"].info.name) for text in gap.evidence):
            continue
        key = _normalize(gap.topic)
        if key in seen:
            continue
        # 이미 물어본 주제는 빼되, 이전 면접에서 확인 안 된 질문은 일부러 이어서 묻는 것이므로 남긴다
        if gap.kind != FOLLOW_UP and any(_asked_before(gap, text) for text in state["existing"]):
            continue
        seen.add(key)
        gap.gap_id = f"G{len(gaps) + len(spare) + 1}"
        (gaps if len(gaps) < CODE_SLOTS else spare).append(gap)
    return {"gaps": gaps, "spare": spare}


def _document_header(text: str, name: str) -> bool:
    text = text.strip()
    return (
        bool(re.match(rf"^{re.escape(name)}\s*[|｜]", text))
        or text.startswith("SYNTHETIC SAMPLE")
        or bool(re.match(r"^(?:경력\s+)?지원\s*(?:직무|분야|구분)\s*[:：]?", text))
    )


def _asked_before(gap: Gap, question: str) -> bool:
    """이 빈틈을 이미 있는 질문이 물었는가.

    문장이 비슷하거나, 인용할 서류 문장과 같은 경험을 묻고 있으면 물은 것으로 본다.
    """
    if _similar(gap.topic, question):
        return True
    basis = gap.evidence[0] if gap.evidence else gap.topic
    return _same_topic(basis, question)


def summary_gaps(posting: PostingContent, analysis: CandidateAnalysis) -> list[Gap]:
    """요약(CandidateAnalysis)으로 빈틈 후보를 만든다. 상세 판정이 없을 때 (stub · 분석 전 · 저장소를 못 읽음)."""
    required = {_normalize(text) for text in posting.qualifications}
    preferred = {_normalize(text) for text in posting.preferred}
    candidates: list[Gap] = []
    unmet: list[str] = []
    for condition in analysis.conditions:
        if condition.met:
            continue
        key = _normalize(condition.requirement)
        kind = PREFERRED if key in preferred and key not in required else REQUIRED
        unmet.append(condition.requirement)
        note = f"공고 조건 [{condition.label}] 근거가 지원 자료에 없음"
        candidates.append(Gap("", kind, condition.requirement, note))
    for finding in analysis.checks:
        if any(_normalize(text) in _normalize(finding.text) for text in unmet):
            continue  # 충족 못 한 조건을 다시 말하는 확인 필요는 건너뛴다
        candidates.append(Gap("", CHECK, _short(finding.text), f"확인 필요 ({finding.source})", [finding.text]))
    for finding in analysis.notable:
        candidates.append(
            Gap(
                "",
                NOTABLE,
                _quote_part(finding.text),
                f"눈여겨볼 점 — 본인 역할 확인 ({finding.source})",
                [finding.text],
            )
        )
    return candidates


def review_gaps(review: ApplicationReview) -> list[Gap]:
    """서류 전형 Agent의 상세 판정(ApplicationReview)으로 빈틈 후보를 만든다 (데모의 15개 기준 판정과 같은 역할).

    - 필수 조건: 자격요건 판정이 met=false (차별 조건처럼 평가하지 않은 요건은 뺀다)
    - 확인 필요: 서류 전형 Agent가 남긴 확인 필요 메모
    - 우대 조건: 우대사항의 NCS 수행준거 중 근거 없음(NONE). 가중치가 큰 우대사항부터
    - 주장만 있음: 팀 성과로 적었거나(TEAM) 본인 역할이 불분명하거나(UNCLEAR) 근거가 주장을 받치지 못한 경험
    - 본인 역할 확인: 본인이 한 성과 · 프로젝트 · 경험. 인용은 요약 문장이 아니라 서류 원문 그대로
    """
    candidates: list[Gap] = []
    for result in review.qualifications:
        if result.met or not result.evaluated:
            continue
        note = f"자격 요건 근거 부족 — {result.shortfall or result.reason}"
        candidates.append(Gap("", REQUIRED, result.text, _short(note, 120)))
    for check in review.checks:
        candidates.append(Gap("", CHECK, _short(check.text), f"확인 필요 ({check.source})", [check.text]))
    # (줄여 쓰면) sorted(review.preferences, key=lambda p: -(p.weight or 0))
    ranked = sorted(review.preferences, key=lambda preference: -(preference.weight or 0))
    for preference in ranked:
        if preference.status != PreferenceStatus.SCORED:
            continue  # 평가 기준(가중치 · NCS)이 없는 우대사항은 판정이 없다
        missing = []
        for criterion in preference.criteria:
            if criterion.level == Level.NONE:
                missing.append(criterion.content)
        if not missing:
            continue
        unit = preference.unit_name or "NCS"
        note = f"NCS '{unit}' 수행준거 근거 없음: " + " / ".join(
            _short(content, 60) for content in missing[:NCS_PER_PREFERENCE]
        )
        candidates.append(Gap("", PREFERRED, preference.text, note))
    claims = 0
    for fact in review.facts:
        if fact.kind not in CLAIM_FACT_KINDS or not fact.quotes or claims >= CLAIM_LIMIT:
            continue
        if fact.actor == Actor.TEAM:
            reason = "팀 · 조직의 성과로 적음 — 본인이 한 부분 확인"
        elif fact.actor == Actor.UNCLEAR:
            reason = "본인 역할이 불분명함 — 본인이 한 부분 확인"
        elif not fact.supported:
            reason = "근거 문장이 주장을 충분히 받치지 못함 — 실제로 한 일 확인"
        else:
            continue
        sentence = fact.quotes[0].sentence
        candidates.append(
            Gap(
                "", CLAIM, _quote_part(sentence), f"주장만 있음 ({fact.quotes[0].document.label}): {reason}", [sentence]
            )
        )
        claims += 1
    for fact in notable_facts(review.facts):
        quote = fact.quotes[0]
        candidates.append(
            Gap(
                "",
                NOTABLE,
                _quote_part(quote.sentence),
                f"눈여겨볼 점 — 본인 역할 확인 ({quote.document.label})",
                [quote.sentence],
            )
        )
    return candidates


async def write(state: State) -> dict[str, Any]:
    """모델에게 빈틈 질문과 free_pick 질문을 한 번에 쓰게 한다."""
    gaps = [gap for gap in state["gaps"] if gap.gap_id not in state["kept"]]
    avoid = [
        sid
        for sid, text in state["sentences"].items()
        if any(text in line for gap in state["gaps"] for line in gap.evidence)
    ]
    lines = []
    for gap in gaps:
        lines.append(
            f"- gap_id: {gap.gap_id} | type: {gap.label} | topic: {gap.topic} | note: {gap.note}"
            + (f" | still_unconfirmed: {gap.detail}" if gap.kind == FOLLOW_UP else "")
        )
        for evidence in gap.evidence:
            lines.append("  " + data_block("evidence", evidence))
    numbered = "\n".join(f"{sid} {text}" for sid, text in state["sentences"].items())
    final = bool(state.get("final"))
    # free_pick: 1차는 늘, 최종면접은 ① 1차 미확인 자리를 이전 면접 기록으로 못 채울 때만 (모델이 서류에서 골라 채움)
    want_pick = state["pick"] is None and bool(state["sentences"]) and not (final and state["gaps"])
    slots = [key for key in FINAL_SLOTS if key not in state.get("slot_kept", {})] if final else []
    # (줄여 쓰면) slot_lines = [f"- {key} ({…label}): {…hint}" for key in slots]
    slot_lines = []
    for key in slots:
        slot_lines.append(f"- {key} ({FINAL_SLOTS[key].label}): {FINAL_SLOTS[key].hint}")
    company = state.get("company")
    if slots and company is not None:
        # 회사 정보도 HR이 입력한 글이라 자료 블록으로 감싼다 (안의 지시문을 따르지 않게)
        talents = "\n".join(f"- {talent.title}: {talent.description}" for talent in company.talents)
        if talents.strip():
            slot_lines.append("company_talents:")
            slot_lines.append(data_block("company_talents", talents))
        if company.culture.strip():
            slot_lines.append("company_culture:")
            slot_lines.append(data_block("company_culture", company.culture.strip()))
    user = "\n".join(
        [
            "gaps:",
            *(lines or ["(없음)"]),
            "",
            "free_pick: " + ("요청함" if want_pick else "요청하지 않음 (free_pick은 null)"),
            "slot_picks: " + ("요청함" if slots else "요청하지 않음 (slot_picks는 빈 목록)"),
            *slot_lines,
            "sentences:",
            data_block("documents", numbered),
            "avoid_sids: " + (", ".join(avoid) or "-"),
            "existing_questions:",
            *[f"- {text}" for text in state["existing"] + list(state["kept"].values())],
            "hr_focus: " + (state.get("focus") or "-"),
            "fix_errors: " + (" / ".join(state["errors"]) or "-"),
        ]
    )
    draft = await state["llm"].structured(QuestionDraft, agent=AGENT_KEY, system=SYSTEM, user=user)
    return _validate(state, draft, avoid, want_pick, slots)


# 질문 문장 스타일 검사. 7.8B 모델로 실제 생성해 보니 한 질문에 2~3개를 묻거나, 면접에서 말한 적 없는 것을
# "이전에 언급한"으로 전제하거나, "경력이 부족합니다" 같은 내부 판단을 지원자에게 말하는 일이 잦았다.
STYLE_MAX_LENGTH = 140
# '특히 · 또한'은 앞 질문 뒤에 새 문장으로 붙을 때만 두 번째 질문이다.
# 한 문장 안의 강조("…중 특히 기억에 남는")는 괜찮다.
_ADD_ON = re.compile(r"^(?:특히|또한|아울러)\s*,?\s*")
_SENTENCE_END = re.compile(r"(?<=[.?!])\s+")
_ASK_SENTENCE = re.compile(r"\?$|(?:주세요|주십시오|주시겠어요|바랍니다)\.?$")
_REFERS_BACK = re.compile(
    r"(?:^|\s)(?:이|해당|이러한|이런|이와|이를|위의|앞의)\s|^(?:그|그런|그러한|관련|비슷한|유사한|어떤|어떻게|무엇|왜)\s"
)
# 경험이 아니라 지식 · 의견만 묻는 질문 ("…설계 시 고려해야 할 주요 요소들을 설명해 주세요")
_KNOWLEDGE = re.compile(
    r"고려해야\s*(?:할|하는)|중요하다고\s*생각|무엇이라고\s*생각|어떻게\s*생각하시|일반적으로|차이(?:점)?(?:은|를|이)\b|장단점|"
    r"수\s*있을지|제안해\s*주|한다면|라면\s*어떻게|상상해|했을지|하셨을지"
)
_DID_IT = re.compile(r"했|하셨|셨|었|였|던|해\s*본|해\s*보신|사례|당시|그때|맡")
_LEAD_WORDS = re.compile(r"^(?:예를\s*들어|만약|그렇다면)\s*,?\s*")
MIN_TRIMMED_LENGTH = 35
_ASK_AGAIN = re.compile(r"(?:말씀|설명|말)해\s*주(?:세요|십시오|시겠)")
_PRESUME = re.compile(
    r"(?:이전에|앞서|아까)\s*(?:언급|말씀)|언급하신|말씀하신|언급하셨|말씀하셨|"
    r"말씀해 주신|말씀해 주셨|말씀이셨|말씀이었"
)
_JUDGMENT = re.compile(
    r"부족(?:합니다|하신|한|해|하다)|\d+\s*년\s*이상|우대\s*조건|조건에\s*부합|미충족|충족하지|요구(?:하는|되는|되었|하고)|공고에서|"
    r"\d+\s*년(?:으로|입니다|이라|밖에)|낮게 나왔|낮은 편|상대적으로 낮|평가가 낮|"
    r"명시(?:되어|돼)\s*있지\s*않|(?:나와|적혀|기재되어|드러나)\s*있지\s*않|확인되지\s*않|근거가\s*없|"
    r"언급(?:해\s*주시지|하시지|하지|되지)\s*않|적어\s*주시지\s*않|적지\s*않으셨|"
    r"(?:경험|이력)(?:은|이)\s*(?:없지만|없으시지만|없으신데|없는데)"
)
# 실제로 하지 않은 일을 상상하게 하는 질문. 경험을 묻는 말('…한 경험을 바탕으로')이 있어도 막는다.
# 예) "…습관을 어떻게 조직 문화에 맞게 발전시킬 수 있을지", "…어떻게 기여할 수 있다고 생각하시나요?"
_HYPOTHETICAL = re.compile(
    r"상상해|했을지|하셨을지|하실지|수\s*있을지|수\s*있다고\s*생각|제안해\s*주|라면\s*어떻게|한다면"
)
# 프롬프트 지시를 지원자에게 그대로 말함: "지원 동기 문장 '…'를 인용해 보세요."
_INSTRUCTION = re.compile(r"인용해\s*(?:보세요|주세요|주십시오)|인용하(?:여|고)\s")
# 서류 내용을 '말씀하셨는데'라고 씀 (면접 전이라 말한 적이 없음) → '적어 주셨는데'로 바꿔 살린다
_SAID = re.compile(r"(다고|라고)\s*(?:말씀|언급)하셨(는데|습니다)")
_YES_NO_END = re.compile(r"(?:있으신가요|있으셨나요|있나요|있습니까|있으십니까|하셨나요|하신 적이 있나요)\?\s*$")
_OPEN_ASK = re.compile(r"어떻게|무엇|어떤|왜|어디|얼마나|설명|말씀|들려|이야기|구체적|공유")
_OPEN_WORDS = ("있다면", "있으신", "있으셨", "해 보신", "해보신", "있는지", "경험이 있")
_LEFTOVER = re.compile(r"\[(?:이력서|자기소개서|S\d+)\]\s*|^\s*S\d+\s*[:：]\s*")
# 실제 모델 결과에서 '질문이 김'으로 버려진 문장 대부분은 내용이 아니라 군더더기 때문에 길었다.
_LEAD_IN = re.compile(r"^[^'\"]{0,25}?(?:경험|과정)\s*(?:중에서|을\s*바탕으로|에서)\s*,\s*(?=['\"])")
# '구체적인 사례를 들어'는 '…했는지 ' 뒤에서만 지운다. 그 밖엔 '사례'가 목적어라 지우면 문장이 깨진다.
_FILLER = re.compile(
    r"(?<=지\s)구체적인\s*사례(?:와\s*함께|를\s*들어)\s+(?=(?:자세히\s+)?(?:설명|말씀))|(?<=\s)자세히\s+(?=설명|말씀)"
)
_LONG_ENDING = re.compile(
    r"(?:구체적으로\s*)?(?:설명|말씀|공유)해\s*주(?:실\s*수\s*있(?:을까요|나요|겠습니까|으신가요)|시겠습니까|시겠어요)\?$"
)
_QUOTE = re.compile(r"'([^']{10,})'")
_NUMBER = re.compile(r"\d{3,}")


_CLAUSE_END = re.compile(r"(?<=[고며데만나서]),\s*")
_QUOTE_LEAD = re.compile(r"^(?:저는|제가|또한|또|그리고|특히|그래서|따라서|한편|다만|이후|당시|그\s*결과)\s+")
_ROLE = re.compile(r"직접|담당(?!자)|주도|설계|만들|리드|맡았|맡아")
QUOTE_LIMIT = 60


def _quote_part(text: str) -> str:
    """질문에 인용할 부분: 본인이 한 일이 적힌 마지막 절을 고르고, 낱말 중간에서 자르지 않는다.

    예) "…알림이 늦게 도착하는 문제가 있었고, 저는 … 큐 기반 비동기 구조로 바꾸는 작업을 직접 설계했습니다."
        앞에서 글자 수로 자르면 '…도착하는 문제…'만 남아 '문제'에서 맡은 역할을 묻는 이상한 질문이 된다.
        → 마지막 절 "동기 호출로 … 직접 설계했습니다"를 인용한다.
    """
    chosen = text.strip()
    clauses = _CLAUSE_END.split(chosen)
    last = clauses[-1].strip()
    if len(clauses) > 1 and (last.startswith(("저는", "제가")) or _ROLE.search(last)):
        chosen = last
    chosen = _QUOTE_LEAD.sub("", chosen).rstrip(".").replace("'", '"')
    if len(chosen) > QUOTE_LIMIT:
        cut = chosen[:QUOTE_LIMIT]
        cut = cut[: cut.rfind(" ")] if " " in cut else cut
        chosen = cut.rstrip(" ,") + "…"
    return chosen


def _clean(text: str) -> str:
    """모델이 질문에 남긴 출처 표시('[자기소개서]', 'S3:')와 인용 앞 목록 번호("'01 이체…")를 지운다.

    '[이력서]에 Java…'처럼 뒤에 조사가 붙으면 괄호만 뗀다 (통째로 지우면 '에 Java…'로 시작하는 문장이 된다).
    """
    text = re.sub(r"\[(자기소개서|이력서)\](?=(?:에서|에|의|을|를|과|와)\s)", r"\1", text)
    text = re.sub(r"'(?:0?\d|[①-⑳])[.)]?\s+(?=[가-힣A-Za-z])", "'", text)
    text = re.sub(r"\s+([,.?])", r"\1", re.sub(r"\(\s*\)", "", _LEFTOVER.sub("", text)))
    return re.sub(r"\s{2,}", " ", text).strip()


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_END.split(text.strip()) if part.strip()]


def _is_ask(sentence: str) -> bool:
    """'?'나 '…주세요.'로 끝나는 묻는 문장인지. '…담당하셨습니다.' 같은 설명 문장은 False."""
    return bool(_ASK_SENTENCE.search(sentence.strip()))


def _shorten(text: str) -> str:
    """뜻은 그대로 두고 군더더기를 덜어 낸다.

    앞머리: "서버 프로그램 구현 경험 중에서, '…'" → "'…'"
    채움말: '구체적인 사례를 들어 ', '자세히 설명' → 빼거나 '설명'
    끝맺음: '…설명해 주실 수 있을까요?' → '…말해 주세요.', '…경험이 있으신가요?' → '…경험이 있다면 말해 주세요.'
    """
    text = re.sub(r"(다\.)\s+(?:특히|또한)\s*,?\s*", r"\1 ", _LEAD_IN.sub("", text))
    text = _LONG_ENDING.sub("말해 주세요.", _FILLER.sub("", text))
    # '…들어주시겠어요?' → '…말해 주세요.' / '…경험이 있으신가요?' → '…경험이 있다면 말해 주세요.'
    text = re.sub(r"들어\s*주시겠(?:어요|습니까)\?$", "말해 주세요.", text)
    text = re.sub(r"(?<=경험)이\s*있으(?:신가요|셨나요|십니까)\?$", "이 있다면 말해 주세요.", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _same_fact(a: str, b: str) -> bool:
    """두 인용 문장이 같은 내용인지. 앞 15글자가 겹치거나, 세 자리 이상 숫자가 2개 이상 같으면 같은 성과로 본다."""
    left, right = _normalize(a), _normalize(b)
    if left[:15] in right or right[:15] in left:
        return True
    return len(set(_NUMBER.findall(left)) & set(_NUMBER.findall(right))) >= 2


def _quotes_repeated(text: str, others: list[str]) -> bool:
    """이 질문이 인용한 서류 문장을 다른 질문이 이미 인용했는지 본다."""
    for mine in _QUOTE.findall(text):
        for other in others:
            if any(_same_fact(mine, theirs) for theirs in _QUOTE.findall(other)):
                return True
    return False


# 질문마다 늘 나오는 말 — '같은 경험인지' 비교할 때는 뺀다
_QUESTION_WORDS = frozenset(
    {
        "구체적인",
        "구체적으로",
        "과정",
        "어떤",
        "어떻게",
        "말해",
        "주세요",
        "설명해",
        "경험",
        "그리고",
        "결과",
        "있다면",
        "해당",
        "특히",
        "무엇",
        "영향",
        "미쳤는지",
        "했는지",
        "겪었는지",
        "사용했는지",
        "이력서",
        "서류",
        "적어",
        "주셨는데",
        "언급된",
        "프로젝트",
        "시스템",
        "서비스",
        "기술적",
        "도전",
        "과제",
        "문제",
        "해결",
        "해결했는지",
        "방법",
        "본인",
        "직접",
        "맡은",
        "부분",
        "이러한",
        "위해",
        "통해",
        "가장",
        "어려웠던",
        "기술",
        "적용",
        "구현",
        "개발",
        "성능",
        "개선",
        "활용해",
        "활용하여",
        "데이터",
        "서버",
        "프로그램",
        "입출력",
        "테스트",
        "효율성",
        "변화",
        "성과",
        "무엇이었는지",
        "사례",
        "함께",
        "바탕으로",
        "말씀해",
        "접근법",
        "역할",
    }
)
_TOPIC_PARTICLE = re.compile(
    r"(?:으로|에서|에게|까지|부터|처럼|보다|이나|이라|하고|했고|하며|하여|을|를|이|가|은|는|에|의|로|와|과|도|만)$"
)


def _words(text: str) -> list[str]:
    """낱말을 뽑아 끝의 조사를 뗀다. 예) '구조로 바꾸는' → ['구조', '바꾸는']"""
    found = []
    for word in re.findall(r"[A-Za-z][A-Za-z0-9+#]*|[가-힣]{2,}|\d[\d,]*", text.replace("'", " ")):
        word = _TOPIC_PARTICLE.sub("", word).lower()
        if len(word) >= 2:
            found.append(word)
    return found


_TEMPLATE_WORDS = frozenset(
    word for template in TEMPLATES.values() for word in _words(re.sub(r"\{\w+\}", " ", template))
)


def _same_topic(a: str, b: str) -> bool:
    """두 질문이 같은 경험을 묻는지: 경험 낱말이 4개 이상, 짧은 쪽의 절반 이상 겹치면 같은 경험.

    예) '알림 발송 시스템을 동기 호출에서 큐 기반 비동기 구조로 변경한 …' / '…동기 호출 방식에서 큐 기반 비동기 구조로
        전환한 경험이 있다면 …' → 7개 · 78% 겹침. 가상 지원자 21명 결과에서 다음으로 높은 쌍은 45%였다.
    """
    skip = _QUESTION_WORDS | _TEMPLATE_WORDS
    left = {word for word in _words(a) if word not in skip}
    right = {word for word in _words(b) if word not in skip}
    shared = left & right
    smaller = min(len(left), len(right))
    return smaller > 0 and len(shared) >= 4 and len(shared) / smaller >= 0.5


def _style_problem(text: str, kind: str) -> str | None:
    """모델이 쓴 질문의 문장 스타일 문제. 템플릿에는 쓰지 않는다. kind는 빈틈 종류(FOLLOW_UP 등)."""
    if text.count("?") >= 2:
        return "한 질문에 두 가지 이상을 물음 (하나만)"
    asks = 0
    for index, sentence in enumerate(_sentences(text)):
        if index > 0 and asks > 0 and _ADD_ON.match(sentence):
            return "한 질문에 두 가지 이상을 물음 (하나만)"
        asks += _is_ask(sentence)
    if asks >= 2 or re.search(r"(?:설명|말씀|말)해\s*주시고", text):
        return "한 질문에 두 가지 이상을 물음 (하나만)"
    if text.count("'") % 2 == 1:
        return "인용 따옴표가 짝이 맞지 않음"
    for quoted in re.findall(r"'([^']+)'", text):
        tech_list = " / " in quoted and re.fullmatch(r"[A-Za-z0-9 ./+#()-]+", quoted)
        if quoted.startswith("[") or quoted.rstrip(" .").endswith("하기") or quoted.count(",") >= 3 or tech_list:
            return "평가 기준 이름이나 기술 목록 줄을 인용함 (본인이 한 일이 적힌 문장만)"
    after = text.split("?", 1)[1] if "?" in text else ""
    if _ASK_AGAIN.search(after):
        return "물음표 뒤에 한 번 더 물음 (하나만)"
    if len(text) > STYLE_MAX_LENGTH:
        return f"질문이 김 ({len(text)}자, {STYLE_MAX_LENGTH}자 이내)"
    if _YES_NO_END.search(text) and not _OPEN_ASK.search(text):
        return "예/아니오로 끝나는 질문 (경험을 열어서)"
    if kind != FOLLOW_UP and _PRESUME.search(text):
        return "면접에서 아직 말하지 않은 것을 전제함 ('이전에 언급한')"
    if re.match(r"^구체적으로\s", text):
        return "무엇에 대한 질문인지 빠짐 ('구체적으로 어떤 …'으로 시작)"
    if kind not in FINAL_SLOTS and _KNOWLEDGE.search(text) and not _DID_IT.search(re.sub(r"'[^']*'", "", text)):
        return "경험이 아니라 지식 · 의견만 물음 (지원자가 실제로 한 일을)"
    if _JUDGMENT.search(text):
        return "내부 판단(경력 부족 · 요건 · 낮은 평가)을 지원자에게 말함"
    if _HYPOTHETICAL.search(re.sub(r"'[^']*'", "", text)):
        return "가정 · 상상으로 물음 ('…할 수 있을지') — 실제로 한 일을"
    if _INSTRUCTION.search(text):
        return "프롬프트 지시('인용해 보세요')를 지원자에게 말함"
    if kind in (REQUIRED, PREFERRED) and not any(word in text for word in _OPEN_WORDS):
        return "근거 없는 조건인데 경험이 있다고 전제함 ('~경험이 있다면')"
    return None


def _trimmed_versions(text: str) -> list[str]:
    """걸린 질문을 잘라서 살릴 후보. ① 첫 질문 문장까지 ② 앞 설명 문장을 뺀 첫 질문 ③ '특히'로 시작한 질문.

    ②③은 앞 문장을 버리므로 '이 · 해당 · 관련'처럼 앞을 가리키는 말이 남으면 쓰지 않는다.
    예) "점수가 다소 낮게 나왔습니다. 특히, 보안 테스트 사례를 들어 주시겠어요? 이를 통해 …"
        → "보안 테스트 사례를 들어 주시겠어요?"
    """
    parts = _sentences(text)
    found: list[str] = []

    def add(chosen: list[str], check_reference: bool) -> None:
        candidate = " ".join(chosen).strip()
        if check_reference:
            candidate = _LEAD_WORDS.sub("", candidate)
            if _REFERS_BACK.search(candidate):
                return
        if len(candidate) >= MIN_TRIMMED_LENGTH and candidate != text.strip() and candidate not in found:
            found.append(candidate)

    first_ask = next((index for index, sentence in enumerate(parts) if _is_ask(sentence)), None)
    if first_ask is not None:
        add(parts[: first_ask + 1], False)
        if first_ask > 0:
            add([parts[first_ask]], True)
    for index, sentence in enumerate(parts):
        if index > 0 and _ADD_ON.match(sentence) and _is_ask(sentence):
            add([_ADD_ON.sub("", sentence)], True)
    return found


_GENERIC_WORDS = {
    "경험",
    "과정",
    "구현",
    "개발",
    "서버",
    "프로그램",
    "성능",
    "개선",
    "최적화",
    "테스트",
    "데이터",
    "시스템",
    "서비스",
    "프로젝트",
    "기술",
    "문제",
    "해결",
    "결과",
    "업무",
    "관리",
    "처리",
    "기능",
    "설계",
    "운영",
    "담당",
    "역할",
    "직접",
    "사용",
    "적용",
    "통해",
    "위해",
    "대한",
    "모듈",
    "공통",
    "배치",
    "환경",
    "구축",
    "백엔드",
    "api",
    "저는",
    "제가",
}
_PARTICLE_END = re.compile(
    r"(?:으로|에서|에게|까지|부터|처럼|보다|이나|이라|하고|했고|하며|하여|했습니다|합니다|입니다|"
    r"을|를|이|가|은|는|에|의|로|와|과|도|만)$"
)


def _grounding_problem(text: str, evidence: list[str]) -> str | None:
    """근거 문장이 있는 빈틈인데 질문이 근거와 낱말 하나도 겹치지 않으면(평가 항목만 늘어놓은 일반 질문) 문제."""
    words: set[str] = set()
    for sentence in evidence:
        for word in re.findall(r"[A-Za-z][A-Za-z0-9+#]*|[가-힣]{2,}|\d[\d,]*", sentence):
            word = _PARTICLE_END.sub("", word).replace(",", "").lower()
            if len(word) >= 2 and word not in _GENERIC_WORDS:
                words.add(word)
    flat = text.replace(",", "").lower()
    if words and not any(word in flat for word in words):
        return "근거 문장과 이어지지 않는 일반적인 질문 (서류에 적힌 경험을 가리켜서)"
    return None


def _checked(
    text: str, kind: str, others: list[str], evidence: list[str] | None = None
) -> tuple[str | None, str | None]:
    """검사하고, 걸리면 잘라서 한 번 더 본다. 반환: (쓸 질문 또는 None, 걸린 이유 또는 None).

    evidence: 확인 필요 · 본인 역할 확인 빈틈의 근거 문장. 주면 질문이 그 문장과 이어지는지도 본다.
    """

    def problem_of(candidate: str) -> str | None:
        found = _problem(candidate, others) or _style_problem(candidate, kind)
        # 이전 면접 질문을 이어서 묻는 FOLLOW_UP 은 원래 같은 경험을 묻는 자리라 보지 않는다
        if found is None and kind != FOLLOW_UP and any(_same_topic(candidate, other) for other in others):
            found = "다른 질문과 같은 경험을 다시 물음 (서류의 다른 경험을)"
        if found is None and evidence:
            found = _grounding_problem(candidate, evidence)
        return found

    text = _clean(text)
    if kind != FOLLOW_UP:
        text = _SAID.sub(r"\1 적어 주셨\2", text)
    text = _shorten(text)
    problem = problem_of(text)
    if problem is None:
        return text, None
    for part in _trimmed_versions(text):
        part = _shorten(part)
        if len(part) >= MIN_TRIMMED_LENGTH and problem_of(part) is None:
            return part, None
    return None, problem


def _problem(text: str, others: list[str]) -> str | None:
    if not text or len(text) < 5:
        return "질문이 비어 있음"
    blocked = blocked_attribute(text)
    if blocked:
        return f"직무와 무관한 조건 '{blocked}'"
    if _INTERNAL.search(text):
        return "내부 번호 · 점수 · 판단을 질문에 드러냄"
    if len(text) > MAX_QUESTION_LENGTH:
        return f"질문이 너무 김 ({len(text)}자)"
    if any(_similar(text, other) for other in others):
        return "이미 있는 질문과 비슷함"
    head = _normalize(text)[:20]
    if len(head) == 20 and not text.startswith("'") and any(_normalize(other)[:20] == head for other in others):
        return "다른 질문과 같은 말로 시작함 (같은 경험을 두 번)"
    if _quotes_repeated(text, others):
        return "다른 질문이 이미 인용한 서류 문장을 또 인용함"
    return None


def _resolve_gap_id(raw: str, gaps: list[Gap], open_ids: set[str]) -> str | None:
    """모델이 쓴 gap_id를 실제 빈틈 번호로 맞춘다. 못 맞추면 None.

    작은 모델은 번호 대신 '확인 필요 (서버 프로그램 구현)'처럼 빈틈 이름을 쓰기도 한다.
    이름이 맞는 열린 빈틈이 하나뿐이면 그것으로 보고, 여러 개면 topic까지 들어 있는 것으로 좁힌다.
    """
    raw = raw.strip()
    if raw in open_ids:
        return raw
    name = re.sub(r"\s*\(.*?\)\s*", "", raw).strip()
    open_gaps = [gap for gap in gaps if gap.gap_id in open_ids]
    same = [gap for gap in open_gaps if gap.label == name] or [
        gap for gap in open_gaps if name and (name in gap.label or gap.label in name)
    ]
    if len(same) > 1:
        same = [gap for gap in same if gap.topic and gap.topic in raw]
    return same[0].gap_id if len(same) == 1 else None


def _compare_with(state: State, kind: str) -> list[str]:
    """중복 검사에 쓸 기존 질문. 1차 미확인(FOLLOW_UP)은 이번 카드 질문하고만 비교한다.

    이어서 묻기는 일부러 1차 질문을 다시 짚는 질문이라("지난 면접에서 '…' 질문에 답해 주셨는데"),
    1차 질문과 비교하면 늘 '비슷함'으로 걸려 최종면접 ① 자리가 빠진다.
    """
    if kind == FOLLOW_UP:
        return [question.text for question in state["interview"].questions]
    return state["existing"]


def _validate(
    state: State, draft: QuestionDraft, avoid: list[str], want_pick: bool, slots: list[str] | None = None
) -> dict[str, Any]:
    """모델이 쓴 질문을 코드로 검사한다. 통과한 것만 kept · pick에 넣는다."""
    kept = dict(state["kept"])
    errors: list[str] = []
    kinds = {gap.gap_id: gap.kind for gap in state["gaps"]}
    open_ids = {gap.gap_id for gap in state["gaps"] if gap.gap_id not in kept}
    for item in draft.questions:
        gap_id = _resolve_gap_id(item.gap_id, state["gaps"], open_ids)
        if gap_id is None:
            errors.append(f"없는 gap_id 또는 중복 '{item.gap_id}'")
            continue
        gap = next(gap for gap in state["gaps"] if gap.gap_id == gap_id)
        evidence = gap.evidence if gap.kind in QUOTED_KINDS else None
        text, problem = _checked(
            item.question.strip(), kinds[gap_id], _compare_with(state, kinds[gap_id]) + list(kept.values()), evidence
        )
        if text is None:
            errors.append(f"{gap_id}: {problem}")
            continue
        kept[gap_id] = text
        open_ids.discard(gap_id)
    pick, pick_sid = state["pick"], state["pick_sid"]
    if want_pick:
        if draft.free_pick is None:
            errors.append("free_pick이 없음")
        else:
            sid = draft.free_pick.sid.strip().upper()
            sentence = state["sentences"].get(sid)
            checked, problem = _checked(
                draft.free_pick.question.strip(), "PICK", state["existing"] + list(kept.values())
            )
            if sentence is None or sid in avoid:
                errors.append(f"free_pick: 쓸 수 없는 문장 번호 '{sid}'")
            elif evidence_source(sentence, state["applicant"].documents) is None:
                errors.append("free_pick: 지원 문서에 없는 문장")
            elif checked is None:
                errors.append(f"free_pick: {problem}")
            else:
                pick, pick_sid = checked, sid
    slot_kept = dict(state.get("slot_kept", {}))
    for slot_pick in draft.slot_picks:
        key = slot_pick.slot.strip().upper()
        if key not in (slots or []) or key in slot_kept:
            continue  # 요청하지 않은 자리 · 이미 채운 자리
        sentence = state["sentences"].get((slot_pick.sid or "").strip().upper()) if slot_pick.sid else None
        if slot_pick.sid and sentence is None:
            errors.append(f"{key}: 쓸 수 없는 문장 번호 '{slot_pick.sid}'")
            continue
        others = state["existing"] + list(kept.values()) + list(slot_kept.values()) + ([pick] if pick else [])
        checked, problem = _checked(slot_pick.question.strip(), key, others, [sentence] if sentence else None)
        if checked is None:
            errors.append(f"{key}: {problem}")
        elif not FINAL_SLOTS[key].topic.search(checked) and not _names_talent(checked, state.get("company")):
            errors.append(f"{key}: '{FINAL_SLOTS[key].label}' 자리인데 그 주제를 묻지 않음")
        else:
            slot_kept[key] = checked
    return {"kept": kept, "pick": pick, "pick_sid": pick_sid, "errors": errors, "slot_kept": slot_kept}


def route_after_gaps(state: State) -> str:
    # 최종면접은 서류 문장이 없어도 자리 질문(열린 질문)을 모델이 쓸 수 있으므로 write로 간다
    return "write" if state["gaps"] or state["sentences"] or state.get("final") else "finalize"


def route_after_write(state: State) -> str:
    pick_done = state["pick"] is not None or not state["sentences"] or (state.get("final") and bool(state["gaps"]))
    slots_done = not state.get("final") or len(state.get("slot_kept", {})) >= len(FINAL_SLOTS)
    done = len(state["kept"]) >= len(state["gaps"]) and pick_done and slots_done
    if done or state["retry"] >= MAX_RETRY:
        return "finalize"
    return "retry"


def bump_retry(state: State) -> dict[str, Any]:
    return {"retry": state["retry"] + 1}


def _names_talent(question: str, company: CompanyProfile | None) -> bool:
    """질문이 회사 인재상 이름을 그대로 말하는지 ('함께 성장'처럼 주제 낱말 목록에 없는 인재상도 인정하려고)."""
    if company is None:
        return False
    # 풀어 쓰면: 인재상마다 → 이름이 비어 있지 않고 질문 안에 그 이름이 있으면 True, 하나도 없으면 False
    flat = _normalize(question)
    return any(talent.title.strip() and _normalize(talent.title) in flat for talent in company.talents)


def _slot_fallback(key: str, company: CompanyProfile | None) -> str:
    """자리 질문을 못 채웠을 때의 기본 질문. 회사 정보가 있으면 인재상 · 조직 문화를 넣어 묻는다.

    예) 인재상 '고객 신뢰를 최우선으로' → "'고객 신뢰를 최우선으로'와 관련해 기억에 남는 경험을 하나 골라, …"
    """
    if company is not None and key == VALUES:
        titles = [talent.title.strip() for talent in company.talents if talent.title.strip()]
        if titles:
            question = (
                f"'{titles[0]}'와 관련해 기억에 남는 경험을 하나 골라, 그때 본인이 한 선택과 그 이유를 말해 주세요."
            )
            return _fix_josa(question)
    if company is not None and key == CULTURE and company.culture.strip():
        culture = _short(company.culture.strip().rstrip("."), 40)
        return (
            f"저희는 '{culture}'라는 방식으로 일하는데, 이와 비슷하게 일해 본 경험이나 맞지 않았던 경험과 "
            "그때 어떻게 했는지 말해 주세요."
        )
    return FINAL_SLOTS[key].fallback


def finalize(state: State) -> dict[str, Any]:
    """통과 못 한 빈틈은 템플릿으로 채워 순서대로 돌려준다. 맨 앞에는 1분 자기소개를 넣는다.

    1차   : 자기소개 + 빈틈 2개(우선순위 순) + 이 사람만의 확인 포인트(실패하면 다음 순위 빈틈)
    최종면접: 자기소개 + ① 1차 미확인(없으면 모델이 고른 문장, 그것도 없으면 기본 질문)
            + ②~⑤ 자리 질문(없으면 자리별 기본 질문)
    """
    questions: list[str] = []
    follow_up = ""  # 최종면접 ① 1차 미확인 질문 (중복 검사를 이번 카드 질문하고만 한다)
    if state.get("final"):
        if state["gaps"]:
            gap = state["gaps"][0]
            follow_up = state["kept"].get(gap.gap_id) or _template(gap)
            questions.append(follow_up)
        else:
            questions.append(state["pick"] or PICK_FALLBACK)
        for key in FINAL_SLOTS:
            questions.append(state.get("slot_kept", {}).get(key) or _slot_fallback(key, state.get("company")))
        limit = 1 + len(FINAL_SLOTS)
    else:
        for gap in state["gaps"]:
            questions.append(state["kept"].get(gap.gap_id) or _template(gap))
        if state["pick"]:
            questions.append(state["pick"])
        elif state["spare"]:
            questions.append(_template(state["spare"][0]))
        limit = MAX_QUESTIONS
    result: list[str] = []
    for text in questions:
        others = _compare_with(state, FOLLOW_UP) if text == follow_up else state["existing"]
        if not text or any(_similar(text, other) for other in others + result):
            continue
        # 같은 서류 경험을 다시 묻는 질문은 뺀다 (예: 자동 생성으로 이미 물은 경험을 AI Chat 요청이 템플릿으로 또 물음)
        if text != follow_up and any(_same_topic(text, other) for other in others + result):
            continue
        result.append(text)
    result = result[:limit]
    # 이번 전형 카드에 자기소개가 이미 있으면(면접관이 직접 넣음 등) 다시 넣지 않는다
    #   이전 면접의 자기소개는 보지 않는다 (최종면접에서도 처음에 다시 묻는다)
    if not any("자기소개" in question.text for question in state["interview"].questions):
        result.insert(0, INTRO)
    return {"result": result}


_ACTION_END = re.compile(
    r"(?:개발|개선|수정|정리|구현|설계|도입|전환|감소|단축|분석|작성|구축|처리|적용|최적화|자동화|연동|"
    r"운영|담당|유지보수|해결|추가|제거|검증|관리|고도화|이관|교체|축소|확대)$"
)


def _title(quote: str) -> str | None:
    """인용할 부분이 프로젝트 · 업무 '이름'뿐이면 다듬은 이름을, 문장이면 None을 돌려준다.

    예) '팀 프로젝트 - 중고거래 웹 서비스 (백엔드 담당)' → '중고거래 웹 서비스'
        '쿠폰 중복 사용 버그 원인 분석 및 수정', '조회 API 4개 개발' → None (한 일 · 숫자가 있음)
    """
    text = re.sub(r"\s*\([^)]*\)\s*$", "", quote.rstrip("…").strip())
    if not text or len(text) > 30 or re.search(r"\d", text) or re.search(r"[다요]\.?$|[음함됨임춤줌]$", text):
        return None
    if _ACTION_END.search(text):
        return None
    return re.sub(r"^.*?프로젝트\s*[-–:]\s*", "", text).strip() or text


def _template(gap: Gap) -> str:
    key = gap.kind + NO_ANSWER if gap.kind == FOLLOW_UP and gap.status == NO_ANSWER else gap.kind
    title = _title(gap.topic) if gap.kind == NOTABLE and "이력서" in gap.note else None
    if title:
        return TEMPLATES[NOTABLE + "_TITLE"].format(topic=title)
    if gap.kind == NOTABLE and gap.evidence and _ROLE.search(gap.evidence[0]):
        key = NOTABLE + "_ROLE"
        return _fix_josa(TEMPLATES[key].format(topic=gap.topic, detail=""))
    topic = (
        gap.topic if gap.kind in (NOTABLE, CLAIM) else _short(gap.topic.strip("'\""), 30)
    )  # 질문 첫머리의 따옴표는 뗀다
    detail = gap.detail
    if gap.kind == FOLLOW_UP and ("AI가" in detail or "면접관" in detail):
        # 답변 분석이 실패했을 때 남는 면접관용 메모('AI가 해석하지 못한 답변 …')는 지원자에게 읽지 않는다
        detail = "본인이 직접 한 일과 결과"
    return _fix_josa(TEMPLATES[key].format(topic=topic, detail=_short(detail, 30)))


def _fix_josa(question: str) -> str:
    """조사를 앞 글자 받침에 맞춘다.

    "…낮춤'라고" → "…낮춤'이라고",  "RDBMS 설계와 운영 경험와 관련해" → "…경험과 관련해" (받침이 있으면 '과')
    """

    def has_final(char: str) -> bool:
        """한글 글자에 받침이 있는지: (글자 번호 - 0xAC00) % 28 이 0이 아니면 받침이 있다."""
        return "가" <= char <= "힣" and (ord(char) - 0xAC00) % 28 != 0

    def pick_with(match: re.Match[str]) -> str:
        return match.group(1) + ("과" if has_final(match.group(1)) else "와")

    question = re.sub(r"([가-힣])[와과](?=\s*관련)", pick_with, question)

    def pick_quoted_with(match: re.Match[str]) -> str:
        """ "'함께 성장'와" → "'함께 성장'과" (인용 안 마지막 글자의 받침을 본다)."""
        inner = match.group(1)
        return f"'{inner}'" + ("과" if inner and has_final(inner[-1]) else "와")

    question = re.sub(r"'([^']+)'[와과](?=\s)", pick_quoted_with, question)

    def pick(match: re.Match[str]) -> str:
        inner = match.group(1)
        last = inner[-1] if inner else ""
        if has_final(last):
            return f"'{inner}'이라고"
        return match.group(0)

    return re.sub(r"'([^']+)'라고", pick, question)


_graph = StateGraph(State)
_graph.add_node("load_context", load_context)
_graph.add_node("find_gaps", find_gaps)
_graph.add_node("write", write)
_graph.add_node("bump_retry", bump_retry)
_graph.add_node("finalize", finalize)
_graph.add_edge(START, "load_context")
_graph.add_edge("load_context", "find_gaps")
_graph.add_conditional_edges("find_gaps", route_after_gaps, {"write": "write", "finalize": "finalize"})
_graph.add_conditional_edges("write", route_after_write, {"finalize": "finalize", "retry": "bump_retry"})
_graph.add_edge("bump_retry", "write")
_graph.add_edge("finalize", END)
interview_graph = _graph.compile()


async def generate_questions(
    llm: LlmClient,
    *,
    applicant: ApplicantDetail,
    posting: PostingContent,
    analysis: CandidateAnalysis,
    interview: InterviewView,
    focus: str | None,
    company: CompanyProfile | None = None,
    review: ApplicationReview | None = None,
) -> list[str]:
    """맞춤 면접 질문을 만든다 (1차: 자기소개 + 3개, 최종면접: 자기소개 + 자리 5개).

    차별 조건이 들어간 범위 요청은 무시하고 기본 기준으로 만든다 (규칙 6).
    company: 회사 인재상 · 조직 문화. 주면 최종면접 ② · ③ 자리의 기준으로 쓴다 (없어도 동작한다).
    review: 서류 전형 Agent의 상세 판정 (load_review로 읽는다). 있으면 1차 빈틈을 이것으로 고르고,
            없으면 analysis 요약으로 고른다.
    """
    safe_focus = "" if focus is None or blocked_attribute(focus) else focus.strip()
    state: State = {
        "llm": llm,
        "applicant": applicant,
        "posting": posting,
        "analysis": analysis,
        "review": review,
        "interview": interview,
        "focus": safe_focus,
        "company": company,
    }
    out = await interview_graph.ainvoke(state)
    return list(out["result"])


class ReviewReader(Protocol):
    """상세 판정을 읽는 쪽. 서류 전형 Agent의 저장소(ReviewStore)가 이 모양이다 (읽기만 하므로 latest만 쓴다)."""

    async def latest(self, application_id: UUID) -> ApplicationReview | None: ...


async def load_review(store: ReviewReader, applicant: ApplicantDetail) -> ApplicationReview | None:
    """서류 전형 Agent가 저장한 이 지원서의 최근 상세 판정. 읽기만 한다.

    없거나(분석 전 · stub) 저장소를 읽지 못하면 None → 질문은 요약(CandidateAnalysis)으로 만든다.
    """
    try:
        return await store.latest(applicant.info.application_id)
    except Exception:  # DB 연결 실패 등. 질문 생성은 요약으로 계속한다
        logger.warning(
            "서류 상세 판정을 읽지 못해 요약으로 질문을 만든다: %s", applicant.info.application_id, exc_info=True
        )
        return None
