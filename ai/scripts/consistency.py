"""Application Agent 일관성 측정. 서류 평가 데이터셋(scripts/demo/fixtures)의 지원자를 같은 입력으로 여러 번 분석해
칸마다 같은 판정이 나온 비율과, 중점 평가 항목 등급이 정답표(answer-key.json)와 맞는 비율을 잰다.

사용법 (ai 폴더에서, ai/.env의 모델로 실제로 부른다):
    uv run python scripts/consistency.py --runs 3
    uv run python scripts/consistency.py --runs 2 --limit 5 --out consistency.json

- 저장된 분석 · 문장 분석 결과를 다시 쓰지 않고 매번 처음부터 분석한다. 모델 호출 기록은 DB에 남기지 않는다.
- 평가 기준은 backend application-fixtures.yml, 인재상은 아래 TALENTS(데모 회사 설정과 같은 글)다.
- 표기는 화면(표 보기)과 같다: 경험형 상 · 중 · 하 · 확인 필요, 인재상 행동 확인 · 일부 확인 · 미확인.
- 정답표는 채점에만 쓰고 모델에 넣지 않는다. 지원자는 모두 가상 인물이다.
"""

import argparse
import asyncio
import json
import time
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

import yaml

from hiremate_ai.agents.analysis.application.graph import ReviewInput, run_review
from hiremate_ai.agents.analysis.application.service import match_criteria
from hiremate_ai.agents.analysis.application.table import judge_talents
from hiremate_ai.agents.analysis.application.types import (
    ApplicationReview,
    Criterion,
    CriterionResult,
    EvaluationRules,
    ScreeningRubric,
)
from hiremate_ai.config import settings
from hiremate_ai.contract import (
    AnalysisStatus,
    ApplicantDetail,
    ApplicantDocument,
    ApplicantInfo,
    CriterionCategory,
    CriterionType,
    DocumentType,
    PostingContent,
    Talent,
    TalentLevel,
    Verdict,
)
from hiremate_ai.llm.call_log import CallRecord
from hiremate_ai.llm.client import build_llm

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "scripts" / "demo" / "fixtures"
RUBRIC = ROOT / "backend" / "src" / "main" / "resources" / "application-fixtures.yml"
RECRUITMENT = UUID("00000000-0000-4000-8000-000000000030")
TODAY = date(2026, 11, 3)
# 정답표의 중점 평가 항목 이름 → 평가 기준 번호
FOCUS = {
    "API 개발·운영": "Q-01",
    "SQL 작성·DB 개선": "Q-02",
    "외부 연동 설계·구현": "P-01",
    "장애 분석·복구": "P-02",
    "빌드·배포 자동화": "P-03",
}
TALENTS = [
    Talent(
        title="협업",
        description="행동 확인: 의견 차이를 정리해 공유하고, 관계자와 기준을 합의함 / "
        "일부 확인: 의견 차이를 정리해 공유했지만, 이후 어떻게 조율했는지 확인되지 않음",
    ),
    Talent(
        title="고객 신뢰",
        description="행동 확인: 고객에게 미친 영향을 파악하고, 안내나 피해를 줄이는 조치를 직접 맡음 / "
        "일부 확인: 영향을 받은 거래를 확인했지만, 이후 본인이 맡은 대응은 확인되지 않음",
    ),
    Talent(
        title="끈기",
        description="행동 확인: 첫 시도가 막힌 뒤 접근을 바꾸고, 바꾼 방법의 효과를 확인함 / "
        "일부 확인: 첫 시도가 막힌 뒤 다른 방법을 시도했지만, 결과를 확인했는지는 기재되지 않음",
    ),
]
TALENT_MARKS = {
    TalentLevel.HIGH: "행동 확인",
    TalentLevel.MID: "일부 확인",
    TalentLevel.LOW: "미확인",
    TalentLevel.UNKNOWN: "확인 필요",
}


class MemoryCallLog:
    """모델 호출 기록을 DB 대신 메모리에 둔다 (호출 수만 센다)."""

    def __init__(self) -> None:
        self.records: list[CallRecord] = []

    async def record(self, record: CallRecord) -> None:
        self.records.append(record)


def load_criteria() -> list[Criterion]:
    raw = yaml.safe_load(RUBRIC.read_text(encoding="utf-8"))["hiremate"]["dummy"]["screening-rubric"]["criteria"]
    return [
        Criterion(
            criterion_id=item["criterion-id"],
            category=CriterionCategory(item["category"]),
            text=item["text"],
            important=item["important"],
            criterion_type=CriterionType(item["criterion-type"]),
            evaluation_rules=EvaluationRules(**item["evaluation-rules"]),
        )
        for item in raw
    ]


def posting_of(criteria: list[Criterion]) -> PostingContent:
    """평가 기준과 짝이 맞는 공고. 자격요건 · 우대사항 글은 평가 기준 글 그대로다 (seed.py --fixtures와 같다)."""
    return PostingContent(
        title="응용 소프트웨어 엔지니어 (백엔드)",
        job_category="백엔드 개발",
        employment_type="정규직",
        career="경력 무관",
        location="서울 중구",
        intro="결제 · 대출 · 보험 같은 서비스의 API와 외부 연동을 만들고 운영하는 백엔드 엔지니어를 찾습니다.",
        duties=["REST API 개발과 운영", "외부 시스템 연동 설계와 구현", "장애 대응과 빌드 · 배포 자동화"],
        qualifications=[c.text for c in criteria if c.category == CriterionCategory.QUALIFICATION],
        preferred=[c.text for c in criteria if c.category == CriterionCategory.PREFERENCE],
        benefits=["유연 근무", "자기계발비 지원"],
    )


def applicant_of(index: int, raw: dict[str, Any]) -> ApplicantDetail:
    documents = [
        ApplicantDocument(
            type=kind, file_id=uuid5(RECRUITMENT, f"{raw['email']}{kind}"), file_name="", size=1, text=raw[key]
        )
        for kind, key in (
            (DocumentType.RESUME, "resume"),
            (DocumentType.COVER_LETTER, "coverLetter"),
            (DocumentType.PORTFOLIO, "portfolio"),
        )
        if raw.get(key)
    ]
    info = ApplicantInfo(
        application_id=uuid5(RECRUITMENT, raw["email"]),
        recruitment_id=RECRUITMENT,
        application_no=index,
        name=raw["name"],
        email=raw["email"],
        career_years=None,
        last_company=None,
        analysis_status=AnalysisStatus.PENDING,
        submitted_at="2026-11-03T00:00:00Z",
    )
    return ApplicantDetail(info=info, phone="010-0000-0000", certificates=raw.get("certificates"), documents=documents)


def criterion_mark(result: CriterionResult) -> str:
    """화면 표기와 같은 규칙 (frontend table.ts criterionMark)."""
    condition = result.criterion_type == CriterionType.CONDITION
    if result.verdict == Verdict.MET:
        return "O" if condition else ("상" if result.metric else "중")
    if result.verdict == Verdict.PARTIAL:
        return "X" if condition else "중"
    if result.verdict == Verdict.NOT_MET:
        return "X" if condition else "하"
    return "확인 필요"


async def analyze(llm: Any, context: ReviewInput) -> dict[str, str]:
    """지원자 한 명을 한 번 분석해 칸 이름 → 표기를 돌려준다."""
    review: ApplicationReview = await run_review(llm, context)
    marks = {result.criterion_id: criterion_mark(result) for result in review.criteria}
    fit = await judge_talents(llm, review, TALENTS)
    marks |= {f"T:{item.title}": TALENT_MARKS[item.level] for item in fit.items}
    return marks


async def main() -> None:
    parser = argparse.ArgumentParser(description="Application Agent 일관성 측정")
    parser.add_argument("--runs", type=int, default=3, help="지원자마다 분석할 횟수")
    parser.add_argument("--limit", type=int, default=0, help="앞에서부터 이만큼만 (0이면 전원)")
    parser.add_argument("--concurrency", type=int, default=4, help="동시에 분석할 지원자 수")
    parser.add_argument("--out", type=Path, help="칸별 표기를 남길 JSON 파일")
    args = parser.parse_args()

    raws = json.loads((FIXTURES / "applicants.json").read_text(encoding="utf-8"))
    if args.limit:
        raws = raws[: args.limit]
    key = {item["id"]: item for item in json.loads((FIXTURES / "answer-key.json").read_text(encoding="utf-8"))}
    criteria = load_criteria()
    posting = posting_of(criteria)
    matched, notes = match_criteria(posting, rubric_of(criteria))
    log = MemoryCallLog()
    llm = build_llm(log, timeout=settings.worker_llm_timeout_seconds)
    gate = asyncio.Semaphore(args.concurrency)

    async def one(index: int, raw: dict[str, Any], run: int) -> tuple[str, int, dict[str, str]]:
        context = ReviewInput(
            applicant=applicant_of(index, raw),
            posting=posting,
            criteria=matched,
            criteria_version="fixtures-2026-11-03",
            notes=notes,
            input_hash=f"consistency-{run}",
            today=TODAY,
        )
        async with gate:
            marks = await analyze(llm, context)
        print(f"  {raw['name']} {run + 1}회차 끝", flush=True)
        return raw["note"].split()[0], run, marks

    started = time.monotonic()
    print(f"지원자 {len(raws)}명 × {args.runs}회 분석을 시작한다")
    done = await asyncio.gather(
        *(one(index, raw, run) for run in range(args.runs) for index, raw in enumerate(raws, start=1))
    )
    names = {raw["note"].split()[0]: raw["name"] for raw in raws}
    runs: dict[str, list[dict[str, str]]] = {hm: [{} for _ in range(args.runs)] for hm in names}
    for hm, run, marks in done:
        runs[hm][run] = marks
    report(runs, names, key, args.runs)
    print(f"\n모델 호출 {len(log.records)}번 · {time.monotonic() - started:.0f}초")
    if args.out:
        args.out.write_text(json.dumps({"runs": runs}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"칸별 표기: {args.out}")


def rubric_of(criteria: list[Criterion]) -> ScreeningRubric:
    return ScreeningRubric(
        company_id=RECRUITMENT,
        recruitment_id=RECRUITMENT,
        criteria_version="fixtures-2026-11-03",
        hire_count=1,
        criteria=criteria,
    )


def report(runs: dict[str, list[dict[str, str]]], names: dict[str, str], key: dict[str, Any], count: int) -> None:
    columns = sorted({column for marks in runs.values() for run in marks for column in run})
    print(f"\n[1] 칸 일치: {count}번 모두 같은 표기가 나온 칸의 비율")
    same_total = cells_total = 0
    changed: list[str] = []
    for column in columns:
        same = 0
        for hm, marks in runs.items():
            seen = [run.get(column, "없음") for run in marks]
            if len(set(seen)) == 1:
                same += 1
            else:
                changed.append(f"{hm} {names[hm]} · {column}: {' / '.join(seen)}")
        same_total += same
        cells_total += len(runs)
        print(f"  {column:<12} {same}/{len(runs)}")
    print(f"  전체 {same_total}/{cells_total} ({same_total / cells_total:.0%})")
    if changed:
        print("  흔들린 칸:")
        for line in changed:
            print(f"    {line}")

    print("\n[2] 정답 일치: 중점 평가 항목 등급이 정답표와 같은 비율 (회차별)")
    for run in range(count):
        hits = 0
        confusion: Counter[tuple[str, str]] = Counter()
        for hm, marks in runs.items():
            expected = key[hm]
            got = marks[run].get(FOCUS[expected["criterion"]], "없음")
            confusion[(expected["grade"], got)] += 1
            hits += got == expected["grade"]
        detail = ", ".join(f"정답 {want}→{got} {n}" for (want, got), n in sorted(confusion.items()) if want != got)
        print(f"  {run + 1}회차 {hits}/{len(runs)}" + (f" · 틀린 칸: {detail}" if detail else ""))


if __name__ == "__main__":
    asyncio.run(main())
