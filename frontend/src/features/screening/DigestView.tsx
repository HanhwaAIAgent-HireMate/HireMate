import type { CandidateAnalysis } from '@/features/screening/api'

type Digest = CandidateAnalysis['digests'][number]
type Section = Digest['sections'][number]
type Row = Section['rows'][number]

/**
 * 이력서 · 포트폴리오 정리 보기. AI가 서류에 적힌 것만 짧게 옮긴 표(경력 · 주요 경험)와 카드(포트폴리오 프로젝트:
 * 문제 · 해결 · 기술 · 성과), 기술 칩 · 자격 줄을 보여 준다. 원문 글은 보여 주지 않고, 원본은 PDF로 본다.
 */
export function DigestView({ digest }: { digest: Digest }) {
  return (
    <div className="space-y-5 text-[13px] leading-5">
      {digest.sections.map((section, index) => (
        <section key={index} className="space-y-2">
          <h4 className="flex items-center gap-2 text-sm font-semibold">
            <span className="h-3.5 w-1 rounded-full bg-ai" aria-hidden />
            {section.title}
          </h4>
          {section.layout === 'cards' ? (
            <Cards section={section} />
          ) : section.rows.length > 0 ? (
            <RowTable section={section} />
          ) : null}
          {section.tags.length > 0 && <Tags tags={section.tags} />}
          {section.items.length > 0 && (
            <ul className="space-y-0.5 text-muted-foreground">
              {section.items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  )
}

function RowTable({ section }: { section: Section }) {
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-left">
        <thead className="bg-muted/60 text-xs text-muted-foreground">
          <tr>
            {section.columns.map((column) => (
              <th key={column} className="px-3 py-1.5 font-medium whitespace-nowrap">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {section.rows.map((row, index) => (
            <tr key={index} className="border-t align-top">
              {section.columns.map((column, cellIndex) => (
                <td
                  key={column}
                  className={
                    cellIndex === 0 ? 'px-3 py-2 font-medium whitespace-nowrap' : 'px-3 py-2'
                  }
                >
                  <Cell value={row.cells[cellIndex]} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** 포트폴리오 프로젝트 카드. 문제 · 해결 다음에 기술 칩, 마지막에 성과를 둔다 */
function Cards({ section }: { section: Section }) {
  return (
    <ol className="space-y-2">
      {section.rows.map((row, index) => (
        <li key={index} className="rounded-lg border">
          <div className="flex items-center gap-2 border-b bg-muted/40 px-3 py-1.5">
            <span className="text-xs font-semibold text-ai">
              {String(index + 1).padStart(2, '0')}
            </span>
            <span className="min-w-0 flex-1 font-semibold">{row.title}</span>
          </div>
          <dl className="grid grid-cols-[3rem_1fr] gap-x-3 gap-y-1.5 px-3 py-2">
            {cardLines(section, row).map((line) => (
              <div key={line.label} className="contents">
                <dt className="text-xs leading-5 text-muted-foreground">{line.label}</dt>
                <dd className={line.strong ? 'font-medium' : undefined}>{line.value}</dd>
              </div>
            ))}
          </dl>
        </li>
      ))}
    </ol>
  )
}

function cardLines(section: Section, row: Row) {
  const lines = section.columns.map((label, index) => ({
    label,
    value: <Cell value={row.cells[index]} />,
    strong: label === '성과',
  }))
  const tags = row.tags ?? []
  if (tags.length > 0) {
    const at = lines.findIndex((line) => line.label === '성과')
    lines.splice(at < 0 ? lines.length : at, 0, {
      label: '기술',
      value: <Tags tags={tags} />,
      strong: false,
    })
  }
  return lines
}

function Tags({ tags }: { tags: string[] }) {
  return (
    <ul className="flex flex-wrap gap-1.5">
      {tags.map((tag) => (
        <li key={tag} className="rounded-full bg-ai-soft px-2.5 py-0.5 text-xs text-ai">
          {tag}
        </li>
      ))}
    </ul>
  )
}

function Cell({ value }: { value?: string }) {
  return value ? value : <span className="text-muted-foreground">-</span>
}
