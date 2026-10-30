"""Report Agent 스킬. 리포트 종류 · 전형 종류마다 '어떻게 잘 쓰는지'를 적은 지시문이다.

skills/<이름>.md 하나가 스킬 하나다. 맨 위 front matter에 name과 description을 적는다.
외부 스킬을 참고했으면 source에 출처를 적는다 (모델에는 보내지 않는다). 외부 스킬은 실행 중에 받아오지 않고,
검토한 내용을 우리 부품 이름과 규칙으로 고쳐 써서 넣는다.
Report Agent는 처음에 이름과 설명만 받고, 필요한 스킬만 load_skill 도구로 읽는다.
반드시 지킬 규칙(차별 조건, 숫자 참조, 순위 · 추천 금지)은 스킬이 아니라 system과 check.py에 둔다.
"""

from dataclasses import dataclass
from functools import cache
from importlib.resources import files


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str


@cache
def all_skills() -> dict[str, Skill]:
    skills = {}
    for entry in sorted(files(__package__).joinpath("skills").iterdir(), key=lambda item: item.name):
        if entry.name.endswith(".md"):
            skill = parse(entry.read_text(encoding="utf-8"))
            skills[skill.name] = skill
    return skills


def parse(text: str) -> Skill:
    """front matter(--- 사이의 name · description)와 본문을 나눈다."""
    _, header, body = text.split("---", 2)
    fields = dict(line.split(":", 1) for line in header.strip().splitlines())
    return Skill(name=fields["name"].strip(), description=fields["description"].strip(), body=body.strip())


def catalog() -> str:
    """system에 넣는 스킬 목록. 이름과 한 줄 설명뿐이다."""
    return "\n".join(f"- {skill.name}: {skill.description}" for skill in all_skills().values())
