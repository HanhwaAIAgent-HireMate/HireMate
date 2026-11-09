import { zodResolver } from '@hookform/resolvers/zod'
import { AlertCircle, CheckCircle2, FileText, FileUp } from 'lucide-react'
import { useRef, useState, type ReactNode } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  DOCUMENT_LABELS,
  useSchoolCheck,
  useSubmitApplication,
  type ApplicationInput,
  type SchoolCheck,
} from '@/features/apply/api'
import { PhotoField } from '@/features/apply/PhotoField'
import type { PublicPosting } from '@/features/posting/api'
import { ApiError, errorMessage } from '@/lib/api/client'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'

const MAX_FILE = 20 * 1024 * 1024
const file = z.instanceof(File).nullable()

function schema(requirePortfolio: boolean, requireCertificate: boolean) {
  return z
    .object({
      name: z.string().trim().min(1).max(100),
      email: z.email(),
      phone: z.string().regex(/^[0-9+\-() ]{9,20}$/),
      certificates: z.string().max(1000),
      consentPrivacy: z.boolean(),
      consentAi: z.boolean(),
      resume: file,
      coverLetter: file,
      portfolio: file,
    })
    .superRefine((values, context) => {
      const require = (ok: boolean, path: string) => {
        if (!ok) context.addIssue({ code: 'custom', path: [path], message: '필수 항목이에요.' })
      }
      require(values.resume !== null, 'resume')
      require(values.coverLetter !== null, 'coverLetter')
      require(!requirePortfolio || values.portfolio !== null, 'portfolio')
      require(!requireCertificate || values.certificates.trim().length > 0, 'certificates')
      require(values.consentPrivacy && values.consentAi, 'consentPrivacy')
    })
}

type Values = z.infer<ReturnType<typeof schema>>

type Section = { key: string; label: string; fields: (keyof Values)[] }

// APL-02 지원서 작성. 모든 채용이 같은 지원서를 쓰고, 필수가 비면 제출하지 않고 그 위치로 이동한다
export function ApplicationForm({
  posting,
  onSubmitted,
}: {
  posting: PublicPosting
  onSubmitted: (result: { applicationNo: number; name: string }) => void
}) {
  const required = (type: string) =>
    posting.documents.find((document) => document.type === type)?.required ?? false
  const requirePortfolio = required('PORTFOLIO')
  const requireCertificate = required('CERTIFICATE')
  const submit = useSubmitApplication(posting.postingId)
  const checkSchools = useSchoolCheck(posting.postingId)
  // 블라인드 채용 서류에서 찾은 학교 이름. 있으면 다시 올리거나 그대로 내게 묻는다
  const [found, setFound] = useState<{
    input: ApplicationInput
    documents: SchoolCheck['documents']
  } | null>(null)
  const [serverError, setServerError] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const form = useForm<Values>({
    resolver: zodResolver(schema(requirePortfolio, requireCertificate)),
    defaultValues: {
      name: '',
      email: '',
      phone: '',
      certificates: '',
      consentPrivacy: false,
      consentAi: false,
      resume: null,
      coverLetter: null,
      portfolio: null,
    },
  })
  const values = useWatch({ control: form.control })
  const errors = form.formState.errors

  const sections: Section[] = [
    { key: 'basic', label: '기본 정보', fields: ['name', 'email', 'phone'] },
    { key: 'resume', label: '이력서', fields: ['resume'] },
    { key: 'coverLetter', label: '자기소개서', fields: ['coverLetter'] },
    ...(requirePortfolio
      ? [{ key: 'portfolio', label: '포트폴리오', fields: ['portfolio'] as (keyof Values)[] }]
      : []),
    ...(requireCertificate
      ? [{ key: 'certificates', label: '자격증', fields: ['certificates'] as (keyof Values)[] }]
      : []),
    { key: 'consent', label: '동의', fields: ['consentPrivacy'] },
  ]
  const filled = (section: Section) =>
    section.key === 'basic'
      ? Boolean(values.name?.trim() && values.email?.trim() && values.phone?.trim())
      : section.key === 'consent'
        ? Boolean(values.consentPrivacy && values.consentAi)
        : section.key === 'certificates'
          ? Boolean(values.certificates?.trim())
          : Boolean(values[section.fields[0]])
  const done = sections.filter(filled).length
  const hasError = (section: Section) => section.fields.some((field) => errors[field])

  const onValid = (data: Values) => {
    setServerError('')
    const input = {
      ...data,
      name: data.name.trim(),
      email: data.email.trim(),
      photo: posting.content.blind ? null : photo,
    } as ApplicationInput
    if (!posting.content.blind) {
      send(input)
      return
    }
    // 확인은 알림일 뿐이라, 확인하지 못하면 그대로 제출한다
    checkSchools.mutate(input, {
      onSuccess: ({ documents }) =>
        documents.length > 0 ? setFound({ input, documents }) : send(input),
      onError: () => send(input),
    })
  }

  // 다시 올릴 서류의 위치로 이동한다
  const reupload = () => {
    const type = found?.documents[0]?.type
    setFound(null)
    const key =
      type === 'COVER_LETTER' ? 'coverLetter' : type === 'PORTFOLIO' ? 'portfolio' : 'resume'
    document.getElementById(`apply-${key}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  const send = (input: ApplicationInput) =>
    submit.mutate(input, {
      onSuccess: (result) => onSubmitted(result),
      onError: (error) =>
        setServerError(
          error instanceof ApiError && error.code === 'ALREADY_APPLIED'
            ? '이미 이 이메일로 지원했어요.'
            : error instanceof ApiError && error.code === 'POSTING_NOT_OPEN'
              ? '지원 접수 기간이 아니에요.'
              : errorMessage(error),
        ),
    })

  const onInvalid = () => {
    const first = sections.find((section) =>
      section.fields.some((field) => form.getFieldState(field).invalid),
    )
    document
      .getElementById(`apply-${first?.key}`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  const fileProps = (field: 'resume' | 'coverLetter' | 'portfolio') => ({
    value: values[field] ?? null,
    error: Boolean(errors[field]),
    onChange: (picked: File | null) =>
      form.setValue(field, picked, { shouldValidate: form.formState.isSubmitted }),
  })

  return (
    <form
      noValidate
      onSubmit={(event) => void form.handleSubmit(onValid, onInvalid)(event)}
      className="flex items-start gap-8"
    >
      <div className="min-w-0 flex-1 space-y-6">
        <div>
          <h1 className="text-xl font-bold">지원서 작성</h1>
          <p className="mt-1 text-xs text-muted-foreground">
            {posting.content.title} · 마감 {formatDateTime(posting.closeAt)}
          </p>
        </div>
        {/* 증명사진은 선택이고, 블라인드 채용이면 받지 않는다 */}
        {!posting.content.blind && (
          <Field id="photo" label="증명사진" required={false}>
            <PhotoField onChange={setPhoto} />
          </Field>
        )}
        <Field id="basic" label="기본 정보" required error={hasError(sections[0])}>
          <div className="grid grid-cols-3 gap-2">
            <Input
              aria-label="이름"
              placeholder="이름"
              aria-invalid={Boolean(errors.name)}
              {...form.register('name')}
            />
            <Input
              aria-label="이메일"
              type="email"
              placeholder="이메일"
              aria-invalid={Boolean(errors.email)}
              {...form.register('email')}
            />
            <Input
              aria-label="연락처"
              placeholder="010-0000-0000"
              aria-invalid={Boolean(errors.phone)}
              {...form.register('phone')}
            />
          </div>
        </Field>
        <Field id="resume" label="이력서" required format="PDF" error={Boolean(errors.resume)}>
          <FilePicker label="이력서" {...fileProps('resume')} />
        </Field>
        <Field
          id="coverLetter"
          label="자기소개서"
          required
          format="PDF"
          error={Boolean(errors.coverLetter)}
        >
          <FilePicker label="자기소개서" {...fileProps('coverLetter')} />
        </Field>
        <Field
          id="portfolio"
          label="포트폴리오"
          required={requirePortfolio}
          format="PDF"
          error={Boolean(errors.portfolio)}
        >
          <FilePicker label="포트폴리오" {...fileProps('portfolio')} />
        </Field>
        <Field
          id="certificates"
          label="자격증"
          required={requireCertificate}
          error={Boolean(errors.certificates)}
        >
          <Input
            aria-label="자격증"
            placeholder="예: 정보처리기사, SQLD"
            {...form.register('certificates')}
          />
        </Field>
        <Field id="consent" label="동의" required error={Boolean(errors.consentPrivacy)}>
          <div className="space-y-2.5">
            <Consent
              checked={Boolean(values.consentPrivacy)}
              onChange={(checked) =>
                form.setValue('consentPrivacy', checked, {
                  shouldValidate: form.formState.isSubmitted,
                })
              }
              label="개인정보 수집·이용에 동의합니다."
              title="개인정보 수집·이용 안내"
              body={`수집 항목: 이름, 이메일, 연락처, 제출 서류, 선택한 증명사진\n이용 목적: ${posting.companyName} 채용 전형 진행과 결과 안내\n보관 기간: 채용 종료 후 회사가 정한 기간까지 보관한 뒤 파기합니다.\n동의하지 않으면 지원할 수 없어요.`}
            />
            <Consent
              checked={Boolean(values.consentAi)}
              onChange={(checked) =>
                form.setValue('consentAi', checked, { shouldValidate: form.formState.isSubmitted })
              }
              label="AI 활용 안내를 확인했습니다."
              title="AI 활용 안내"
              body={`제출한 자료는 채용 담당자의 검토를 돕기 위해 AI가 분석해요.\nAI는 근거를 정리하고 검토 순서를 제안할 뿐이며, 합격 · 불합격은 채용 담당자가 직접 결정합니다.\n나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 분석과 탐색에 쓰지 않아요.`}
            />
          </div>
        </Field>
        {serverError && (
          <p role="alert" className="text-sm text-destructive">
            {serverError}
          </p>
        )}
      </div>
      <aside className="sticky top-6 w-[240px] shrink-0 rounded-xl border p-4">
        <div className="flex items-center justify-between text-sm font-semibold">
          필수 항목
          <span>
            {done} / {sections.length}
          </span>
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
          <div
            className="h-full bg-foreground transition-all"
            style={{ width: `${(done / sections.length) * 100}%` }}
          />
        </div>
        <ul className="mt-4 space-y-2.5 text-sm">
          {sections.map((section) => (
            <li
              key={section.key}
              className={cn('flex items-center gap-2', hasError(section) && 'font-semibold')}
            >
              {hasError(section) ? (
                <AlertCircle className="size-4 text-fail-foreground" />
              ) : (
                <CheckCircle2
                  className={cn(
                    'size-4',
                    filled(section) ? 'text-pass-foreground' : 'text-muted-foreground/50',
                  )}
                />
              )}
              {section.label}
            </li>
          ))}
        </ul>
        <Button
          type="submit"
          className="mt-5 h-10 w-full"
          disabled={submit.isPending || checkSchools.isPending}
        >
          제출하기
        </Button>
      </aside>
      <AlertDialog open={found !== null} onOpenChange={(open) => !open && setFound(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>서류에 학교 이름으로 보이는 말이 있어요</AlertDialogTitle>
            <AlertDialogDescription>
              블라인드 채용이라 지우고 다시 올리는 것을 권해요. 학교에서 일한 경력처럼 출신 학교가
              아니라면 그대로 제출해도 돼요.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <ul className="space-y-1 rounded-lg bg-muted p-3 text-sm">
            {found?.documents.map((document) => (
              <li key={document.type}>
                <span className="font-semibold">{DOCUMENT_LABELS[document.type]}</span>{' '}
                {document.names.map((name) => `"${name}"`).join(', ')}
              </li>
            ))}
          </ul>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={reupload}>다시 올리기</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (found) send(found.input)
                setFound(null)
              }}
            >
              그대로 제출
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </form>
  )
}

function Field({
  id,
  label,
  required,
  format,
  error,
  children,
}: {
  id: string
  label: string
  required: boolean
  format?: string
  error?: boolean
  children: ReactNode
}) {
  return (
    <section id={`apply-${id}`} className="scroll-mt-6 space-y-2">
      <h2 className="flex items-center gap-2 text-sm font-bold">
        {label}
        <span
          className={cn(
            'rounded px-1.5 py-0.5 text-[11px] font-semibold',
            required ? 'bg-fail text-fail-foreground' : 'bg-muted text-muted-foreground',
          )}
        >
          {required ? '필수' : '선택'}
        </span>
        {format && <span className="text-xs font-normal text-muted-foreground">{format}</span>}
        {error && <span className="text-xs font-normal text-fail-foreground">입력이 필요해요</span>}
      </h2>
      {children}
    </section>
  )
}

function FilePicker({
  label,
  value,
  error,
  onChange,
}: {
  label: string
  value: File | null
  error: boolean
  onChange: (file: File | null) => void
}) {
  const input = useRef<HTMLInputElement>(null)
  const [message, setMessage] = useState('')
  const pick = (picked: File | undefined) => {
    if (!picked) return
    if (!picked.name.toLowerCase().endsWith('.pdf') && picked.type !== 'application/pdf') {
      setMessage('PDF 파일만 올릴 수 있어요.')
      return
    }
    if (picked.size > MAX_FILE) {
      setMessage('20MB 이하 파일만 올릴 수 있어요.')
      return
    }
    setMessage('')
    onChange(picked)
  }
  return (
    <div>
      {value ? (
        <div className="flex items-center gap-2 rounded-lg border px-3 py-2.5 text-sm">
          <FileText className="size-4 text-muted-foreground" />
          <span className="min-w-0 flex-1 truncate font-medium">{value.name}</span>
          <span className="text-xs text-muted-foreground">
            {(value.size / 1024 / 1024).toFixed(1)}MB
          </span>
          <Button type="button" variant="outline" size="sm" onClick={() => input.current?.click()}>
            변경
          </Button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => input.current?.click()}
          className={cn(
            'flex w-full items-center gap-2 rounded-lg border border-dashed px-3 py-2.5 text-sm font-medium',
            error
              ? 'border-fail-foreground/60 bg-fail/30 text-fail-foreground'
              : 'text-muted-foreground hover:bg-muted',
          )}
        >
          <FileUp className="size-4" />
          PDF 올리기
        </button>
      )}
      <input
        ref={input}
        type="file"
        accept="application/pdf,.pdf"
        aria-label={`${label} 파일`}
        hidden
        onChange={(event) => {
          pick(event.target.files?.[0])
          event.target.value = ''
        }}
      />
      {message && <p className="mt-1 text-xs text-destructive">{message}</p>}
    </div>
  )
}

function Consent({
  checked,
  onChange,
  label,
  title,
  body,
}: {
  checked: boolean
  onChange: (checked: boolean) => void
  label: string
  title: string
  body: string
}) {
  return (
    <div className="flex items-center gap-2.5 text-sm">
      <Checkbox
        checked={checked}
        onCheckedChange={(value) => onChange(value === true)}
        aria-label={label}
      />
      <span className="flex-1">{label}</span>
      <Dialog>
        <DialogTrigger className="text-xs text-muted-foreground underline underline-offset-2">
          보기
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
          </DialogHeader>
          <p className="text-sm leading-6 whitespace-pre-wrap text-muted-foreground">{body}</p>
        </DialogContent>
      </Dialog>
    </div>
  )
}
