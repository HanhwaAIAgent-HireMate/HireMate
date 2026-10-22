"""최종 리포트 작성. 인원과 숫자는 코드가 입력에서 옮기고, 모델은 합격 근거와 특이사항 문장만 쓴다.

합격 근거는 서류 분석(notable), 전형 메모, 지원자 프로필의 평가 · 면접 분석을 함께 쓴다 (v8 Report 입력).
프로필의 확인할 점(평가 약점, 면접에서 확인되지 않거나 어긋난 점)은 강점처럼 쓰지 않고 특이사항으로 남긴다.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from contextlib import suppress
from uuid import UUID

from hiremate_ai.agents.generation.report.types import (
    Finalist,
    FinalistDraft,
    FinalistInput,
    ProfileNote,
    ReportContent,
    ReportDraft,
    ReportInput,
)
from hiremate_ai.agents.guardrails import blocked_attribute
from hiremate_ai.db.profile import ItemAgent, ItemCategory
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block

type Profiles = Mapping[UUID, Sequence[ProfileNote]]
"""합격자 지원서 ID → 프로필의 평가 · 면접 분석 항목 (profiles.load_profiles)."""

AGENT = "report"
MEMO_SOURCE = "전형 메모"
NO_EVIDENCE = "제출 문서에서 뚜렷한 근거를 찾지 못했어요. 전형 기록을 확인해 주세요."
CHECK_NOTES_PER_FINALIST = 2
"""합격자마다 특이사항으로 옮기는 확인할 점 수. 많으면 리포트가 확인할 점 목록이 된다."""
REPEAT_OVERLAP = 0.5
"""모델이 쓴 특이사항이 확인할 점과 이만큼 넘게 겹치면 되풀이로 보고 버린다."""

_PROFILE_LABELS = {
    (ItemAgent.ASSESSMENT, ItemCategory.STRENGTH): "평가 강점",
    (ItemAgent.ASSESSMENT, ItemCategory.CHECK): "평가 확인할 점",
    (ItemAgent.INTERVIEW, ItemCategory.STRENGTH): "면접에서 확인된 점",
    (ItemAgent.INTERVIEW, ItemCategory.CHECK): "면접에서 확인되지 않은 점",
}

SYSTEM = f"""채용이 끝난 뒤 담당자가 읽을 최종 리포트의 문장을 쓴다.
- 합격과 불합격은 이미 담당자가 확정했다. 결과를 다시 판단하거나 바꾸자고 하지 않는다.
- 인원 수와 합격률은 쓰지 않는다. 코드가 따로 넣는다. 자료에 없는 숫자를 만들지 않는다.
- finalists에는 자료의 최종 합격자마다 하나씩, 이름을 자료 그대로 적는다.
- reason은 그 지원자의 서류 분석, 전형 메모, 평가 · 면접 분석에 있는 내용만으로 쓴다. 근거가 없으면 없다고 쓴다.
  여러 전형의 근거가 있으면 함께 쓴다(예: 서류의 경험이 면접에서 확인됨).
- 평가 확인할 점과 면접에서 확인되지 않은 점은 reason에 강점처럼 쓰지 않는다.
- sources에는 reason에 쓴 근거의 출처를 자료에 적힌 그대로 적고, 전형 메모를 썼으면 "{MEMO_SOURCE}"를 적는다.
- notes에는 여러 전형을 견주어 드러난 특이사항만, 어느 합격자의 어떤 내용이 어느 전형에서 이어지거나 어긋났는지
  이름과 함께 쓴다. 평가 확인할 점과 면접에서 확인되지 않은 점은 코드가 따로 넣으니 다시 쓰지 않는다.
  해당하는 내용이 없으면 빈 목록이다.
- 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 쓰지 않는다.
- 존댓말(~어요)로 짧게 쓴다."""

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_PUNCTUATION = re.compile(r"[\s.,·()]")


async def write_report(data: ReportInput, llm: LlmClient, profiles: Profiles | None = None) -> ReportContent:
    """확정 결과로 최종 리포트를 쓴다. 채용 상태는 바꾸지 않는다.

    profiles는 합격자 프로필의 평가 · 면접 분석 항목이다. 없으면 서류 분석과 전형 메모만 쓴다.
    모델 문장이 검사를 통과하지 못하면 이유를 붙여 한 번만 다시 쓰게 한다. 그래도 남은 문제 문장은 버리고,
    모델이 형식에 맞는 답을 내지 못하면 숫자와 분석 근거만 옮긴 리포트를 돌려준다.
    """
    profiles = profiles or {}
    allowed_numbers = _numbers_in(data, profiles)
    draft = None
    if data.finalists:
        user = _user_prompt(data, profiles)
        draft = await _draft(llm, user)
        if draft is None:
            draft = await _draft(llm, user)
        elif found := _problems(draft, data, profiles, allowed_numbers):
            draft = await _draft(llm, _retry_prompt(user, draft, found)) or draft
    draft = draft or ReportDraft(summary="", finalists=[], notes=[])
    return ReportContent(
        summary=" ".join([_count_summary(data), *_usable([draft.summary], allowed_numbers)]),
        applicant_count=data.applicant_count,
        final_count=len(data.finalists),
        stages=data.stages,
        finalists=[
            _finalist(finalist, _notes_of(profiles, finalist), draft.finalists, allowed_numbers)
            for finalist in data.finalists
        ],
        notes=_notes(data, profiles, draft.notes, allowed_numbers),
    )


async def _draft(llm: LlmClient, user: str) -> ReportDraft | None:
    with suppress(LlmOutputError):
        return await llm.structured(ReportDraft, agent=AGENT, system=_system(), user=user)
    return None


def _problems(draft: ReportDraft, data: ReportInput, profiles: Profiles, allowed_numbers: set[str]) -> list[str]:
    """모델 문장 중 그대로 쓸 수 없는 것. 다시 쓰게 할 때 모델에게 이유로 보여 준다."""
    found = []
    texts = [("summary", draft.summary), *((f"notes[{i}]", note) for i, note in enumerate(draft.notes))]
    for label, text in texts:
        if text.strip() and not _usable([text], allowed_numbers):
            found.append(f"{label}에 자료에 없는 숫자나 쓰면 안 되는 조건이 있다: {text}")
    drafts = {finalist.name.strip(): finalist for finalist in draft.finalists}
    for finalist in data.finalists:
        written = drafts.get(finalist.name)
        if written is None:
            found.append(f"최종 합격자 {finalist.name}의 reason이 없다")
            continue
        if not _usable([written.reason], allowed_numbers):
            found.append(f"{finalist.name}의 reason에 자료에 없는 숫자나 쓰면 안 되는 조건이 있다")
        allowed_sources = _allowed_sources(finalist, _notes_of(profiles, finalist))
        if unknown := [source for source in written.sources if source not in allowed_sources]:
            found.append(f"{finalist.name}의 sources에 자료에 없는 출처가 있다: {', '.join(unknown)}")
    if unknown_names := sorted(set(drafts) - {finalist.name for finalist in data.finalists}):
        found.append(f"자료에 없는 이름이 finalists에 있다: {', '.join(unknown_names)}")
    return found


def _retry_prompt(user: str, draft: ReportDraft, found: list[str]) -> str:
    reasons = "\n".join(f"- {reason}" for reason in found)
    return (
        f"{user}\n\n앞서 쓴 답:\n{draft.model_dump_json()}\n\n앞서 쓴 답의 문제:\n{reasons}\n"
        "문제를 고쳐 답 전체를 다시 쓴다."
    )


def _user_prompt(data: ReportInput, profiles: Profiles) -> str:
    parts = [f"채용: {data.title}", "최종 합격자별 자료:"]
    for finalist in data.finalists:
        notable = "\n".join(f"- {finding.text} (출처: {finding.source})" for finding in finalist.notable)
        parts.append(data_block("analysis", notable or "(분석 근거 없음)", name=finalist.name))
        if finalist.memos:
            memos = "\n".join(f"- {memo}" for memo in finalist.memos)
            parts.append(data_block("memo", memos, name=finalist.name, source=MEMO_SOURCE))
        if notes := _notes_of(profiles, finalist):
            lines = "\n".join(_note_line(note) for note in notes)
            parts.append(data_block("stages", lines, name=finalist.name))
    return "\n\n".join(parts)


def _note_line(note: ProfileNote) -> str:
    label = _PROFILE_LABELS.get((note.agent, note.category), "분석")
    evidence = f" (근거: {note.evidence})" if note.evidence else ""
    return f"- [{label}] {note.content}{evidence} (출처: {note.source})"


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
    # 전형이 하나면 견줄 전형이 없어 '가장 낮았다'고 쓰지 않는다
    if len(stages) >= 2:
        lowest = min(stages, key=lambda stage: stage.passed / stage.target)
        rate = round(100 * lowest.passed / lowest.target)
        notes.append(f"{lowest.name}의 합격률이 {rate}%로 가장 낮았어요.")
    return notes


def _notes(data: ReportInput, profiles: Profiles, drafted: list[str], allowed_numbers: set[str]) -> list[str]:
    """집계 특이사항, 확인할 점, 모델이 쓴 특이사항 순이다. 모델 문장이 확인할 점을 되풀이하면 버린다."""
    checks = _check_notes(data, profiles)
    written = [
        note
        for note in _usable(drafted, allowed_numbers)
        if not any(_repeats(note, check) for check in checks) and not _copied_from_rules(note)
    ]
    return _dedupe([*_count_notes(data), *checks, *written])


def _copied_from_rules(note: str) -> bool:
    """지시문의 낱말을 그대로 옮긴 문장. 작은 모델은 지시문의 설명을 답으로 베끼기도 한다."""
    return _PUNCTUATION.sub("", note) in _PUNCTUATION.sub("", SYSTEM)


def _repeats(note: str, check: str) -> bool:
    """두 문장이 같은 내용인지. 띄어쓰기를 뺀 두 글자 묶음이 절반 넘게 겹치면 같다고 본다."""
    left, right = _bigrams(note), _bigrams(check)
    return bool(left and right) and len(left & right) / min(len(left), len(right)) > REPEAT_OVERLAP


def _bigrams(text: str) -> set[str]:
    compact = _PUNCTUATION.sub("", text)
    return {compact[i : i + 2] for i in range(len(compact) - 1)}


def _check_notes(data: ReportInput, profiles: Profiles) -> list[str]:
    """합격자의 확인할 점 중 원문 근거가 있는 것을 특이사항으로 옮긴다. 모델이 빠뜨려도 남게 코드가 넣는다.

    근거가 없는 항목(점수가 빈 영역, 답변을 기록하지 않은 질문)은 분석 Agent가 코드로 적은 사실이라 옮기지 않는다.
    """
    notes = []
    for finalist in data.finalists:
        checks = [
            note for note in _notes_of(profiles, finalist) if note.category is ItemCategory.CHECK and note.evidence
        ]
        notes += [f"{finalist.name}: {note.content} ({note.source})" for note in checks[:CHECK_NOTES_PER_FINALIST]]
    return _usable(notes, allowed_numbers=_numbers_in(data, profiles))


def _finalist(
    finalist: FinalistInput, notes: Sequence[ProfileNote], drafts: list[FinalistDraft], allowed_numbers: set[str]
) -> Finalist:
    allowed_sources = _allowed_sources(finalist, notes)
    draft = next((draft for draft in drafts if draft.name.strip() == finalist.name), None)
    if draft is not None and _usable([draft.reason], allowed_numbers):
        sources = _dedupe(source for source in draft.sources if source in allowed_sources)
        if sources:
            return Finalist(name=finalist.name, reason=draft.reason.strip(), sources=sources)
    return _fallback_finalist(finalist, notes)


def _allowed_sources(finalist: FinalistInput, notes: Sequence[ProfileNote]) -> set[str]:
    """그 합격자의 reason에 쓸 수 있는 출처. 분석 근거와 평가 · 면접 강점의 출처, 메모가 있으면 전형 메모다."""
    sources = {finding.source for finding in finalist.notable}
    sources |= {note.source for note in notes if note.category is ItemCategory.STRENGTH}
    if finalist.memos:
        sources.add(MEMO_SOURCE)
    return sources


def _fallback_finalist(finalist: FinalistInput, notes: Sequence[ProfileNote]) -> Finalist:
    """모델 문장을 쓸 수 없을 때. 근거 두 개까지를 자르지 않고 그대로 옮긴다 (StubReportAgent와 같다).

    서류 분석 근거가 없으면 평가 · 면접 강점을 쓴다.
    """
    strengths = [note for note in notes if note.category is ItemCategory.STRENGTH]
    picked = [(finding.text, finding.source) for finding in finalist.notable[:2]] or [
        (note.content, note.source) for note in strengths[:2]
    ]
    sources = _dedupe([finding.source for finding in finalist.notable] or [source for _, source in picked])
    if finalist.memos:
        sources.append(MEMO_SOURCE)
    reason = ", ".join(text for text, _ in picked) or NO_EVIDENCE
    return Finalist(name=finalist.name, reason=reason, sources=sources)


def _notes_of(profiles: Profiles, finalist: FinalistInput) -> Sequence[ProfileNote]:
    return profiles.get(finalist.application_id, ())


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


def _numbers_in(data: ReportInput, profiles: Profiles) -> set[str]:
    """입력에 나온 숫자. 지원서 · 기업 ID의 숫자는 리포트 근거가 아니라서 뺀다."""
    shown = data.model_dump_json(
        by_alias=True,
        exclude={"company_id": True, "recruitment_id": True, "finalists": {"__all__": {"application_id"}}},
    )
    texts = [shown, *(f"{note.content} {note.evidence or ''}" for notes in profiles.values() for note in notes)]
    return {number for text in texts for number in _NUMBER.findall(text)}


def _dedupe(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(items))
