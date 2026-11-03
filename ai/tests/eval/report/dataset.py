"""Report Agent 평가 자료. 정답 판정표(gold.json)로 backend와 같은 모양의 리포트 묶음 · 분포를 만든다.

묶음은 backend ReportBundles(결정 · AI 추천 · 항목 판정 · 지표)와 ai enrich(판정 이유 · 원문 근거)를 합친 모양이고,
분포는 backend ReportDistributions와 같은 규칙으로 센다. 그래서 평가 결과가 실제 화면과 같은 입력에서 나온다.
"""

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from hiremate_ai.agents.generation.report.bundle import (
    Area,
    BundleApplicant,
    BundleStage,
    Evidence,
    Fact,
    Metric,
    ReportBundle,
    ReportKind,
)
from hiremate_ai.agents.generation.report.explain import (
    CareerCount,
    CountBucket,
    CriterionCount,
    DistributionFacts,
    GroupCount,
    RequiredCount,
)
from hiremate_ai.agents.generation.report.strength import quote_strength
from hiremate_ai.contract import StageType

HERE = Path(__file__).resolve().parent
GOLD: dict[str, Any] = json.loads((HERE / "gold.json").read_text(encoding="utf-8"))
CASES: list[dict[str, Any]] = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))["cases"]

NAMESPACE = UUID("00000000-0000-4000-8000-0000000000bb")
COMPANY = uuid5(NAMESPACE, "company")
RECRUITMENT = uuid5(NAMESPACE, "recruitment")
STAGE = uuid5(NAMESPACE, "document-stage")
TITLE = "응용 소프트웨어 엔지니어 (백엔드)"
STAGE_NAME = "서류 전형"
AS_OF = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)
CONFIRMED = datetime(2026, 10, 27, 18, 0, tzinfo=UTC)

# backend와 같은 값: 필수 조건(중요 표시한 자격요건), 경력 구간, 다시 볼 지원자의 필수 조건 개수
REQUIRED = [c["criterionId"] for c in GOLD["criteria"] if c["criterionId"] in ("Q-01", "Q-02")]
CAREER_BANDS = [(0, 0), (1, 2), (3, 4), (5, 6), (7, 10**6)]
CAREER_LABELS = ["신입", "1~2년", "3~4년", "5~6년", "7년 이상"]
MAX_MISSING_REQUIRED = 1

VERDICT_WORDS = {"MET": "충족", "PARTIAL": "부분 충족", "NOT_MET": "미충족", "UNKNOWN": "확인 필요"}
_SOURCES = {"RESUME": "이력서", "COVER_LETTER": "자기소개서", "PORTFOLIO": "포트폴리오"}
_ROLES = {"SELF": "본인이 직접", "TEAM": "팀 · 조직의 성과", "UNCLEAR": "본인 역할 불분명"}
CRITERIA: dict[str, dict[str, Any]] = {c["criterionId"]: c for c in GOLD["criteria"]}
APPLICANTS: list[dict[str, Any]] = GOLD["applicants"]
BY_NAME: dict[str, dict[str, Any]] = {a["name"]: a for a in APPLICANTS}
BY_NUMBER: dict[str, dict[str, Any]] = {a["number"]: a for a in APPLICANTS}


def verdict(number: str, criterion_id: str) -> str:
    return str(BY_NUMBER[number]["criteria"][criterion_id]["verdict"])


def career_years(applicant: dict[str, Any]) -> int | None:
    """분석이 뽑은 경력 연수. 서류를 읽지 못하면 모른다."""
    if all(cell["verdict"] == "UNKNOWN" for cell in applicant["criteria"].values()):
        return None
    return int(applicant["careerYears"])


def met_count(applicant: dict[str, Any]) -> int:
    return sum(1 for cell in applicant["criteria"].values() if cell["verdict"] == "MET")


def missing_required(applicant: dict[str, Any]) -> list[str]:
    return [cid for cid in REQUIRED if applicant["criteria"][cid]["verdict"] != "MET"]


def above_line(applicant: dict[str, Any]) -> bool:
    return not missing_required(applicant)


def required_mark(applicant: dict[str, Any]) -> str:
    """backend ReportBundles.required와 같다: 모두 충족 MET, 미충족 · 부분이 하나라도 있으면 NOT_MET, 나머지 UNKNOWN."""
    missing = missing_required(applicant)
    if not missing:
        return "MET"
    marks = [applicant["criteria"][cid]["verdict"] for cid in missing]
    return "NOT_MET" if any(mark in ("NOT_MET", "PARTIAL") for mark in marks) else "UNKNOWN"


def stage_decisions() -> dict[str, str]:
    """전형 결과 리포트(S1)의 결정. 자격요건을 모두 충족하고 우대사항 충족도가 2 이상이면 합격, 나머지는 불합격이다."""
    credit = {"MET": 1.0, "PARTIAL": 0.5}
    decisions = {}
    for applicant in APPLICANTS:
        cells = applicant["criteria"]
        qualified = all(cells[cid]["verdict"] == "MET" for cid in cells if cid.startswith("Q-"))
        preference = sum(credit.get(cells[cid]["verdict"], 0.0) for cid in cells if cid.startswith("P-"))
        decisions[applicant["number"]] = "PASS" if qualified and preference >= 2 else "FAIL"
    return decisions


@dataclass(frozen=True)
class Case:
    id: str
    kind: str
    purpose: str
    targets: list[str]  # 지원자번호
    focus: str
    brief: bool
    target: int | None  # 분포의 서류 통과 목표
    forbid: list[str]  # 리포트 어디에도 나오면 안 되는 말
    no_splits: bool  # 판정이 갈린 항목이 없어야 한다


def cases() -> list[Case]:
    return [
        Case(
            id=raw["id"],
            kind=raw["kind"],
            purpose=raw["purpose"],
            targets=[BY_NAME[name]["number"] for name in raw.get("targets", [])],
            focus=raw.get("focus", ""),
            brief=raw.get("brief", False),
            target=raw.get("target"),
            forbid=raw.get("forbid", []),
            no_splits=raw.get("noSplits", False),
        )
        for raw in CASES
    ]


def bundle(case: Case) -> ReportBundle:
    """backend ReportBundles.build + ai enrich와 같은 묶음. 비교는 결정 전(PENDING), 전형 결과는 결정 확정 뒤다."""
    stage_report = case.kind == "STAGE"
    decisions = stage_decisions() if stage_report else {a["number"]: "PENDING" for a in APPLICANTS}
    facts: list[Fact] = []
    evidence: list[Evidence] = []
    for applicant in APPLICANTS:
        number = applicant["number"]
        for cid, cell in applicant["criteria"].items():
            facts.append(
                Fact(
                    id=f"{number}-document.criterion.{cid}",
                    applicant=number,
                    stage_id=STAGE,
                    key=f"document.criterion.{cid}",
                    label=f"{cid} {CRITERIA[cid]['text']}",
                    value=cell["verdict"],
                )
            )
        facts.append(
            Fact(
                id=f"{number}-document.decision",
                applicant=number,
                stage_id=STAGE,
                key="document.decision",
                label=f"{STAGE_NAME} 결정",
                value=decisions[number],
            )
        )
        facts.append(
            Fact(
                id=f"{number}-document.ai_pick",
                applicant=number,
                stage_id=STAGE,
                key="document.ai_pick",
                label="AI 추천",
                value="RECOMMENDED" if above_line(applicant) else "NOT_RECOMMENDED",
            )
        )
        evidence += [_evidence(number, cid, cell) for cid, cell in applicant["criteria"].items()]
    areas = [
        Area(
            id=category.lower(),
            label="자격요건" if category == "QUALIFICATION" else "우대사항",
            score_key=None,
            keys=[f"document.criterion.{c['criterionId']}" for c in GOLD["criteria"] if c["category"] == category],
        )
        for category in ("QUALIFICATION", "PREFERENCE")
    ]
    return ReportBundle(
        kind=ReportKind.STAGE if stage_report else ReportKind.COMPARE,
        company_id=COMPANY,
        recruitment_id=RECRUITMENT,
        stage_id=STAGE,
        title=TITLE,
        as_of=AS_OF,
        focus=case.focus,
        brief=case.brief,
        stages=[
            BundleStage(
                stage_id=STAGE,
                name=STAGE_NAME,
                type=StageType.DOCUMENT,
                confirmed_at=CONFIRMED if stage_report else None,
            )
        ],
        applicants=[
            BundleApplicant(
                number=a["number"],
                application_id=uuid5(NAMESPACE, a["email"]),
                career_years=career_years(a),
                last_company=a["lastCompany"],
            )
            for a in APPLICANTS
        ],
        targets=case.targets,
        total_key=None,
        areas=areas,
        metrics=_metrics(decisions),
        facts=facts,
        evidence=evidence,
    )


def _evidence(number: str, cid: str, cell: dict[str, Any]) -> Evidence:
    """enrich._evidence와 같다: 정량 원문을 먼저, 없으면 첫 원문을 고르고 그 서류를 출처로 쓴다."""
    quotes = cell["quotes"]
    quote = next((q for q in quotes if quote_strength(q["sentence"]) == "QUANT"), quotes[0] if quotes else None)
    return Evidence(
        id=f"e-{number}-{cid}",
        applicant=number,
        stage_id=STAGE,
        agent="application",
        text=cell["reason"],
        source=_SOURCES[quote["document"]] if quote else "서류 전체",
        quote=quote["sentence"] if quote else None,
        label=CRITERIA[cid]["text"],
        verdict=cell["verdict"],
        strength=quote_strength(quote["sentence"]) if quote else None,
        detail=f"역할 {_ROLES[cell['role']]}",
        role=cell["role"],
    )


def _metrics(decisions: dict[str, str]) -> list[Metric]:
    """backend ReportBundles.metrics와 같은 지표."""
    total = len(APPLICANTS)
    count = Counter(decisions.values())
    metrics = [
        Metric(id="m-target", stage_id=STAGE, label="대상", value=total, unit="명"),
        Metric(id="m-pass", stage_id=STAGE, label="합격", value=count["PASS"], unit="명"),
        Metric(id="m-fail", stage_id=STAGE, label="불합격", value=count["FAIL"], unit="명"),
        Metric(id="m-pending", stage_id=STAGE, label="미결정", value=count["PENDING"], unit="명"),
        Metric(id="m-pass-rate", stage_id=STAGE, label="합격률", value=round(100 * count["PASS"] / total, 1), unit="%"),
    ]
    marks = Counter(required_mark(a) for a in APPLICANTS)
    for mark, metric_id, label in (
        ("MET", "m-req-met", "필수 조건 충족"),
        ("NOT_MET", "m-req-unmet", "필수 조건 미충족"),
        ("UNKNOWN", "m-req-unknown", "필수 조건 확인 필요"),
    ):
        metrics.append(
            Metric(id=metric_id, stage_id=STAGE, label=label, value=marks[mark], unit="명", group="required-judgement")
        )
    passed = [a for a in APPLICANTS if decisions[a["number"]] == "PASS"]
    for group, label, people in (("all", "전체", APPLICANTS), ("pass", "합격자", passed)):
        if not people:
            continue
        for band, (low, high) in enumerate(CAREER_BANDS):
            inside = [a for a in people if (years := career_years(a)) is not None and low <= years <= high]
            metrics.append(
                Metric(
                    id=f"m-career-{group}-{band}",
                    stage_id=STAGE,
                    label=f"{label} {CAREER_LABELS[band]}",
                    value=len(inside),
                    unit="명",
                    group=f"career-{group}",
                )
            )
    return metrics


def distribution(target: int) -> DistributionFacts:
    """backend ReportDistributions.build(...).forAi()와 같은 분포. 정렬 기준은 기본(BASIC: 충족 개수)이다."""
    above = sorted((a for a in APPLICANTS if above_line(a)), key=met_count, reverse=True)
    cut: dict[str, int] | None = None
    groups: list[GroupCount] = []
    if len(above) > target:
        value = met_count(above[target - 1])
        first = next(i for i, a in enumerate(above) if met_count(a) == value)
        last = max(i for i, a in enumerate(above) if met_count(a) == value)
        cut = {"value": value, "from": first + 1, "to": last + 1, "inside": target - first}
        groups.append(
            GroupCount(
                label="목표 인원에서 동점인 지원자",
                reason=f"필수 조건 충족자 중 목표 {target}명째와 충족 개수({value}개)가 같은 지원자예요. "
                "개수로는 구분되지 않아요.",
                size=last - first + 1,
            )
        )
    below = [a for a in APPLICANTS if not above_line(a) and 0 < len(missing_required(a)) <= MAX_MISSING_REQUIRED]
    groups.append(
        GroupCount(
            label="필수 조건을 조금 못 채운 지원자",
            reason=f"필수 조건 중 못 채웠거나 확인이 필요한 것이 {MAX_MISSING_REQUIRED}개 이하인 지원자예요.",
            size=len(below),
        )
    )
    marks = Counter(required_mark(a) for a in APPLICANTS)
    criteria = []
    for cid, criterion in CRITERIA.items():
        found = Counter(a["criteria"][cid]["verdict"] for a in APPLICANTS)
        criteria.append(
            CriterionCount(
                criterion_id=cid,
                text=criterion["text"],
                required=cid in REQUIRED,
                met=found["MET"],
                partial=found["PARTIAL"],
                not_met=found["NOT_MET"],
                unknown=found["UNKNOWN"],
            )
        )
    careers = []
    for band, (low, high) in enumerate(CAREER_BANDS):
        inside = [a for a in APPLICANTS if (years := career_years(a)) is not None and low <= years <= high]
        careers.append(CareerCount(label=CAREER_LABELS[band], all=len(inside), above_line=sum(map(above_line, inside))))
    buckets = Counter(met_count(a) for a in above)
    return DistributionFacts(
        total=len(APPLICANTS),
        analyzed=len(APPLICANTS),
        above_line=len(above),
        target=target,
        passed=0,
        required=RequiredCount(met=marks["MET"], unmet=marks["NOT_MET"], unknown=marks["UNKNOWN"]),
        criteria=criteria,
        groups=groups,
        careers=careers,
        counts=[CountBucket(value=value, count=buckets[value]) for value in sorted(buckets, reverse=True)],
        cut=cut,
    )


def expected_splits(targets: list[str]) -> dict[str, dict[str, str]]:
    """비교 대상끼리 판정이 갈린 항목 → 지원자번호별 판정. derive.split_keys와 같은 뜻이다."""
    found = {}
    for cid in CRITERIA:
        marks = {number: verdict(number, cid) for number in targets}
        if len(set(marks.values())) > 1:
            found[cid] = marks
    return found
