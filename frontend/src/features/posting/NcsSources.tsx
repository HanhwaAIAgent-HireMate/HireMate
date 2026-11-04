import { BookOpen, ChevronDown } from 'lucide-react'

import type { NcsSource } from '@/features/posting/api'

const FIELD_ORDER = ['duties', 'qualifications', 'preferred']
const FIELD_LABELS: Record<string, string> = {
  duties: '주요 업무',
  qualifications: '자격 요건',
  preferred: '우대 사항',
}

/**
 * 수정안이 참고한 NCS 출처. 공고 줄마다 그 줄을 받쳐 준 NCS 원문을 보여 준다.
 * NCS는 HR이 보고 판단하는 참고자료라 공고에는 들어가지 않고 이 답에만 보인다.
 * 화면 순서(주요 업무 → 자격 요건 → 우대 사항, 줄 순서)로 늘어놓고, 처음에는 펼쳐 둔다.
 */
export function NcsSources({ sources }: { sources: NcsSource[] }) {
  if (sources.length === 0) return null
  const sorted = [...sources].sort(
    (a, b) => FIELD_ORDER.indexOf(a.field) - FIELD_ORDER.indexOf(b.field) || a.number - b.number,
  )
  return (
    <details open className="group rounded-lg border bg-muted/40">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium [&::-webkit-details-marker]:hidden">
        <BookOpen className="size-3.5 text-ai" />
        참고한 NCS {sources.length}건
        <ChevronDown className="ml-auto size-3.5 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>
      <ul className="divide-y border-t">
        {sorted.map((source) => (
          <li
            key={`${source.field}-${source.number}`}
            data-testid="ncs-source"
            className="space-y-1 px-2.5 py-2"
          >
            <div className="flex items-start gap-1.5">
              <span className="shrink-0 rounded bg-ai-soft px-1.5 py-0.5 text-[11px] font-medium text-ai">
                {FIELD_LABELS[source.field] ?? source.field} {source.number}
              </span>
              <span className="line-clamp-2 text-xs">{source.line}</span>
            </div>
            <p className="text-[11px] text-muted-foreground">
              {source.dutyName} › {source.unitName} › {source.taskName}
            </p>
            <blockquote className="border-l-2 border-ai/40 pl-2 text-xs leading-relaxed text-muted-foreground">
              {source.sentence}
            </blockquote>
          </li>
        ))}
      </ul>
    </details>
  )
}
