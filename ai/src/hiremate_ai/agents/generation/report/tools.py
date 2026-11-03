"""Report Agent 도구. 모두 묶음(ReportBundle) 안에서만 읽는다. 범위는 ToolRuntime의 context로 받아 모델이 바꿀 수 없다.

Report Agent는 다른 Agent를 부르지 않는다. 분석 Agent가 미리 남긴 판정 · 근거는 묶음으로만 읽는다.
"""

from dataclasses import dataclass, field

from langchain.tools import ToolRuntime, tool

from hiremate_ai.agents.generation.report.bundle import ReportBundle
from hiremate_ai.agents.generation.report.derive import scope_of, split_keys, tally
from hiremate_ai.agents.generation.report.skills import all_skills
from hiremate_ai.llm.prompt import data_block

NO_SUCH_APPLICANT = "범위 밖 지원자번호예요. get_overview의 지원자번호만 쓸 수 있어요."


@dataclass
class ReportScope:
    """도구의 조회 범위와 기록. skills는 읽은 스킬로, 진행 표시와 실행 기록에 쓴다.

    log는 화면의 AI 작업 과정에 보일 도구 사용 기록, read는 근거를 읽은 지원자별 근거 수다.
    """

    bundle: ReportBundle
    skills: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    read: dict[str, int] = field(default_factory=dict)


@tool
async def load_skill(name: str, runtime: ToolRuntime[ReportScope]) -> str:
    """스킬 지시문을 읽는다. name은 system의 스킬 목록에 있는 이름이다."""
    skill = all_skills().get(name)
    if skill is None:
        return f"없는 스킬이에요. 있는 스킬: {', '.join(all_skills())}"
    if name not in runtime.context.skills:
        runtime.context.skills.append(name)
    return skill.body


@tool
async def get_overview(runtime: ToolRuntime[ReportScope]) -> str:
    """리포트 범위의 전형, 지원자, 지표(id · 값), 값 key 목록(key · 이름 · 종류 · 값이 있는 지원자 수)을 본다."""
    bundle = runtime.context.bundle
    runtime.context.log.append("리포트 범위 · 지표 · 항목 목록을 읽음")
    lines = [f"리포트: {bundle.kind} · {bundle.title} · 기준 {bundle.as_of:%Y-%m-%d %H:%M}"]
    if bundle.focus:
        lines.append(f"요청 관점: {bundle.focus}")
    lines.append("전형:")
    for stage in bundle.stages:
        state = f"확정 {stage.confirmed_at:%m-%d %H:%M}" if stage.confirmed_at else "진행 중"
        current = " (현재)" if stage.stage_id == bundle.stage_id else ""
        lines.append(f"- {stage.name}{current} · {stage.type} · {state}")
    lines.append(f"지원자 {len(bundle.applicants)}명:")
    for applicant in bundle.applicants[:60]:
        career = "신입" if applicant.career_years == 0 else f"경력 {applicant.career_years}년"
        lines.append(f"- {applicant.number} · {career if applicant.career_years is not None else '경력 확인 필요'}")
    if bundle.targets:
        lines.append(f"비교 대상: {', '.join(bundle.targets)}")
    if splits := split_keys(bundle):
        lines.append(f"판정이 갈린 항목 (splits에 이유를 쓴다): {', '.join(splits)}")
    if bundle.total_key:
        lines.append(f"총점 key: {bundle.total_key}")
    if bundle.areas:
        lines.append("영역 (영역마다 섹션 하나):")
        for area in bundle.areas:
            score = f"점수 {area.score_key} · " if area.score_key else ""
            lines.append(f"- {area.id} · {area.label} · {score}항목 {', '.join(area.keys)}")
    lines.append("지표:")
    for metric in bundle.metrics:
        of = f" · {metric.key}의 집계" if metric.key else ""
        group = f" · group {metric.group}" if metric.group else ""
        lines.append(f"- {metric.id} · {metric.label} · {metric.value:g}{metric.unit}{of}{group}")
    lines.append("값 key:")
    keys: dict[str, list[str]] = {}
    for fact in bundle.facts:
        keys.setdefault(fact.key, []).append(fact.applicant)
    for key, numbers in keys.items():
        sample = next(fact for fact in bundle.facts if fact.key == key)
        values = sorted({str(fact.value) for fact in bundle.facts if fact.key == key})
        kind = "숫자" if isinstance(sample.value, float | int) else f"판정({' · '.join(values[:5])})"
        top = f"/{sample.max:g}" if sample.max is not None else ""
        lines.append(f"- {key} · {sample.label} · {kind}{top} · {len(set(numbers))}명")
    return "\n".join(lines)


@tool
async def get_values(keys: list[str], applicants: list[str], runtime: ToolRuntime[ReportScope]) -> str:
    """지원자들의 값을 읽는다. keys는 값 key(끝에 *를 붙이면 그 앞이 같은 key 전부), applicants는 지원자번호다."""
    bundle = runtime.context.bundle
    known = {applicant.number for applicant in bundle.applicants}
    if unknown := [number for number in applicants if number not in known]:
        return f"{NO_SUCH_APPLICANT} ({', '.join(unknown)})"

    rows = [
        fact
        for fact in bundle.facts
        if fact.applicant in applicants and any(_matches(fact.key, pattern) for pattern in keys)
    ]
    if not rows:
        return "그 key의 값이 없어요."
    runtime.context.log.append(f"판정 · 값 {len(rows)}개를 읽음 ({len({fact.applicant for fact in rows})}명)")
    lines = []
    for fact in rows:
        value = f"{fact.value:g}" if isinstance(fact.value, float | int) else fact.value
        top = f"/{fact.max:g}" if fact.max is not None else ""
        lines.append(f"{fact.id} · {fact.applicant} · {fact.key} ({fact.label}) = {value}{top}")
    # 값이 빈 지원자를 알려 준다. 빈 칸이 있는 key는 막대 · 쌓은 막대에 쓰지 않는다
    for key in dict.fromkeys(fact.key for fact in rows):
        have = {fact.applicant for fact in rows if fact.key == key}
        if missing := [number for number in applicants if number not in have]:
            lines.append(
                f"{key} 값 없음 (보류 · 확인 필요): {', '.join(missing)}. "
                "이 key는 bar · stacked에 쓰지 않는다. 영역 점수 표(rings)에는 넣어도 되고 화면이 '확인 필요'로 그린다"
            )
    return "\n".join(lines)


@tool
async def count_values(keys: list[str], runtime: ToolRuntime[ReportScope]) -> str:
    """판정 key마다 범위 전체(비교면 비교 대상)의 값별 인원과 충족 비율을 센다.

    항목끼리 '높다 · 낮다'를 쓰기 전에 읽는다. keys 끝에 *를 붙이면 그 앞이 같은 key 전부다.
    """
    bundle = runtime.context.bundle
    known = list(dict.fromkeys(fact.key for fact in bundle.facts if isinstance(fact.value, str)))
    wanted = [key for key in known if any(_matches(key, pattern) for pattern in keys)]
    if not wanted:
        return "그 판정 key가 없어요."
    people = scope_of(bundle)
    runtime.context.log.append(f"항목 {len(wanted)}개의 판정 인원을 셈")
    lines = []
    for key in wanted:
        counts, rate = tally(bundle, key, people)
        shown = " · ".join(f"{value} {count}명" for value, count in counts.most_common())
        lines.append(f"{key} · 충족 · 있음 {rate}% · {shown}")
    return "\n".join(lines)


def _matches(key: str, pattern: str) -> bool:
    return key.startswith(pattern[:-1]) if pattern.endswith("*") else key == pattern


@tool
async def get_evidence(applicant: str, runtime: ToolRuntime[ReportScope]) -> str:
    """지원자 한 명의 근거 문장(근거 id · 전형 · 분석 Agent · 출처)을 읽는다."""
    bundle = runtime.context.bundle
    if applicant not in {item.number for item in bundle.applicants}:
        return NO_SUCH_APPLICANT
    items = [item for item in bundle.evidence if item.applicant == applicant]
    if not items:
        return "근거 문장이 없어요."
    runtime.context.read[applicant] = len(items)
    lines = []
    for item in items:
        stage = bundle.stage(item.stage_id)
        lines.append(f"{item.id} · [{stage.name if stage else '?'} · {item.agent}] {item.line()}")
    return data_block("evidence", "\n".join(lines), applicant=applicant)


TOOLS = [load_skill, get_overview, get_values, count_values, get_evidence]
