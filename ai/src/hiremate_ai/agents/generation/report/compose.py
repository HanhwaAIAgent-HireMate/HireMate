"""Report Agent 도구 루프. 스킬을 골라 읽고, 묶음을 조회한 뒤 설계서를 낸다. 다른 Agent는 부르지 않는다.

설계서는 check.problems로 검사해 한 번 고쳐 쓰게 하고, 끝내 통과하지 못하면 기본 구성을 쓴다.
"""

import logging

from openai import APIError

from hiremate_ai.agents.generation.report.bundle import ReportBundle, ReportKind
from hiremate_ai.agents.generation.report.check import MAX_BRIEF_SUMMARY, problems
from hiremate_ai.agents.generation.report.derive import drawable
from hiremate_ai.agents.generation.report.fallback import fallback_spec
from hiremate_ai.agents.generation.report.repair import repair
from hiremate_ai.agents.generation.report.skills import catalog
from hiremate_ai.agents.generation.report.spec import ReportSpec
from hiremate_ai.agents.generation.report.tools import TOOLS, ReportScope
from hiremate_ai.agents.guardrails import blocked_attribute
from hiremate_ai.config import settings
from hiremate_ai.contract import ContractModel, StageType
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import data_block

logger = logging.getLogger(__name__)

AGENT = "report"
REWRITES = 2
"""검사에 걸린 설계서를 고쳐 쓰는 횟수. 백그라운드 작업이라 Root보다 넉넉하다."""
REWRITE = (
    "설계서에 고칠 점이 있다. 아래 문제만 고치고, 문제가 없는 섹션과 부품은 그대로 두어 설계서 전체를 다시 낸다:\n"
)
"""고쳐 쓰기 지시. 고치다가 앞에서 맞춘 부품을 빼 버리지 않게 한다."""
MAX_FOCUS = 40
"""요청 관점 글자 수. 관점은 '협업'처럼 짧은 말이라, 긴 글은 잘라 지시문을 끼워 넣지 못하게 한다."""
BLOCKED_FOCUS = "요청 관점에 채용 판단에 쓰면 안 되는 조건이 있어 관점 없이 만듦"

SYSTEM = """너는 채용 담당자가 읽을 리포트를 설계하는 Report Agent다.
글만 쓰지 않는다. 정해진 부품(kpi · bar · stacked · radar · distribution · donut · cross · share · composition ·
position · rings · matrix · tally · table · evidence · text)을 골라 묶음의 지표 id · 값 key · 근거 id로 채우는
설계서(ReportSpec)를 낸다. 화면과 PDF가 그것을 그린다.

설계서는 섹션으로 나눈다. 한눈에 보기 → 영역마다 섹션 하나(area에 영역 id) → 요청 관점(있으면) → 정리.
섹션마다 읽을 점(takeaway) 한 문장과 부품 1~3개를 둔다. 한 부품에는 한 가지만 그린다.
takeaway는 '무엇을 보여 줘요'가 아니라 그림에서 읽은 사실이다 (예: 'Q-05 테스트 코드만 판정이 갈렸어요').

반드시 지킬 것:
- 숫자는 지표 · 값으로만 보여 준다. 문장에 쓰는 숫자는 도구로 읽은 값만 쓴다.
- 판단 문장에는 근거 id를 붙인다.
- 합격 · 불합격을 판단하거나, 순위를 매기거나('가장 높다' 포함), 누구를 뽑으라고 쓰지 않는다.
- 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 쓰지 않는다.
- 지원자는 지원자번호(A-0012)로만 쓴다.
- 모든 문장은 해요체(~어요 · ~예요)로 짧게 쓴다. ~습니다 · ~합니다는 쓰지 않는다.
- 시각화 부품은 모두 합쳐 셋 이상, 시각화 부품마다 caption 한 줄.
- 같은 모양의 그래프만 되풀이하지 말고 자료에 맞는 부품을 고른다.

먼저 visual-guide와 리포트 종류에 맞는 스킬을 load_skill로 읽고, 읽은 스킬 이름을 skills에 적는다.

스킬 목록:
{catalog}"""

SKILL_NAMES = {
    "visual-guide": "그래프 고르기",
    "compare": "지원자 비교",
    "evidence": "근거 고르기",
    "final": "채용 최종 리포트",
    "stage-document": "서류 전형 결과",
    "stage-assessment": "평가 전형 결과",
    "stage-interview": "면접 전형 결과",
}
"""화면의 AI 작업 과정에 보일 지침 이름 (frontend report/skills.ts와 같다)."""

_STAGE_SKILL = {
    StageType.DOCUMENT: "stage-document",
    StageType.ASSESSMENT: "stage-assessment",
    StageType.INTERVIEW: "stage-interview",
}


class ComposedReport(ContractModel):
    """Report Agent 결과 (contract/ComposedReport.json). fallback이면 모델 설계서 대신 기본 구성을 썼다.

    skills는 읽은 스킬로, 화면의 실행 기록 칩에 쓴다.
    steps는 화면의 'AI 작업 과정'에 보일 한 줄씩이다 (읽은 자료, 검사 횟수, 코드가 고친 것).
    bundle은 Agent가 실제로 읽은 묶음이다 (ai가 분석 판정 · 근거를 붙인 뒤). 화면은 이 묶음으로 그린다.
    """

    spec: ReportSpec
    skills: list[str]
    fallback: bool
    bundle: ReportBundle
    steps: list[str] = []


async def compose_report(bundle: ReportBundle, llm: LlmClient) -> ComposedReport:
    """묶음으로 리포트 설계서를 만든다. 채용 상태는 바꾸지 않는다."""
    bundle, guarded = guard_focus(bundle)
    scope = ReportScope(bundle=bundle, log=guarded)
    agent = llm.tool_agent(
        ReportSpec,
        agent=AGENT,
        system=SYSTEM.format(catalog=catalog()),
        tools=TOOLS,
        context=ReportScope,
        max_calls=settings.llm_report_max_calls,
    )

    repaired: list[ReportSpec] = []
    notes: list[str] = []

    async def validate(spec: ReportSpec) -> str | None:
        # 기계적인 규칙 위반은 코드가 먼저 고치고, 고친 설계서를 검사한다
        # 관점 묶음은 다시 쓸 기회가 남았으면 모델에게 돌려주고, 마지막 시도에서는 코드가 묶는다
        notes.clear()
        spec = repair(spec, bundle, group_by_code=len(repaired) >= REWRITES, notes=notes)
        repaired.append(spec)
        found = problems(spec, bundle)
        if unread := [name for name in recommended_skills(bundle) if name not in scope.skills]:
            found.append(f"권하는 스킬 {', '.join(unread)}을 읽지 않았다. load_skill로 읽고 그 구성을 따른다")
        if not found:
            return None
        # 지원자 정보 없이 검사 문구만 남긴다 (지원자번호 · 값 key · 근거 id)
        logger.info("리포트 설계서 검사에 걸림 (%s): %s", bundle.kind, " | ".join(found))
        return REWRITE + "\n".join(f"- {p}" for p in found)

    try:
        spec = await agent.run(request(bundle), context=scope, validate=validate, rewrites=REWRITES)
    except (LlmOutputError, APIError) as error:
        # 모델 서버 오류(사용 한도, 연결 끊김, 요청 거절)도 SDK가 다시 시도한 뒤라 빈 화면 대신 기본 구성을 낸다
        if isinstance(error, APIError):
            logger.warning("모델 서버 오류로 리포트를 기본 구성으로 만든다 (%s)", type(error).__name__)
            tried = "모델 서버 오류로 AI 구성을 받지 못해 코드가 숫자와 표로 만듦"
        else:
            logger.warning("리포트를 기본 구성으로 만든다 (reason=%s)", error.reason.value)
            tried = f"AI 구성이 검사를 {len(repaired)}번 모두 넘지 못해 코드가 숫자와 표로 만듦" if repaired else ""
        return ComposedReport(
            spec=fallback_spec(bundle),
            skills=scope.skills,
            fallback=True,
            bundle=bundle,
            steps=steps(scope, [tried or "AI 구성을 받지 못해 코드가 숫자와 표로 만듦"]),
        )
    spec = repaired[-1] if repaired else spec
    finished = [f"구성 검사를 {max(1, len(repaired))}번째에 통과"]
    finished += [f"코드 보완: {note}" for note in notes]
    return ComposedReport(
        spec=spec.model_copy(update={"skills": scope.skills}),
        skills=scope.skills,
        fallback=False,
        bundle=bundle,
        steps=steps(scope, finished),
    )


def guard_focus(bundle: ReportBundle) -> tuple[ReportBundle, list[str]]:
    """모델에 넘기기 전에 요청 관점을 코드가 검사한다. 줄바꿈을 없애고 MAX_FOCUS자로 자른다.

    리포트 창의 비교 요청은 Root를 거치지 않으므로, 차별 조건(규칙 6)이 든 관점은 여기서 빼고 화면의 작업 과정에 남긴다.
    """
    focus = " ".join(bundle.focus.split())[:MAX_FOCUS]
    if focus and blocked_attribute(focus):
        logger.info("차별 조건이 든 요청 관점을 빼고 리포트를 만든다")
        return bundle.model_copy(update={"focus": ""}), [BLOCKED_FOCUS]
    return (bundle if focus == bundle.focus else bundle.model_copy(update={"focus": focus})), []


def steps(scope: ReportScope, finished: list[str]) -> list[str]:
    """화면의 AI 작업 과정. 읽은 스킬, 도구로 읽은 자료, 검사 · 보완 순서다."""
    read = ", ".join(SKILL_NAMES.get(name, name) for name in scope.skills)
    lines = [f"지침 {len(scope.skills)}개를 읽음 ({read})"] if scope.skills else []
    lines += list(dict.fromkeys(scope.log))
    if scope.read:
        lines.append(f"근거 {sum(scope.read.values())}건을 읽음 ({len(scope.read)}명)")
    return lines + [line for line in finished if line]


def recommended_skills(bundle: ReportBundle) -> list[str]:
    """리포트 종류에 맞는 스킬. 읽지 않고 낸 설계서는 검사에 걸린다."""
    if bundle.kind is ReportKind.COMPARE:
        kind = "compare"
    elif bundle.kind is ReportKind.FINAL:
        kind = "final"
    else:
        kind = _STAGE_SKILL.get(bundle.current.type, "stage-document")
    return ["visual-guide", kind, "evidence"]


def request(bundle: ReportBundle) -> str:
    """user 지시. 리포트 종류, 권하는 스킬, 비교 대상과 관점이다. 자료는 도구로 읽는다."""
    kind = {
        ReportKind.STAGE: "전형 결과 리포트",
        ReportKind.COMPARE: "지원자 비교 리포트",
        ReportKind.FINAL: "채용 최종 리포트",
    }
    scope = (
        f"범위: 모든 전형 ({', '.join(stage.name for stage in bundle.stages)})"
        if bundle.kind is ReportKind.FINAL
        else f"현재 전형: {bundle.current.name}"
    )
    lines = [
        f"{kind[bundle.kind]}를 설계한다. {scope}.",
        f"권하는 스킬: {', '.join(recommended_skills(bundle))}. 모두 load_skill로 먼저 읽는다.",
    ]
    if bundle.brief:
        lines.append(
            f"간략히 요청이다. summary는 {MAX_BRIEF_SUMMARY}자 이내 두 문장, 섹션 한두 개, 부품 셋까지만 쓴다. "
            "영역마다 섹션을 두지 않아도 된다."
        )
    elif bundle.areas:
        areas = ", ".join(f"{area.id}({area.label})" for area in bundle.areas)
        lines.append(f"영역: {areas}. 영역마다 섹션을 하나씩 둔다.")
    if bundle.targets:
        lines.append(f"비교 대상: {', '.join(bundle.targets)}")
    if bundle.kind is ReportKind.COMPARE and bundle.total_key is None and not any(a.score_key for a in bundle.areas):
        lines.append(
            "점수 없이 항목 판정만 있는 전형이다. rings(관점) · matrix · tally로 그리고 "
            "bar · stacked · distribution · position · donut은 쓰지 않는다 (compare 스킬의 '점수가 없을 때')."
        )
    if bundle.focus:
        # 담당자가 적은 말이라 지시로 읽지 않게 자료 블록으로 넣는다
        lines.append("요청 관점 (관점 이름으로만 쓴다):\n" + data_block("focus", bundle.focus))
    if len(bundle.stages) > 1 and bundle.kind is not ReportKind.FINAL:
        lines.append(f"범위: {', '.join(stage.name for stage in bundle.stages)}")
    if bundle.kind is not ReportKind.COMPARE and not bundle.brief and (found := hints(bundle)):
        lines.append("이 묶음으로 그릴 수 있는 자료 (모두 부품으로 쓴다):")
        lines += found
    return "\n".join(lines)


def hints(bundle: ReportBundle) -> list[str]:
    """영역 밖에서 바로 그릴 수 있는 자료. 모델이 부품 종류를 고를 때 놓치지 않게 알려 준다."""
    data = drawable(bundle)
    lines = []
    if data.flags:
        shown = ", ".join(f"{key}({'/'.join(sorted(found))})" for key, found in data.flags.items())
        lines.append(f"- 두 갈래 판정 {shown} → distribution split" + (", cross" if len(data.flags) > 1 else ""))
    lines += [f"- 있음 · 없음 key {prefix}.* {len(keys)}개 → share" for prefix, keys in data.families.items()]
    if data.groups:
        shown = ", ".join(f"{group}({len(ids)}조각)" for group, ids in data.groups.items())
        lines.append(f"- 조각 지표 group {shown} → donut, 구간이 같은 group 둘 이상이면 composition")
    return lines
