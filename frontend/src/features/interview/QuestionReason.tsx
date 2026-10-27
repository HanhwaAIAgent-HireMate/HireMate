import { ChevronDown, Info } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'

type Section = { label: string; value: string }

const BADGE_COLORS: Record<string, string> = {
  '직무 개념과 적용 판단': 'border-sky-200 bg-sky-50 text-sky-800',
  '가상 업무 상황 판단': 'border-violet-200 bg-violet-50 text-violet-800',
  '필수 조건 근거 없음': 'border-amber-200 bg-amber-50 text-amber-800',
  '우대 조건 근거 없음': 'border-amber-200 bg-amber-50 text-amber-800',
  '확인 필요': 'border-amber-200 bg-amber-50 text-amber-800',
  '주장만 있음': 'border-amber-200 bg-amber-50 text-amber-800',
  '본인 역할 확인': 'border-teal-200 bg-teal-50 text-teal-800',
  '사실 관계 확인': 'border-slate-200 bg-slate-50 text-slate-700',
  '이전 면접에서 확인 안 됨': 'border-indigo-200 bg-indigo-50 text-indigo-800',
}

const FIELD =
  /^(이 질문의 자리|이전 면접 질문|이전 면접 답변|질문 유형|확인할 내용|생성 방식|질문 기준(?: · 회사 인재상| · 조직 문화)?|출처|원문|기준 문구|공통 질문):\s*(.*)$/

// 저장된 표시 문구만 항목으로 나눈다. 없는 근거나 출처를 새로 만들지 않는다.
function sections(reason: string): Section[] {
  const result: Section[] = []
  for (const line of reason.split(/\r\n?|\n/)) {
    const match = FIELD.exec(line)
    if (match) result.push({ label: match[1], value: match[2] })
    else if (result.length) result[result.length - 1].value += `\n${line}`
    else result.push({ label: '참고 내용', value: line })
  }
  return result
}

export function QuestionReason({
  text,
  reason,
  source,
}: {
  text: string
  reason?: string | null
  source: 'AI' | 'MANUAL'
}) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const rows = reason ? sections(reason) : []
  const criterion = rows.find((row) => row.label === '질문 기준')
  const purpose = rows.find((row) => row.label === '확인할 내용')
  const type = rows.find((row) => row.label === '질문 유형')
  const method = rows.find((row) => row.label === '생성 방식')
  const slot = rows.find((row) => row.label === '이 질문의 자리')
  const material = rows.filter(
    (row) =>
      !['질문 기준', '확인할 내용', '질문 유형', '생성 방식', '이 질문의 자리'].includes(row.label),
  )
  const common = source === 'AI' && /^(?:Q\d+\. )?1분 자기소개 부탁드립니다\.$/.test(text)
  const hasMaterial = material.length > 0
  const samePurpose = !!criterion && !!purpose && criterion.value.trim() === purpose.value.trim()

  return (
    <div className="min-w-0 flex-1 text-sm">
      {type && !common && (
        <div className="mb-2">
          <ReasonBadge label="질문 유형" value={type.value} />
        </div>
      )}
      <p className="leading-relaxed font-semibold">{text}</p>
      <button
        type="button"
        aria-label="질문 생성 근거"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((value) => !value)}
        className={`mt-1 inline-flex min-h-7 items-center gap-1 rounded px-0.5 text-xs font-medium hover:text-ai focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none ${open ? 'text-ai' : 'text-muted-foreground'}`}
      >
        <Info className="size-3.5" aria-hidden="true" />
        근거
        <ChevronDown
          className={`size-3 transition-transform motion-reduce:transition-none ${open ? 'rotate-180' : ''}`}
          aria-hidden="true"
        />
      </button>
      <div id={id} hidden={!open} role="region" aria-label="질문 생성 근거">
        <div className="mt-1 space-y-4 rounded-xl border border-border/70 bg-muted/30 p-4 text-sm leading-relaxed text-foreground">
          {common ? (
            <>
              <ReasonSection label="근거">
                이 전형의 모든 지원자에게 똑같이 묻는 자기소개 질문입니다.
              </ReasonSection>
              <ReasonSection label="면접 확인 부분">
                지원자의 주요 경험과 지원 동기를 먼저 듣기 위한 질문입니다.
              </ReasonSection>
            </>
          ) : reason ? (
            <>
              {slot && (
                <div className="flex flex-wrap items-center gap-2">
                  <ReasonBadge label="이 질문의 자리" value={slot.value} />
                </div>
              )}
              <ReasonSection label="근거">
                {!hasMaterial && (
                  <p>
                    {criterion?.value ||
                      '이 질문에 연결된 원문이나 기준이 별도로 기록되지 않았습니다.'}
                  </p>
                )}
                {material.map((row, index) => {
                  if (
                    row.label === '출처' &&
                    ['원문', '기준 문구'].includes(material[index + 1]?.label)
                  )
                    return null
                  const previous = material[index - 1]
                  if (row.label === '원문' || row.label === '기준 문구')
                    return (
                      <div
                        key={index}
                        className="flex items-start gap-2 rounded-lg bg-background/80 px-3 py-2.5"
                      >
                        {previous?.label === '출처' && (
                          <span className="inline-flex shrink-0 rounded-full border bg-background px-2.5 py-0.5 text-xs leading-5 font-medium text-muted-foreground">
                            {previous.value === '자기소개서' ? '자소서' : previous.value}
                          </span>
                        )}
                        <blockquote className="min-w-0 flex-1 break-words whitespace-pre-wrap">
                          {row.value}
                        </blockquote>
                      </div>
                    )
                  return (
                    <ReasonSection
                      key={index}
                      label={row.label === '출처' ? '참고한 자료' : row.label}
                    >
                      {row.value}
                    </ReasonSection>
                  )
                })}
              </ReasonSection>
              <ReasonSection label="면접 확인 부분">
                {purpose && !(samePurpose && !hasMaterial)
                  ? purpose.value
                  : '구체적인 확인 목적은 별도로 기록되지 않았습니다.'}
              </ReasonSection>
              {method && <ReasonSection label="생성 방식">{method.value}</ReasonSection>}
            </>
          ) : (
            <ReasonSection
              label={source === 'MANUAL' ? '면접관이 직접 추가한 질문' : '기록된 근거가 없어요'}
            >
              {source === 'MANUAL'
                ? '담당자가 직접 추가한 질문입니다. AI 생성 근거는 없습니다.'
                : '이 질문은 생성 근거가 저장되기 전에 만들어졌습니다. 새로 생성하는 질문부터 근거를 확인할 수 있습니다.'}
            </ReasonSection>
          )}
        </div>
      </div>
    </div>
  )
}

function ReasonSection({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="mb-2 text-xs font-semibold text-ai">{label}</p>
      <div className="space-y-2 break-words whitespace-pre-wrap">{children}</div>
    </div>
  )
}

function ReasonBadge({ label, value }: { label: string; value: string }) {
  return (
    <span
      aria-label={`${label}: ${value}`}
      className={`inline-flex max-w-full items-center rounded-full border px-3 py-1 text-xs leading-5 font-medium ${BADGE_COLORS[value] || 'border-border bg-background text-muted-foreground'}`}
    >
      {value}
    </span>
  )
}
