"""최종 리포트 작성. 인원과 숫자는 코드가 입력에서 옮기고, 모델은 합격 근거와 특이사항 문장만 쓴다."""

import re
from collections.abc import Iterable
from contextlib import suppress

from hiremate_ai.agents.generation.report.types import (
    Finalist,
    FinalistDraft,
    FinalistInput,
    ReportContent,
    ReportDraft,
    ReportInput,
)
from hiremate_ai.agents.guardrails import blocked_attribute
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block

AGENT = "report"
MEMO_SOURCE = "전형 메모"
NO_EVIDENCE = "제출 문서에서 뚜렷한 근거를 찾지 못했어요. 전형 기록을 확인해 주세요."

SYSTEM = f"""채용이 끝난 뒤 담당자가 읽을 최종 리포트의 문장을 쓴다.
- 합격과 불합격은 이미 담당자가 확정했다. 결과를 다시 판단하거나 바꾸자고 하지 않는다.
- 인원 수와 합격률은 쓰지 않는다. 코드가 따로 넣는다. 자료에 없는 숫자를 만들지 않는다.
- finalists에는 자료의 최종 합격자마다 하나씩, 이름을 자료 그대로 적는다.
- reason은 그 지원자의 분석 근거와 전형 메모에 있는 내용만으로 쓴다. 근거가 없으면 없다고 쓴다.
- sources에는 reason에 쓴 분석 근거의 출처를 그대로 적고, 전형 메모를 썼으면 "{MEMO_SOURCE}"를 적는다.
- 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 쓰지 않는다.
- 존댓말(~어요)로 짧게 쓴다."""

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


async def write_report(data: ReportInput, llm: LlmClient) -> ReportContent:
    """확정 결과로 최종 리포트를 쓴다. 채용 상태는 바꾸지 않는다.

    모델이 형식에 맞는 답을 내지 못하면 숫자와 분석 근거만 옮긴 리포트를 돌려준다.
    """
    draft = ReportDraft(summary="", finalists=[], notes=[])
    if data.finalists:
        with suppress(LlmOutputError):
            draft = await llm.structured(ReportDraft, agent=AGENT, system=_system(), user=_user_prompt(data))
    allowed_numbers = _numbers_in(data)
    return ReportContent(
        summary=" ".join([_count_summary(data), *_usable([draft.summary], allowed_numbers)]),
        applicant_count=data.applicant_count,
        final_count=len(data.finalists),
        stages=data.stages,
        finalists=[_finalist(finalist, draft.finalists, allowed_numbers) for finalist in data.finalists],
        notes=_dedupe([*_count_notes(data), *_usable(draft.notes, allowed_numbers)]),
    )


def _user_prompt(data: ReportInput) -> str:
    parts = [f"채용: {data.title}", "최종 합격자별 자료:"]
    for finalist in data.finalists:
        notable = "\n".join(f"- {finding.text} (출처: {finding.source})" for finding in finalist.notable)
        parts.append(data_block("analysis", notable or "(분석 근거 없음)", name=finalist.name))
        if finalist.memos:
            memos = "\n".join(f"- {memo}" for memo in finalist.memos)
            parts.append(data_block("memo", memos, name=finalist.name, source=MEMO_SOURCE))
    return "\n\n".join(parts)


def _system() -> str:
    return f"{SYSTEM}\n\n{UNTRUSTED_RULE}"


def _count_summary(data: ReportInput) -> str:
    return (
        f"지원자 {data.applicant_count}명 중 **{len(data.finalists)}명**을 최종 합격으로 결정했어요. "
        f"전형 {len(data.stages)}개를 거쳤어요."
    )


def _count_notes(data: ReportInput) -> list[str]:
    """backend 집계 값으로만 만드는 특이사항. StubReportAgent와 같은 기준이다."""
    notes = []
    undecided = sum(data.undecided)
    if undecided > 0:
        notes.append(f"결정하지 않아 불합격으로 확정된 지원자가 전형 전체에서 {undecided}명 있었어요.")
    stages = [stage for stage in data.stages if stage.target > 0]
    if stages:
        lowest = min(stages, key=lambda stage: stage.passed / stage.target)
        rate = round(100 * lowest.passed / lowest.target)
        notes.append(f"{lowest.name}의 합격률이 {rate}%로 가장 낮았어요.")
    return notes


def _finalist(finalist: FinalistInput, drafts: list[FinalistDraft], allowed_numbers: set[str]) -> Finalist:
    allowed_sources = {finding.source for finding in finalist.notable}
    if finalist.memos:
        allowed_sources.add(MEMO_SOURCE)
    draft = next((draft for draft in drafts if draft.name.strip() == finalist.name), None)
    if draft is not None and _usable([draft.reason], allowed_numbers):
        sources = _dedupe(source for source in draft.sources if source in allowed_sources)
        if sources:
            return Finalist(name=finalist.name, reason=draft.reason.strip(), sources=sources)
    return _fallback_finalist(finalist)


def _fallback_finalist(finalist: FinalistInput) -> Finalist:
    """모델 문장을 쓸 수 없을 때. 분석 근거를 그대로 옮긴다 (StubReportAgent와 같다)."""
    sources = _dedupe(finding.source for finding in finalist.notable)
    if finalist.memos:
        sources.append(MEMO_SOURCE)
    reason = ", ".join(_shorten(finding.text) for finding in finalist.notable[:2]) or NO_EVIDENCE
    return Finalist(name=finalist.name, reason=reason, sources=sources)


def _usable(texts: Iterable[str], allowed_numbers: set[str]) -> list[str]:
    """빈 문장, 입력에 없는 숫자가 든 문장, 차별 조건이 든 문장은 버린다."""
    usable = []
    for text in texts:
        text = text.strip()
        if not text or blocked_attribute(text) is not None:
            continue
        if not set(_NUMBER.findall(text)) <= allowed_numbers:
            continue
        usable.append(text)
    return usable


def _numbers_in(data: ReportInput) -> set[str]:
    return set(_NUMBER.findall(data.model_dump_json(by_alias=True)))


def _dedupe(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _shorten(text: str) -> str:
    return text if len(text) <= 40 else text[:39] + "…"
