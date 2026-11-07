"""Generate small synthetic PDFs for document-structure evaluation.

Run from ai/: PYTHONPATH=tests uv run python -m eval.document_quality_fixtures
The source is deliberately self-contained so fixture generation needs no network
access or extra dependency. Coordinates are points measured from the bottom.
"""

from pathlib import Path

from eval.document_quality_gold import CASES, DrawText, QualityCase


def _literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _stream(lines: list[DrawText], *, graph: bool) -> bytes:
    operators = []
    for line in lines:
        operators.append(f"BT /F1 {line.size} Tf 1 0 0 1 {line.x} {line.y} Tm ({_literal(line.text)}) Tj ET")
    if graph:
        operators.extend(["70 300 240 70 re S", "100 310 25 20 re f", "160 310 25 40 re f", "220 310 25 55 re f"])
    return "\n".join(operators).encode("ascii")


def _pdf(case: QualityCase) -> bytes:
    objects: list[bytes] = []
    pages = case.pages
    page_ids = [4 + i * 2 for i in range(len(pages))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects.append(f"<< /Type /Pages /Count {len(pages)} /Kids [{kids}] >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for index, lines in enumerate(pages):
        stream = _stream(lines, graph=case.graph_page == index + 1)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {page_ids[index] + 1} 0 R >>".encode()
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    output = bytearray(b"%PDF-1.4\n%fixture\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)


def main() -> None:
    destination = Path(__file__).resolve().parents[1] / "samples"
    for case in CASES:
        path = destination / f"document_quality_{case.name}.pdf"
        path.write_bytes(_pdf(case))
        print(path.name)


if __name__ == "__main__":
    main()
