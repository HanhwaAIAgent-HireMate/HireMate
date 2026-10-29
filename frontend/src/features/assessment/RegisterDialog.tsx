import { AlertTriangle, ArrowRight, Check, FileSpreadsheet, FileUp, Link2 } from 'lucide-react'
import { useRef, useState, type ReactNode } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  NCS_AREAS,
  useAttachResultFile,
  useImportResults,
  usePreviewTable,
  useSaveResult,
  type IdentifierType,
  type ImportRow,
  type TablePreview,
} from '@/features/assessment/api'
import { careerLabel, useAllCandidates, type StageOverview } from '@/features/screening/api'
import { errorMessage } from '@/lib/api/client'
import { cn } from '@/lib/utils'

type Method = 'TABLE' | 'FILE' | 'MANUAL' | 'SUBMISSION'

const METHODS: { key: Method | 'API'; label: string; hint: string }[] = [
  { key: 'TABLE', label: '결과표 업로드', hint: 'CSV · XLSX' },
  { key: 'FILE', label: '결과 파일 업로드', hint: '지원자별 리포트' },
  { key: 'MANUAL', label: '지원자별 수동 입력', hint: '점수 · 등급 · 메모' },
  { key: 'SUBMISSION', label: '제출 파일 · URL', hint: '과제형 전형' },
  { key: 'API', label: 'API · Webhook', hint: '외부 서비스 연동' },
]

const TARGETS = [
  { value: 'EMAIL', label: '지원자 매칭 키 (이메일)' },
  { value: 'APPLICATION_NO', label: '지원자 매칭 키 (지원번호)' },
  ...NCS_AREAS.map((area) => ({ value: area, label: area })),
  { value: 'TOTAL', label: '총점 (0~100)' },
  { value: 'GRADE', label: '등급' },
  { value: 'SKIP', label: '사용 안 함' },
] as const

/** 열 이름으로 결과 항목을 짐작한다. */
function guess(column: string): string {
  const name = column.replace(/\s/g, '')
  if (/이메일|email/i.test(name)) return 'EMAIL'
  if (/지원번호|번호|no/i.test(name)) return 'APPLICATION_NO'
  if (/총점|합계|total/i.test(name)) return 'TOTAL'
  if (/등급|grade/i.test(name)) return 'GRADE'
  const area = NCS_AREAS.find(
    (item) => item.startsWith(name.replace(/능력$/, '')) || name.startsWith(item.slice(0, 2)),
  )
  return area ?? 'SKIP'
}

/** 파일 열 이름이 10자를 넘으면 10자까지만 보이고 … 을 붙인다. 전체 이름은 마우스를 올리면 보인다. */
const COLUMN_NAME_LIMIT = 10
const shorten = (name: string) =>
  name.length > COLUMN_NAME_LIMIT ? `${name.slice(0, COLUMN_NAME_LIMIT)}…` : name

const toNumber = (value: string | undefined) => {
  const parsed = Number((value ?? '').replace(/,/g, ''))
  return value && Number.isFinite(parsed) ? parsed : null
}

// STG-10 평가 결과 등록. 외부에서 진행한 평가 결과를 가져와 평가 전형의 결과로 관리한다
export function RegisterDialog({
  overview,
  open,
  onOpenChange,
}: {
  overview: StageOverview
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [method, setMethod] = useState<Method>('TABLE')
  const [step, setStep] = useState(1)
  const [table, setTable] = useState<TablePreview | null>(null)
  const [mapping, setMapping] = useState<string[]>([])
  const [links, setLinks] = useState<Record<string, string>>({})
  const preview = usePreviewTable(overview.stageId)
  const importer = useImportResults(overview.stageId)
  const candidates = useAllCandidates(overview.stageId, open)
  const fileInput = useRef<HTMLInputElement>(null)

  const keyIndex = mapping.findIndex((target) => target === 'EMAIL' || target === 'APPLICATION_NO')
  const identifierType = (mapping[keyIndex] ?? 'EMAIL') as IdentifierType
  const entries: ImportRow[] = (table?.rows ?? []).map((row) => {
    const areas: Record<string, number> = {}
    let total: number | null = null
    let grade: string | null = null
    mapping.forEach((target, index) => {
      if (NCS_AREAS.includes(target as (typeof NCS_AREAS)[number])) {
        const value = toNumber(row[index])
        if (value !== null) areas[target] = value
      }
      if (target === 'TOTAL') total = toNumber(row[index])
      if (target === 'GRADE') grade = row[index] || null
    })
    const identifier = keyIndex >= 0 ? (row[keyIndex] ?? '') : ''
    return { identifier, applicationId: links[identifier] ?? null, total, areas, grade }
  })

  const check = (nextLinks = links) =>
    importer.mutate(
      {
        dryRun: true,
        identifierType,
        entries: entries.map((entry) => ({
          ...entry,
          applicationId: nextLinks[entry.identifier] ?? null,
        })),
      },
      { onError: (error) => toast.error(errorMessage(error)) },
    )

  const pick = (file: File | undefined) => {
    if (!file) return
    preview.mutate(file, {
      onSuccess: (result) => {
        setTable(result)
        setMapping(result.columns.map(guess))
        setLinks({})
        importer.reset()
        setStep(2)
      },
      onError: (error) => toast.error(errorMessage(error)),
    })
  }

  const close = () => {
    onOpenChange(false)
    setStep(1)
    setTable(null)
    importer.reset()
  }

  const save = () =>
    importer.mutate(
      { dryRun: false, identifierType, entries },
      {
        onSuccess: (result) => {
          toast.success(`${result.matched}명의 평가 결과를 등록했어요.`)
          close()
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    )

  const dryRun = importer.data && !importer.data.saved ? importer.data : null
  const steps = ['입력 방식', method === 'TABLE' ? '항목 매핑' : '결과 입력', '확인']

  return (
    <Dialog open={open} onOpenChange={(value) => (value ? onOpenChange(true) : close())}>
      <DialogContent
        showCloseButton={false}
        className="flex max-h-[85vh] flex-col gap-0 p-0 sm:max-w-[760px]"
      >
        <div className="flex items-center gap-3 border-b px-5 py-4">
          <DialogTitle className="text-base font-bold">평가 결과 등록</DialogTitle>
          <span className="text-xs text-muted-foreground">{overview.name}</span>
          <ol className="ml-auto flex items-center gap-2 text-xs">
            {steps.map((label, index) => (
              <li key={label} className="flex items-center gap-2">
                {index > 0 && <span className="h-px w-6 bg-border" />}
                <span
                  className={cn(
                    'flex size-5 items-center justify-center rounded-full font-bold',
                    index + 1 < step
                      ? 'bg-pass-foreground text-white'
                      : index + 1 === step
                        ? 'bg-foreground text-background'
                        : 'border text-muted-foreground',
                  )}
                >
                  {index + 1 < step ? <Check className="size-3" /> : index + 1}
                </span>
                <span
                  className={cn(index + 1 === step ? 'font-semibold' : 'text-muted-foreground')}
                >
                  {label}
                </span>
              </li>
            ))}
          </ol>
        </div>
        <div className="flex min-h-0 flex-1">
          <div className="w-[190px] shrink-0 space-y-2 border-r p-3">
            {METHODS.map((item) => {
              const disabled = item.key === 'API'
              return (
                <button
                  key={item.key}
                  disabled={disabled}
                  onClick={() => {
                    setMethod(item.key as Method)
                    setStep(item.key === 'TABLE' && !table ? 1 : 2)
                  }}
                  className={cn(
                    'flex w-full items-start gap-2.5 rounded-lg border p-2.5 text-left',
                    method === item.key && 'border-foreground',
                    disabled && 'opacity-50',
                  )}
                >
                  <span
                    className={cn(
                      'mt-0.5 size-3.5 shrink-0 rounded-full border-2',
                      method === item.key && 'border-4 border-foreground',
                    )}
                  />
                  <span>
                    <span className="block text-sm font-semibold">{item.label}</span>
                    <span className="block text-xs text-muted-foreground">
                      {disabled ? '예정' : item.hint}
                    </span>
                  </span>
                </button>
              )
            })}
          </div>
          <div className="min-w-0 flex-1 overflow-auto p-4">
            {method === 'TABLE' && !table && (
              <button
                onClick={() => fileInput.current?.click()}
                disabled={preview.isPending}
                className="flex h-40 w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed text-sm text-muted-foreground hover:bg-muted/50"
              >
                <FileSpreadsheet className="size-6" />
                결과표 올리기 (CSV · XLSX)
              </button>
            )}
            {method === 'TABLE' && table && step === 2 && (
              <div className="space-y-3">
                <div className="flex items-center gap-2 rounded-lg border px-3 py-2.5 text-sm">
                  <FileSpreadsheet className="size-4 text-ai" />
                  <span className="flex-1 font-semibold">{table.fileName}</span>
                  <span className="text-xs text-muted-foreground">
                    {table.rows.length}행 · {table.columns.length}열
                  </span>
                  <Button size="sm" variant="outline" onClick={() => fileInput.current?.click()}>
                    변경
                  </Button>
                </div>
                <div className="rounded-lg border">
                  <div className="grid grid-cols-[1fr_24px_1.4fr] border-b px-3 py-2 text-xs text-muted-foreground">
                    <span>파일 열</span>
                    <span />
                    <span>결과 항목</span>
                  </div>
                  {table.columns.map((column, index) => (
                    <div
                      key={`${column}-${index}`}
                      className="grid grid-cols-[1fr_24px_1.4fr] items-center px-3 py-1.5 text-sm"
                    >
                      <span className="font-semibold" title={column || undefined}>
                        {shorten(column || `열 ${index + 1}`)}
                      </span>
                      <ArrowRight className="size-3.5 text-muted-foreground" />
                      <select
                        aria-label={`${column} 결과 항목`}
                        value={mapping[index]}
                        onChange={(event) => {
                          setMapping((current) =>
                            current.map((value, i) => (i === index ? event.target.value : value)),
                          )
                          importer.reset()
                        }}
                        className="h-8 rounded-md border bg-background px-2 text-sm"
                      >
                        {TARGETS.map((target) => (
                          <option key={target.value} value={target.value}>
                            {target.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
                {keyIndex < 0 ? (
                  <Banner warn>이메일이나 지원번호 열을 지원자 매칭 키로 지정해 주세요.</Banner>
                ) : !dryRun ? (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => check()}
                    disabled={importer.isPending}
                  >
                    지원자 매칭 확인
                  </Button>
                ) : (
                  <div className="space-y-2">
                    <Banner warn={dryRun.unmatched.length > 0}>
                      <b>
                        {dryRun.matched} / {dryRun.total}명
                      </b>{' '}
                      매칭
                      {dryRun.unmatched.length > 0 && ` · ${dryRun.unmatched.length}명 확인 필요`}
                    </Banner>
                    {dryRun.unmatched.map((identifier) => (
                      <div key={identifier} className="flex items-center gap-2 text-sm">
                        <span className="w-48 truncate text-muted-foreground">{identifier}</span>
                        <ArrowRight className="size-3.5 text-muted-foreground" />
                        <select
                          aria-label={`${identifier} 직접 연결`}
                          value={links[identifier] ?? ''}
                          onChange={(event) => {
                            const next = { ...links, [identifier]: event.target.value }
                            setLinks(next)
                            check(next)
                          }}
                          className="h-8 flex-1 rounded-md border bg-background px-2"
                        >
                          <option value="">직접 연결할 지원자 선택</option>
                          {candidates.data?.items.map((row) => (
                            <option key={row.applicationId} value={row.applicationId}>
                              {row.name} · {careerLabel(row)}
                            </option>
                          ))}
                        </select>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
            {method === 'TABLE' && table && step === 3 && dryRun && (
              <div className="space-y-3 text-sm">
                <Banner>
                  <b>{dryRun.matched}명</b>의 결과를 {overview.name} 결과로 등록해요. 맞추지 못한{' '}
                  {dryRun.total - dryRun.matched}행은 제외해요.
                </Banner>
                <p className="text-xs text-muted-foreground">
                  등록하면 리스트에 총점이 붙고 점수 높은 순으로 정렬돼요. Assessment Agent가 결과를
                  지원자 프로필에 더해요.
                </p>
              </div>
            )}
            {method !== 'TABLE' && (
              <PerCandidate
                stageId={overview.stageId}
                method={method}
                rows={candidates.data?.items ?? []}
              />
            )}
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 border-t px-5 py-3">
          <Button
            variant="outline"
            onClick={() => (step > 1 && method === 'TABLE' ? setStep(step - 1) : close())}
          >
            {step > 1 && method === 'TABLE' ? '이전' : '닫기'}
          </Button>
          {method === 'TABLE' && step === 2 && (
            <Button disabled={!dryRun || dryRun.matched === 0} onClick={() => setStep(3)}>
              다음: 확인
            </Button>
          )}
          {method === 'TABLE' && step === 3 && (
            <Button disabled={importer.isPending} onClick={save}>
              등록
            </Button>
          )}
          {method !== 'TABLE' && <Button onClick={close}>완료</Button>}
        </div>
        <input
          ref={fileInput}
          type="file"
          accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          hidden
          aria-label="결과표 파일"
          onChange={(event) => {
            pick(event.target.files?.[0])
            event.target.value = ''
          }}
        />
      </DialogContent>
    </Dialog>
  )
}

function Banner({ warn, children }: { warn?: boolean; children: ReactNode }) {
  return (
    <div
      className={cn(
        'flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm',
        warn ? 'bg-amber-50 text-amber-900' : 'bg-pass/60',
      )}
    >
      {warn ? (
        <AlertTriangle className="size-4 text-amber-500" />
      ) : (
        <Check className="size-4 text-pass-foreground" />
      )}
      <span>{children}</span>
    </div>
  )
}

/** 결과 파일 · 수동 입력 · 제출 파일과 URL은 지원자마다 바로 저장한다. */
function PerCandidate({
  stageId,
  method,
  rows,
}: {
  stageId: string
  method: Exclude<Method, 'TABLE'>
  rows: {
    applicationId: string
    name: string
    score: number | null
    careerYears: number | null
    lastCompany: string | null
    analysisStatus: 'PENDING' | 'DONE' | 'FAILED'
  }[]
}) {
  const save = useSaveResult(stageId)
  const attach = useAttachResultFile(stageId)
  const [values, setValues] = useState<
    Record<string, { total: string; grade: string; url: string; note: string }>
  >({})
  const fail = (error: unknown) => toast.error(errorMessage(error))

  return (
    <div className="divide-y rounded-lg border">
      {rows.map((row) => {
        const value = values[row.applicationId] ?? {
          total: row.score !== null ? String(row.score) : '',
          grade: '',
          url: '',
          note: '',
        }
        const set = (patch: Partial<typeof value>) =>
          setValues((current) => ({ ...current, [row.applicationId]: { ...value, ...patch } }))
        return (
          <div key={row.applicationId} className="flex items-center gap-3 px-3 py-2 text-sm">
            <div className="w-36 min-w-0">
              <div className="truncate font-semibold">{row.name}</div>
              <div className="truncate text-xs text-muted-foreground">{careerLabel(row)}</div>
            </div>
            {method === 'MANUAL' && (
              <>
                <Input
                  aria-label={`${row.name} 총점`}
                  placeholder="총점"
                  inputMode="decimal"
                  value={value.total}
                  onChange={(event) => set({ total: event.target.value })}
                  className="h-8 w-20"
                />
                <Input
                  aria-label={`${row.name} 등급`}
                  placeholder="등급"
                  value={value.grade}
                  onChange={(event) => set({ grade: event.target.value })}
                  className="h-8 w-16"
                />
                {/* 평가 메모는 Assessment Agent가 강점 · 약점을 뽑는 자료가 된다. 비워 두면 이전 메모를 그대로 둔다 */}
                <Input
                  aria-label={`${row.name} 평가 메모`}
                  placeholder="평가 메모 (선택)"
                  value={value.note}
                  onChange={(event) => set({ note: event.target.value })}
                  className="h-8 min-w-0 flex-1"
                />
                <Button
                  size="sm"
                  variant="outline"
                  className="ml-auto"
                  disabled={save.isPending}
                  onClick={() =>
                    save.mutate(
                      {
                        applicationId: row.applicationId,
                        total: toNumber(value.total),
                        areas: {},
                        grade: value.grade || null,
                        url: null,
                        note: value.note || null,
                      },
                      {
                        onSuccess: () => toast.success(`${row.name} 결과를 저장했어요.`),
                        onError: fail,
                      },
                    )
                  }
                >
                  저장
                </Button>
              </>
            )}
            {method === 'SUBMISSION' && (
              <>
                <Link2 className="size-4 shrink-0 text-muted-foreground" />
                <Input
                  aria-label={`${row.name} 제출 URL`}
                  placeholder="https://"
                  value={value.url}
                  onChange={(event) => set({ url: event.target.value })}
                  className="h-8 flex-1"
                />
                <Button
                  size="sm"
                  variant="outline"
                  disabled={save.isPending}
                  onClick={() =>
                    save.mutate(
                      {
                        applicationId: row.applicationId,
                        total: toNumber(value.total),
                        areas: {},
                        grade: null,
                        url: value.url || null,
                        note: null,
                      },
                      {
                        onSuccess: () => toast.success(`${row.name} 제출물을 저장했어요.`),
                        onError: fail,
                      },
                    )
                  }
                >
                  저장
                </Button>
              </>
            )}
            {(method === 'FILE' || method === 'SUBMISSION') && (
              <label className="ml-auto inline-flex cursor-pointer items-center gap-1 rounded-md border px-2 py-1 text-xs font-medium hover:bg-muted">
                <FileUp className="size-3.5" />
                PDF
                <input
                  type="file"
                  accept="application/pdf,.pdf"
                  hidden
                  onChange={(event) => {
                    const file = event.target.files?.[0]
                    if (file)
                      attach.mutate(
                        { applicationId: row.applicationId, file },
                        {
                          onSuccess: () => toast.success(`${row.name} 파일을 올렸어요.`),
                          onError: fail,
                        },
                      )
                    event.target.value = ''
                  }}
                />
              </label>
            )}
          </div>
        )
      })}
    </div>
  )
}
