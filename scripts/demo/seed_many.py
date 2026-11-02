# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.28", "fpdf2>=2.8"]
# ///
"""분포 리포트 데모 데이터: seed.py와 같은 공고에 가상 지원자 수백 명을 제출한다.

    uv run scripts/demo/seed_many.py --count 300 --headcount 6 --password <12자 이상>

지원자는 applicants.json의 30명 문서에서 줄을 지원자마다 다르게 빼 만든 가상 인물이다(이름도 지어낸 것이다).
실제 모델로 수백 명을 분석하면 몇 시간이 걸리므로 backend를 Application Agent stub(기본값)으로 띄워 둔다.
stub은 평가 항목 글의 낱말이 문서에 나오는 비율로 판정하므로, 판정은 분포 화면을 보기 위한 개발용 값이다.
공고 채용 인원(--headcount)을 넣어 분포 리포트의 서류 통과 목표 기본값(채용 인원 × 10)이 정해지게 한다.
"""

import argparse
import json
import os
import random
import sys
from pathlib import Path

from seed import FONTS, HERE, POSTING, Api, apply, login, publish, wait_for_analysis

SURNAMES = "김이박최정강조윤장임한오서신권황안송류홍"
GIVEN = ["민준", "서연", "도윤", "하은", "시우", "지유", "예준", "수아", "주원", "지아", "하준", "서윤", "지호", "채원"]


def variant(base: dict[str, str | None], index: int, rng: random.Random) -> dict[str, str | None]:
    """base 지원자 문서에서 줄을 지원자마다 다르게 빼 새 가상 지원자를 만든다. 첫 줄(이름 · 직무)은 남긴다."""
    keep = rng.uniform(0.35, 1.0)

    def thin(text: str | None) -> str | None:
        if not text:
            return text
        lines = text.split("\n")
        return "\n".join(lines[:1] + [line for line in lines[1:] if rng.random() < keep])

    name = rng.choice(SURNAMES) + rng.choice(GIVEN)
    return {
        "name": name,
        "email": f"demo{index:04d}@example.com",
        "certificates": base.get("certificates") if rng.random() < keep else None,
        "resume": thin(base["resume"]),
        "coverLetter": thin(base["coverLetter"]),
        "portfolio": thin(base.get("portfolio")) if rng.random() < keep else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="분포 리포트 데모 데이터를 넣는다")
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--app-url", default="http://localhost:5173", help="화면 주소 (frontend)")
    parser.add_argument("--email", default="demo-hr@example.com")
    parser.add_argument("--password", default=os.environ.get("HIREMATE_DEMO_PASSWORD"))
    parser.add_argument("--font", type=Path, help="한글 TTF 글꼴. 비우면 맑은 고딕 · 나눔고딕을 찾는다")
    parser.add_argument("--count", type=int, default=300, help="제출할 가상 지원자 수")
    parser.add_argument("--headcount", type=int, default=6, help="공고 채용 인원")
    parser.add_argument("--seed", type=int, default=7, help="같은 값이면 같은 지원자를 만든다")
    parser.add_argument("--wait-minutes", type=float, default=20)
    args = parser.parse_args()
    if not args.password:
        sys.exit("--password 또는 HIREMATE_DEMO_PASSWORD로 HR 비밀번호(12자 이상)를 준다")
    font = args.font or next((path for path in FONTS if path.exists()), None)
    if font is None:
        sys.exit("한글 글꼴을 찾지 못했다. --font로 TTF 파일을 준다")

    bases = json.loads((HERE / "applicants.json").read_text(encoding="utf-8"))
    rng = random.Random(args.seed)
    POSTING["headcount"] = args.headcount
    api = Api(args.base_url)
    login(api, args.email, args.password)
    recruitment_id, posting_id = publish(api)
    print(f"공고를 게시했다: {recruitment_id} (채용 인원 {args.headcount}명)")
    for index in range(1, args.count + 1):
        apply(args.base_url, posting_id, variant(bases[(index - 1) % len(bases)], index, rng), font)
        print(f"\r지원서 제출 {index}/{args.count}", end="", flush=True)
    print()
    closed = api.post(f"/api/recruitments/{recruitment_id}/posting/close").json()
    stage_id = closed["stages"][0]["id"]
    wait_for_analysis(api, stage_id, args.count, args.wait_minutes)
    print(f"서류 전형 화면: {args.app_url}/hr/recruitments/{recruitment_id}/stages/{stage_id}")


if __name__ == "__main__":
    main()
