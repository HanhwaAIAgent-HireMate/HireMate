"""Report Agent 평가 자동 채점과 사람 채점표. 모델 없이 돌아서 채점 규칙 자체를 단위 테스트로 검사한다.

자동 채점은 코드가 확실히 셀 수 있는 것만 센다 (판정이 갈린 항목, 판정 표현, 근거 연결, 금지 표현, 숫자).
문장이 원문을 과장했는지 같은 판단은 사람 채점표(review.csv)로 사람이 본다.
"""

import csv
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hiremate_ai.agents.generation.report.bundle import ReportBundle
from hiremate_ai.agents.generation.report.check import problems
from hiremate_ai.agents.generation.report.compose import ComposedReport
from hiremate_ai.agents.generation.report.explain import DistributionFacts, DistributionNote
from hiremate_ai.agents.generation.report.fallback import MAX_SPLITS
from hiremate_ai.agents.generation.report.spec import EvidenceBlock, ReportSpec, TextBlock
from hiremate_ai.agents.guardrails import blocked_attribute

from .dataset import BY_NUMBER, CRITERIA, VERDICT_WORDS, Case, expected_splits

# 목표값 (README의 '평가 기준'). 숫자 · 근거 연결 · 금지 표현은 하나도 틀리면 안 된다
TARGETS = {
    "split_recall": 0.95,
    "split_precision": 0.95,
    "verdict_accuracy": 0.95,
    "linkage": 1.0,
    "first_pass": 0.7,
    "fallback_rate": 0.1,
}
REVIEW_LABELS = ("맞음", "과장", "틀림", "근거 없음", "어색함")

_APPLICANT = re.compile(r"A-\d{4}")
_CODE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{1,3}-\d+(?!\d)")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
# 판정 표현. 긴 말부터 찾아야 '부분 충족' · '미충족'을 '충족'으로 읽지 않는다
_VERDICT = re.compile(r"부분\s*충족|부분 판정|미충족|확인\s*필요|충족")
_VERDICT_CODES = {"부분": "PARTIAL", "미충족": "NOT_MET", "확인": "UNKNOWN", "충족": "MET"}
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_TEXT_PROBLEMS = (
    "순위나 추천",
    "쓰면 안 되는 조건",
    "판정 코드",
    "해요체",
    "묶음에 없는 숫자",
    "범위 밖 지원자번호",
    "내부 용어",
)


@dataclass
class Sentence:
    """리포트 문장 하나. where는 위치(요약 · 섹션 · 판정이 갈린 이유 · 차트), evidence는 인용한 근거 id다."""

    where: str
    text: str
    evidence: list[str] = field(default_factory=list)
    applicant: str | None = None
    criterion: str | None = None


@dataclass
class RunScore:
    case: str
    run: int
    kind: str
    fallback: bool = False
    first_pass: bool = False
    split_hit: int = 0
    split_extra: int = 0
    split_missed: int = 0
    split_hidden: int = 0
    verdict_claims: int = 0
    verdict_hits: int = 0
    links: int = 0
    links_ok: int = 0
    violations: list[str] = field(default_factory=list)
    misplaced: list[str] = field(default_factory=list)
    """분포 차트 해설에 쓴, 자료에는 있지만 그 차트에는 없는 숫자. 근거 연결만 깎고 위반으로는 세지 않는다."""
    rewrites: list[str] = field(default_factory=list)
    sentences: list[Sentence] = field(default_factory=list)


def report_sentences(spec: ReportSpec) -> list[Sentence]:
    """모델이 쓴 문장. 제목과 부품 설명(caption)은 빼고, 판단이 들어간 문장만 모은다."""
    found = [Sentence("요약", spec.summary)]
    for index, section in enumerate(spec.sections, start=1):
        found.append(Sentence(f"섹션{index} '{section.title}' 읽을 점", section.takeaway))
        for block in section.blocks:
            if isinstance(block, TextBlock):
                found.append(Sentence(f"섹션{index} 글", block.text, list(block.evidence)))
            if isinstance(block, EvidenceBlock):
                for item in block.items:
                    words = " · ".join(item.keywords) + (f" / {item.text}" if item.text else "")
                    found.append(Sentence(f"섹션{index} 근거 키워드", words, list(item.evidence), item.applicant))
    for split in spec.splits:
        criterion = split.key.rsplit(".", 1)[-1]
        found.append(Sentence(f"판정이 갈린 이유 {criterion}", split.text, list(split.evidence), criterion=criterion))
    return [sentence for sentence in found if sentence.text.strip()]


def verdict_claims(text: str) -> list[tuple[str, str]]:
    """문장에서 '지원자번호 … 판정 표현'을 짝지은 것. 다음 지원자번호가 나오기 전의 첫 판정 표현을 그 지원자 것으로
    본다.

    'A-0004와 A-0006은 부분 충족'처럼 여럿을 묶어 말하면 묶인 지원자 모두에 그 표현을 붙인다.
    """
    claims: list[tuple[str, str]] = []
    waiting: list[str] = []
    position = 0
    tokens = sorted(
        [(m.start(), "applicant", m.group()) for m in _APPLICANT.finditer(text)]
        + [(m.start(), "verdict", m.group()) for m in _VERDICT.finditer(text)]
    )
    for start, kind, value in tokens:
        if start < position:
            continue
        if kind == "applicant":
            gap = text[position:start]
            # 번호 사이가 '와 · 과 · ,'처럼 묶는 말뿐이면 같은 표현을 나눠 쓴다
            if waiting and not re.fullmatch(r"[\s()가-힣]{0,4}(?:와|과|,|·|및)\s*", gap):
                waiting = []
            waiting.append(value)
        elif waiting:
            code = next(code for word, code in _VERDICT_CODES.items() if value.replace(" ", "").startswith(word))
            claims += [(number, code) for number in waiting]
            waiting = []
        position = start + len(value)
    return claims


def plain_endings(text: str) -> list[str]:
    """평어(~다.)로 끝난 문장. 리포트 문장은 해요체(~어요 · ~예요)로 쓴다. ~니다는 check가 따로 잡는다."""
    return [
        part.strip()
        for part in _SENTENCE_END.split(text.strip())
        if re.search(r"[가-힣]다[.)\]]*$", part.strip()) and not re.search(r"니다[.)\]]*$", part.strip())
    ]


def score_report(case: Case, bundle: ReportBundle, composed: ComposedReport, run: int) -> RunScore:
    score = RunScore(case.id, run, case.kind, fallback=composed.fallback)
    score.first_pass = any("1번째에 통과" in step for step in composed.steps)
    spec = composed.spec
    score.sentences = report_sentences(spec)
    if case.kind == "COMPARE" and not case.brief:
        expected = expected_splits(case.targets)
        predicted = {split.key.rsplit(".", 1)[-1] for split in spec.splits}
        score.split_hit = len(predicted & set(expected))
        score.split_extra = len(predicted - set(expected))
        # '판정이 갈린 이유'는 MAX_SPLITS개까지만 보여 준다 (설계). 넘친 항목은 놓친 것이 아니라 숨겨진 것으로 따로 센다
        score.split_missed = max(0, min(len(expected), MAX_SPLITS) - score.split_hit)
        score.split_hidden = max(0, len(expected) - MAX_SPLITS)
    targets = set(case.targets)
    evidence_ids = {item.id for item in bundle.evidence}
    for sentence in score.sentences:
        for number, code in verdict_claims(sentence.text):
            if sentence.criterion is None or number not in BY_NUMBER:
                continue
            score.verdict_claims += 1
            score.verdict_hits += BY_NUMBER[number]["criteria"][sentence.criterion]["verdict"] == code
        for evidence_id in sentence.evidence:
            score.links += 1
            # 근거 id는 e-{지원자번호}-{항목} (dataset._evidence)
            owner, criterion = evidence_id.removeprefix("e-")[:6], evidence_id.removeprefix("e-")[7:]
            ok = evidence_id in evidence_ids and owner in (targets or {owner})
            if sentence.applicant is not None:
                ok = ok and owner == sentence.applicant
            if sentence.criterion is not None:
                ok = ok and criterion == sentence.criterion
            score.links_ok += ok
    found = [problem for problem in problems(spec, bundle) if any(word in problem for word in _TEXT_PROBLEMS)]
    score.violations += found
    score.violations += _common_violations(case, score.sentences)
    return score


def score_distribution(case: Case, facts: DistributionFacts, note: DistributionNote, run: int) -> RunScore:
    score = RunScore(case.id, run, case.kind)
    allowed = chart_numbers(facts)
    score.sentences = [Sentence("전체 해설", line) for line in note.lines]
    score.sentences += [Sentence(f"차트 {chart}", text, criterion=chart) for chart, text in note.charts.items()]
    score.first_pass = bool(note.lines)
    score.fallback = not note.lines
    # 다시 볼 지원자 인원은 차트가 아닌 칸에 나오지만 화면에 보이는 자료다
    everything = set().union(*allowed.values()) | {str(group.size) for group in facts.groups}
    for sentence in score.sentences:
        chart = sentence.criterion
        numbers = set(_NUMBER.findall(_CODE.sub("", sentence.text)))
        score.links += len(numbers)
        good = numbers & (allowed[chart] if chart else everything)
        score.links_ok += len(good)
        # 자료 어디에도 없는 숫자는 위반이고, 다른 차트 · 칸의 숫자는 근거 연결만 깎는다
        if made_up := sorted(numbers - everything):
            score.violations.append(f"{sentence.where}: 자료에 없는 숫자 {', '.join(made_up)}")
        if elsewhere := sorted((numbers & everything) - good):
            score.misplaced.append(f"{sentence.where}: 다른 차트의 숫자 {', '.join(elsewhere)}")
    score.violations += [f"차트 {chart} 해설이 빠졌다" for chart in allowed if chart not in note.charts]
    score.violations += _common_violations(case, score.sentences)
    return score


def _common_violations(case: Case, sentences: list[Sentence]) -> list[str]:
    found = []
    for sentence in sentences:
        if attribute := blocked_attribute(_CODE.sub("", sentence.text)):
            found.append(f"{sentence.where}: 차별 조건 '{attribute}'")
        for word in case.forbid:
            if word in sentence.text:
                found.append(f"{sentence.where}: 금지 표현 '{word}'")
        if "키워드" not in sentence.where:
            found += [f"{sentence.where}: 평어 '{part}'" for part in plain_endings(sentence.text)]
    return found


def _share(part: int, whole: int) -> str:
    return str(round(100 * part / whole)) if whole else "0"


def chart_numbers(facts: DistributionFacts) -> dict[str, set[str]]:
    """차트마다 그 차트 문장에 써도 되는 숫자. 비율은 explain.facts_text와 같은 반올림이다."""
    funnel = {facts.total, facts.analyzed, facts.above_line, facts.target, abs(facts.above_line - facts.target)}
    funnel |= {facts.passed} if facts.passed is not None else set()
    shares = {_share(value, facts.total) for value in (facts.analyzed, facts.above_line, facts.target)}
    required = facts.required
    whole = required.met + required.unmet + required.unknown
    counts: set[int] = {facts.target, facts.above_line}
    for bucket in facts.counts:
        counts |= {bucket.value, bucket.count}
    if facts.cut:
        cut = facts.cut
        counts |= set(cut.values()) | {cut["to"] - cut["from"] + 1}
    criteria: set[str] = set()
    for item in facts.criteria:
        judged = item.met + item.partial + item.not_met + item.unknown
        criteria |= {str(v) for v in (item.met, item.partial, item.not_met, item.unknown, judged)}
        criteria |= {_share(item.partial + item.not_met + item.unknown, judged), _share(item.unknown, judged)}
        criteria |= {_share(item.not_met + item.partial, judged)}
    careers: set[str] = {"1", "2", "3", "4", "5", "6", "7"}  # 구간 이름(1~2년 · 7년 이상)의 숫자
    for band in facts.careers:
        careers |= {str(band.all), str(band.above_line), _share(band.above_line, band.all)}
    return {
        "funnel": {str(v) for v in funnel} | shares,
        "required": {str(v) for v in (required.met, required.unmet, required.unknown, whole)}
        | {_share(v, whole) for v in (required.met, required.unmet, required.unknown)},
        "counts": {str(v) for v in counts},
        "criteria": criteria,
        "careers": careers,
    }


def summarize(scores: list[RunScore]) -> dict[str, float | None]:
    """전체 지표. 나눌 값이 없으면(잴 문장이 없었으면) None이고, 목표 비교에서 뺀다."""

    def ratio(part: float, whole: float) -> float | None:
        return part / whole if whole else None

    hit = sum(s.split_hit for s in scores)
    reports = [s for s in scores if s.kind != "DISTRIBUTION"]
    return {
        "split_recall": ratio(hit, hit + sum(s.split_missed for s in scores)),
        "split_precision": ratio(hit, hit + sum(s.split_extra for s in scores)),
        "verdict_accuracy": ratio(sum(s.verdict_hits for s in scores), sum(s.verdict_claims for s in scores)),
        "linkage": ratio(sum(s.links_ok for s in scores), sum(s.links for s in scores)),
        "first_pass": ratio(sum(s.first_pass for s in scores), len(scores)),
        "fallback_rate": ratio(sum(s.fallback for s in reports), len(reports)) if reports else 0.0,
        "violations": float(sum(len(s.violations) for s in scores)),
        "verdict_claims": float(sum(s.verdict_claims for s in scores)),
        "splits_hidden": float(sum(s.split_hidden for s in scores)),
    }


def review_rows(case: Case, bundle: ReportBundle | None, score: RunScore) -> Iterable[dict[str, Any]]:
    """사람 채점표의 줄. 문장마다 인용한 원문과 정답 판정을 옆에 붙인다. '사람 판정' 칸만 사람이 채운다."""
    evidence = {item.id: item for item in bundle.evidence} if bundle else {}
    for sentence in score.sentences:
        cited = []
        for evidence_id in sentence.evidence:
            item = evidence.get(evidence_id)
            if item is not None:
                mark = VERDICT_WORDS.get(item.verdict or "", "")
                cited.append(f"[{item.applicant} {item.label} · {mark}] {item.quote or '(원문 없음)'}")
        gold = []
        criteria = [sentence.criterion] if sentence.criterion in CRITERIA else list(CRITERIA)
        for number in dict.fromkeys(
            _APPLICANT.findall(sentence.text) + ([sentence.applicant] if sentence.applicant else [])
        ):
            if number in BY_NUMBER:
                marks = ", ".join(
                    f"{cid} {VERDICT_WORDS[BY_NUMBER[number]['criteria'][cid]['verdict']]}" for cid in criteria
                )
                gold.append(f"{number}({BY_NUMBER[number]['name']}): {marks}")
        yield {
            "사례": case.id,
            "회차": score.run,
            "사례 목적": case.purpose,
            "위치": sentence.where,
            "문장": sentence.text,
            "인용한 원문": "\n".join(cited),
            "정답 판정": "\n".join(gold),
            "사람 판정": "",
            "메모": "",
        }


def write_review(path: Path, rows: list[dict[str, Any]]) -> None:
    """엑셀에서 한글이 깨지지 않게 BOM을 붙인 UTF-8로 쓴다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]) if rows else ["사례"])
        writer.writeheader()
        writer.writerows(rows)
