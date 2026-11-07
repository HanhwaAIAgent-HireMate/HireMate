"""Synthetic PDF layout and manually specified reading order.

All text and achievements in these fixtures are fictitious. The expected order
describes how a person should read the page, not PDF object or extractor order.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class DrawText:
    x: int
    y: int
    text: str
    size: int = 11


@dataclass(frozen=True)
class ExpectedBlock:
    type: Literal["section", "paragraph", "list", "table", "reference"]
    value: str
    parent: str | None = None
    role: str | None = None


@dataclass(frozen=True)
class QualityCase:
    name: str
    document_type: str
    pages: list[list[DrawText]]
    reading_order: list[str]
    expected_blocks: list[ExpectedBlock]
    graph_page: int | None = None


CASES = [
    QualityCase(
        name="resume",
        document_type="RESUME",
        pages=[
            [
                DrawText(70, 748, "SAMPLE RESUME", 18),
                DrawText(70, 710, "Skills", 14),
                DrawText(70, 685, "Python"),
                DrawText(70, 665, "SQL"),
                DrawText(300, 710, "Work History", 14),
                DrawText(300, 685, "Orion Lab"),
                DrawText(300, 665, "Built a data pipeline 25% faster."),
                DrawText(70, 55, "SAMPLE RESUME | 1", 9),
            ]
        ],
        reading_order=[
            "SAMPLE RESUME",
            "Skills",
            "Python",
            "SQL",
            "Work History",
            "Orion Lab",
            "Built a data pipeline 25% faster.",
            "SAMPLE RESUME | 1",
        ],
        expected_blocks=[
            ExpectedBlock("section", "Skills"),
            ExpectedBlock("paragraph", "Python", "Skills", "body"),
            ExpectedBlock("paragraph", "SQL", "Skills", "body"),
            ExpectedBlock("section", "Work History"),
            ExpectedBlock("paragraph", "Orion Lab", "Work History", "body"),
            ExpectedBlock("paragraph", "Built a data pipeline 25% faster.", "Work History", "body"),
            ExpectedBlock("paragraph", "SAMPLE RESUME | 1", role="page_footer"),
        ],
    ),
    QualityCase(
        name="cover_letter",
        document_type="COVER_LETTER",
        pages=[
            [
                DrawText(70, 748, "C O V E R  L E T T E R", 18),
                DrawText(70, 710, "Motivation", 14),
                DrawText(70, 685, "I worked with users to improve a"),
                DrawText(70, 668, "booking process by 25%."),
                DrawText(70, 630, "I verified each change with data."),
                DrawText(70, 55, "SAMPLE LETTER | 1", 9),
            ]
        ],
        reading_order=[
            "C O V E R  L E T T E R",
            "Motivation",
            "I worked with users to improve a",
            "booking process by 25%.",
            "I verified each change with data.",
            "SAMPLE LETTER | 1",
        ],
        expected_blocks=[
            ExpectedBlock("section", "Motivation"),
            ExpectedBlock(
                "paragraph", "I worked with users to improve a booking process by 25%.", "Motivation", "body"
            ),
            ExpectedBlock("paragraph", "I verified each change with data.", "Motivation", "body"),
            ExpectedBlock("paragraph", "SAMPLE LETTER | 1", role="page_footer"),
        ],
    ),
    QualityCase(
        name="portfolio",
        document_type="PORTFOLIO",
        pages=[
            [
                DrawText(70, 748, "SAMPLE PORTFOLIO", 18),
                DrawText(70, 710, "Project Results", 14),
                DrawText(70, 680, "- Reduced wait time"),
                DrawText(70, 660, "- Improved reliability"),
                DrawText(70, 620, "Metric"),
                DrawText(240, 620, "Before"),
                DrawText(330, 620, "After"),
                DrawText(70, 600, "Latency"),
                DrawText(240, 600, "4.1s"),
                DrawText(330, 600, "2.3s"),
                DrawText(70, 580, "Failures"),
                DrawText(240, 580, "11"),
                DrawText(330, 580, "2"),
                DrawText(70, 278, "Performance chart", 10),
                DrawText(70, 55, "SAMPLE PORTFOLIO | 1", 9),
            ],
            [
                DrawText(70, 748, "SAMPLE PORTFOLIO", 12),
                DrawText(70, 710, "Implementation", 14),
                DrawText(70, 680, "The following code shows the calculation."),
                DrawText(70, 655, "def latency_ms(value):"),
                DrawText(90, 638, "return value * 1000"),
                DrawText(70, 55, "SAMPLE PORTFOLIO | 2", 9),
            ],
        ],
        reading_order=[
            "SAMPLE PORTFOLIO",
            "Project Results",
            "- Reduced wait time",
            "- Improved reliability",
            "Metric",
            "Before",
            "After",
            "Latency",
            "4.1s",
            "2.3s",
            "Failures",
            "11",
            "2",
            "Performance chart",
            "SAMPLE PORTFOLIO | 1",
            "SAMPLE PORTFOLIO",
            "Implementation",
            "The following code shows the calculation.",
            "def latency_ms(value):",
            "return value * 1000",
            "SAMPLE PORTFOLIO | 2",
        ],
        expected_blocks=[
            ExpectedBlock("section", "Project Results"),
            ExpectedBlock("list", "Reduced wait time|Improved reliability", "Project Results"),
            ExpectedBlock("table", "Metric|Before|After;Latency|4.1s|2.3s;Failures|11|2", "Project Results"),
            ExpectedBlock("reference", "Performance chart", "Project Results", "possible_visual"),
            ExpectedBlock("paragraph", "SAMPLE PORTFOLIO | 1", role="page_footer"),
            ExpectedBlock("paragraph", "SAMPLE PORTFOLIO", role="page_header"),
            ExpectedBlock("section", "Implementation"),
            ExpectedBlock("paragraph", "The following code shows the calculation.", "Implementation", "body"),
            ExpectedBlock("reference", "", "Implementation", "code_example"),
            ExpectedBlock("paragraph", "SAMPLE PORTFOLIO | 2", role="page_footer"),
        ],
        graph_page=1,
    ),
]


# This case starts at parser output so line-level normalization can be tested
# independently from PDF font extraction.
KOREAN_TEXT_CASE = QualityCase(
    name="korean_parser_text",
    document_type="COVER_LETTER",
    pages=[],
    reading_order=["자  기  소  개  서", "지원동기", "예약 변경 정책을", "데이터로 확인했습니다.", "지원서 1"],
    expected_blocks=[
        ExpectedBlock("paragraph", "자기소개서", role="body"),
        ExpectedBlock("section", "지원동기"),
        ExpectedBlock("paragraph", "예약 변경 정책을 데이터로 확인했습니다.", "지원동기", "body"),
        ExpectedBlock("paragraph", "지원서 1", role="page_footer"),
    ],
)


# The PDF is pre-generated on macOS with a system Korean font. The separately
# saved fixture is used everywhere; regenerating it requires that font.
KOREAN_PDF_CASE = QualityCase(
    name="korean",
    document_type=KOREAN_TEXT_CASE.document_type,
    pages=[
        [
            DrawText(70, 748, "자  기  소  개  서", 18),
            DrawText(70, 710, "지원동기", 14),
            DrawText(70, 685, "예약 변경 정책을"),
            DrawText(70, 668, "데이터로 확인했습니다."),
            DrawText(70, 55, "지원서 1", 9),
        ]
    ],
    reading_order=KOREAN_TEXT_CASE.reading_order,
    expected_blocks=KOREAN_TEXT_CASE.expected_blocks,
)

PDF_CASES = [*CASES, KOREAN_PDF_CASE]
