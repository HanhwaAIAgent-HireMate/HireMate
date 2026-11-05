"""채용 최종 리포트. 구성 · 그래프 · 인원 문장은 코드가 기록으로 만들고(fallback_spec), 모델은 코드가 못 하는 문장만
쓴다 (기획 v9 FR-31: 인원과 숫자는 코드가, 모델은 합격 근거와 특이사항 문장만).

모델 호출은 한 번(structured)이고, 검사에 걸린 문장이 있으면 그 문장만 한 번 다시 쓰게 한다.
- 요약: 지원부터 최종 합격까지의 흐름과 다음 채용에서 다시 볼 점
- 최종 합격자별 판단 근거: 키워드와 근거 id (원문은 화면이 근거 id로 붙인다)
- 전형 간 특이사항: 서로 다른 전형 기록이 어긋나거나 이어지는 점. 근거 id를 붙인다
- 전형별 해석: 코드가 센 합격 · 불합격 그룹 비교(derive.stage_digests)에서 담당자가 다음 채용에 쓸 점 한 문장.
  전형 섹션의 읽을 점이 된다. 쓰지 못하면 코드가 쓴 인원 문장이 남는다

문장은 리포트 설계서와 같은 검사(차별 조건, 순위 · 추천, 판정 코드, 합니다체, 자료에 없는 숫자)를 거치고,
근거 id는 그 최종 합격자의 것이어야 한다. 끝내 걸린 문장은 버리고, 모델이 아무것도 쓰지 못하면 코드 구성만 낸다.
최종 합격자를 서로 견주거나 순위를 매기지 않는다. 채용 상태는 바꾸지 않는다.
"""

import logging
import re

from openai import APIError
from pydantic import BaseModel, Field

from hiremate_ai.agents.generation.report.bundle import ReportBundle
from hiremate_ai.agents.generation.report.check import (
    MAX_KEYWORD_LENGTH,
    MAX_KEYWORDS,
    numbers_in,
    problems,
    sentence_problems,
    stage_numbers,
)
from hiremate_ai.agents.generation.report.derive import stage_digests
from hiremate_ai.agents.generation.report.enrich import stage_prefix
from hiremate_ai.agents.generation.report.fallback import fallback_spec, finalists
from hiremate_ai.agents.generation.report.repair import plain_text
from hiremate_ai.agents.generation.report.spec import EvidenceBlock, EvidenceItem, ReportSpec, Section, TextBlock
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block

logger = logging.getLogger(__name__)

AGENT = "report-final"
REWRITES = 1
MAX_NOTABLE = 3
"""전형 간 특이사항 수. 섹션 하나의 부품 수(3)와 같다."""
MAX_FINALIST_EVIDENCE = 12
"""최종 합격자 한 명마다 모델에게 보여 줄 근거 수."""
_APPLICANT = re.compile(r"(?<![A-Za-z0-9])[A-Z]-\d{3,}(?!\d)")


class _Finalist(BaseModel):
    applicant: str = Field(description="최종 합격자 지원자번호")
    keywords: list[str] = Field(
        description=f"판단 근거 키워드 1~{MAX_KEYWORDS}개. {MAX_KEYWORD_LENGTH}자 안의 짧은 명사구"
    )
    evidence: list[str] = Field(description="그 지원자의 근거 id 1~3개 (자료에 있는 것만)")


class _Point(BaseModel):
    text: str = Field(description="전형 간 특이사항 한 문장. 해요체")
    evidence: list[str] = Field(description="그 문장의 근거 id 1개 이상 (최종 합격자의 것)")


class _StageNote(BaseModel):
    area: str = Field(description="전형 비교 자료의 영역 id (예: document, assessment)")
    text: str = Field(description="그 전형에서 담당자가 다음 채용에 쓸 점 한 문장. 해요체")


class _Draft(BaseModel):
    summary: str = Field(description="요약 두세 문장: 지원부터 최종 합격까지의 흐름과 다음 채용에서 다시 볼 점")
    finalists: list[_Finalist] = Field(description="최종 합격자마다 한 항목")
    notable: list[_Point] = Field(description=f"전형 간 특이사항 0~{MAX_NOTABLE}개. 근거가 없으면 비운다")
    stages: list[_StageNote] = Field(
        default_factory=list, description="전형 비교 자료의 영역마다 해석 한 문장. 자료가 없으면 비운다"
    )


SYSTEM = f"""너는 채용 담당자를 돕는 Report Agent다. 채용이 끝난 뒤 최종 리포트에 들어갈 문장만 쓴다.
그래프와 인원 표는 코드가 이미 만들었다. 너는 기록을 읽고 코드가 할 수 없는 해석만 쓴다.

- summary: 지원부터 최종 합격까지 인원이 어떻게 줄었는지, 최종 합격자가 공통으로 보인 점, 다음 채용에서 다시 볼 점
  (확인 필요가 많았던 항목, 서류만으로 판단이 어려웠던 점 등)을 두세 문장으로.
- finalists: 최종 합격자마다 합격을 받친 근거의 키워드와 근거 id. 근거 id는 자료에 있는 그 지원자의 것만 쓴다.
- notable: 전형 간 특이사항. 예: 서류에서 확인 필요였던 점이 면접에서 확인됐다, 서류 강점과 평가 점수가 어긋난다.
  근거 id가 없으면 쓰지 않는다.
- stages: '전형별 합격 · 불합격 비교'의 영역마다 한 문장.
  인원("30명 중 8명 합격")은 화면에 이미 있으니 되풀이하지 않는다.
  다음 중 그 전형에서 가장 눈에 띄는 하나를 쓴다.
  · 무엇이 합격을 갈랐나: 합격자와 불합격자의 충족 비율이나 평균 점수 차이가 가장 큰 항목
  · 기준이 제대로 작동했나: 전체 중 충족한 사람이 거의 없거나 거의 모두인 항목(서류만으로 가리기 어려웠던 기준)
  · 점수가 얼마나 촘촘했나: 합격자 최저와 불합격자 최고의 차이, 두 그룹 점수가 겹친 영역
  항목은 번호(Q-01) 대신 짧은 이름으로 쓴다. 그룹 단위로만 쓰고 지원자 한 명을 집어 쓰지 않는다.

반드시 지킬 것:
- 숫자는 자료에 있는 값만 쓴다. 새로 계산하지 않는다.
- 최종 합격자를 서로 견주거나 순위를 매기지 않는다('가장', '제일', '더 뛰어나다'). 누구를 뽑으라고 쓰지 않는다.
- 근거가 '확인되지 않았어요'인 점을 강점처럼 쓰지 않는다. 서술 근거만 있는 강점은 '서류에 적혀 있어요'처럼 약하게 쓴다.
- 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 쓰지 않는다.
- 판정 코드(PASS · MET)를 쓰지 않고 합격 · 충족처럼 화면 말로 쓴다. 지원자는 지원자번호(A-0012)로 쓴다.
- 해요체(~어요 · ~예요)로 짧게 쓴다.
{UNTRUSTED_RULE}"""


def facts_text(bundle: ReportBundle, people: list[str]) -> str:
    """모델에게 줄 기록. 전형별 인원, 최종 합격자의 전형별 결정 · 점수, 근거(id와 한 줄)다."""
    values = {metric.id: metric for metric in bundle.metrics}
    lines = []
    if "m-applicants" in values:
        lines.append(f"지원 {values['m-applicants'].value:g}명, 최종 합격 {len(people)}명")
    for stage in bundle.stages:
        prefix = stage_prefix(bundle.stages, stage)
        target, passed = values.get(f"m-{prefix}-target"), values.get(f"m-{prefix}-pass")
        if target and passed:
            lines.append(f"- {stage.name}: 대상 {target.value:g}명 중 합격 {passed.value:g}명")
    for number in people:
        lines.append(f"\n최종 합격자 {number}")
        for fact in bundle.facts:
            if fact.applicant == number and not fact.key.split(".")[-1].startswith(("Q-", "P-")):
                shown = f"{fact.value:g}" if isinstance(fact.value, float | int) else plain_text(str(fact.value))
                lines.append(f"- {fact.label}: {shown}" + (f" / {fact.max:g}" if fact.max else ""))
        own = [item for item in bundle.evidence if item.applicant == number][:MAX_FINALIST_EVIDENCE]
        lines += [f"- 근거 {item.id} · {item.line()}" for item in own] or ["- 근거 문장 없음"]
    if digests := stage_digests(bundle):
        lines.append("\n전형별 합격 · 불합격 비교 (코드가 센 값)")
        for digest in digests:
            lines.append(f"[{digest.area}] {digest.label}")
            lines += [f"- {line}" for line in digest.lines]
    return "\n".join(lines)


def _clean_keywords(keywords: list[str]) -> list[str]:
    kept = [word.strip() for word in keywords if word.strip() and len(word.strip()) <= MAX_KEYWORD_LENGTH]
    return kept[:MAX_KEYWORDS]


def _review(draft: _Draft, bundle: ReportBundle, people: list[str]) -> tuple[_Draft, list[str]]:
    """검사를 통과한 문장만 남긴 초안과, 걸린 까닭. 판정 코드는 먼저 화면 말로 바꾼다."""
    allowed = numbers_in(bundle) | stage_numbers(bundle)
    areas = {digest.area for digest in stage_digests(bundle)}
    owner = {item.id: item.applicant for item in bundle.evidence}
    found: list[str] = []

    def sentence(label: str, text: str) -> str | None:
        text = plain_text(text.strip())
        problems = sentence_problems(label, text, allowed)
        if outside := sorted(set(_APPLICANT.findall(text)) - set(people)):
            problems.append(f"{label}에 최종 합격자가 아닌 지원자번호가 있다: {', '.join(outside)}")
        found.extend(problems)
        return None if problems or not text else text

    summary = sentence("summary", draft.summary) or ""
    kept_finalists = []
    for index, item in enumerate(draft.finalists):
        evidence = [i for i in item.evidence if owner.get(i) == item.applicant]
        keywords = [plain_text(word) for word in _clean_keywords(item.keywords)]
        if item.applicant not in people:
            found.append(f"finalists[{index}]: {item.applicant}는 최종 합격자가 아니다")
        elif not evidence or not keywords:
            found.append(f"finalists[{index}]: {item.applicant}의 근거 id와 짧은 키워드가 필요하다")
        else:
            kept_finalists.append(item.model_copy(update={"evidence": evidence, "keywords": keywords}))
    kept_points = []
    for index, point in enumerate(draft.notable[:MAX_NOTABLE]):
        evidence = [i for i in point.evidence if owner.get(i) in people]
        if (text := sentence(f"notable[{index}]", point.text)) is None:
            continue
        if not evidence:
            found.append(f"notable[{index}]: 최종 합격자의 근거 id가 없다")
            continue
        kept_points.append(_Point(text=text, evidence=evidence))
    kept_notes: dict[str, _StageNote] = {}
    for index, note in enumerate(draft.stages):
        label = f"stages[{index}]"
        if note.area not in areas:
            found.append(f"{label}: 비교 자료에 없는 영역 id: {note.area}")
        elif _APPLICANT.search(note.text):
            found.append(f"{label}: 전형 해석은 그룹 단위로 쓰고 지원자번호를 쓰지 않는다")
        elif note.area not in kept_notes and (text := sentence(label, note.text)) is not None:
            kept_notes[note.area] = _StageNote(area=note.area, text=text)
    return (
        _Draft(summary=summary, finalists=kept_finalists, notable=kept_points, stages=list(kept_notes.values())),
        found,
    )


def _merge(spec: ReportSpec, draft: _Draft) -> ReportSpec:
    """코드 구성에 모델 문장을 넣는다. 요약을 바꾸고, 최종 합격자 섹션에 판단 근거를, 그 뒤에 특이사항 섹션을 둔다."""
    notes = {note.area: note.text for note in draft.stages}
    sections = [
        section.model_copy(update={"takeaway": notes[section.area]}) if section.area in notes else section
        for section in spec.sections
    ]
    if draft.finalists:
        evidence = EvidenceBlock(
            title="최종 합격자 판단 근거",
            items=[
                EvidenceItem(applicant=item.applicant, keywords=item.keywords, evidence=item.evidence)
                for item in draft.finalists
            ],
        )
        index = next((i for i, s in enumerate(sections) if s.title == "최종 합격자"), None)
        if index is None:
            sections.append(Section(title="최종 합격자", takeaway="최종 합격자의 판단 근거예요.", blocks=[evidence]))
        else:
            target = sections[index]
            sections[index] = target.model_copy(update={"blocks": [*target.blocks, evidence][:3]})
    if draft.notable:
        sections.append(
            Section(
                title="전형 간 특이사항",
                takeaway=draft.notable[0].text,
                blocks=[
                    TextBlock(title=f"특이사항 {i + 1}", text=point.text, evidence=point.evidence)
                    for i, point in enumerate(draft.notable)
                ],
            )
        )
    summary = draft.summary or spec.summary
    return spec.model_copy(update={"summary": summary, "sections": sections})


async def compose_final(bundle: ReportBundle, llm: LlmClient) -> tuple[ReportSpec, list[str], bool]:
    """최종 리포트 설계서, 화면의 AI 작업 과정, 모델 문장이 하나도 없는지(코드 구성만)."""
    spec = fallback_spec(bundle)
    people = finalists(bundle)
    evidence = sum(1 for item in bundle.evidence if item.applicant in people)
    steps = ["전형 기록으로 그래프와 인원 표를 만듦"]
    if not people:
        return spec, [*steps, "최종 합격자가 없어 AI 문장 없이 기록만 담음"], True
    steps.append(f"최종 합격자 {len(people)}명의 근거 {evidence}건을 읽음")
    text = facts_text(bundle, people)
    user = data_block("final", text)
    best = _Draft(summary="", finalists=[], notable=[])
    for attempt in range(REWRITES + 1):
        try:
            draft = await llm.structured(_Draft, agent=AGENT, system=SYSTEM, user=user)
        except LlmOutputError as error:
            logger.warning("최종 리포트 문장을 만들지 못했다 (reason=%s)", error.reason.value)
            break
        except APIError as error:
            logger.warning("모델 서버 오류로 최종 리포트 문장을 만들지 못했다 (%s)", type(error).__name__)
            break
        reviewed, found = _review(draft, bundle, people)
        best = _combine(best, reviewed)
        if not found or attempt == REWRITES:
            steps.append(f"AI 문장 검사를 {attempt + 1}번째에 통과" if not found else "검사에 걸린 AI 문장은 뺌")
            break
        logger.info("최종 리포트 문장을 다시 쓰게 한다: %s", " | ".join(found))
        user = data_block("final", text) + "\n\n고칠 점 (나머지는 그대로 둔다):\n" + "\n".join(f"- {p}" for p in found)
    merged = _merge(spec, best)
    if merged != spec and (left := problems(merged, bundle)):
        # 합친 설계서가 검사에 걸리면 모델 문장을 빼고 기록만 낸다
        logger.warning("최종 리포트에 넣은 문장이 검사에 걸려 기록만 낸다: %s", " | ".join(left))
        merged = spec
    if best.stages and merged != spec:
        steps.append(f"전형 {len(best.stages)}개의 합격 · 불합격 기록을 견주어 해석함")
    written = merged != spec
    if not written:
        steps.append("AI 문장을 넣지 못해 기록만 담음")
    return merged, steps, not written


def _combine(current: _Draft, new: _Draft) -> _Draft:
    """두 시도에서 통과한 문장을 모은다. 다시 쓴 문장이 있으면 새 것을, 없으면 앞 시도의 것을 둔다."""
    people = {item.applicant: item for item in current.finalists} | {item.applicant: item for item in new.finalists}
    return _Draft(
        summary=new.summary or current.summary,
        finalists=list(people.values()),
        notable=new.notable or current.notable,
        stages=list(({note.area: note for note in current.stages} | {note.area: note for note in new.stages}).values()),
    )
