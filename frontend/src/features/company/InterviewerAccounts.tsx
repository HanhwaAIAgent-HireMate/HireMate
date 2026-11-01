import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useCreateInterviewer, useInterviewerAccounts } from '@/features/company/api'
import { SettingsSection } from '@/features/company/SettingsSection'
import { errorMessage } from '@/lib/api/client'
import { formatMonthDay } from '@/lib/format'

const schema = z.object({
  name: z.string().trim().min(1, '이름을 입력해 주세요.').max(100),
  email: z.email('이메일 형식으로 입력해 주세요.'),
  password: z
    .string()
    .min(12, '비밀번호는 12자 이상이에요.')
    .max(128)
    .refine((value) => value.trim().length > 0, '비밀번호를 입력해 주세요.'),
})

type Values = z.infer<typeof schema>

const FIELDS: { name: keyof Values; label: string; type: string }[] = [
  { name: 'name', label: '이름', type: 'text' },
  { name: 'email', label: '이메일', type: 'email' },
  { name: 'password', label: '처음 비밀번호 (12자 이상)', type: 'password' },
]

/** 설정 › 면접관. HR이 면접관 계정을 만든다. 비밀번호는 HR이 면접관에게 직접 알려 준다 */
export function InterviewerAccounts() {
  const accounts = useInterviewerAccounts()
  const create = useCreateInterviewer()
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { name: '', email: '', password: '' },
  })

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await create.mutateAsync(values)
      form.reset()
      toast.success(`${values.name} 면접관 계정을 만들었어요.`)
    } catch (error) {
      form.setError('root', { message: errorMessage(error) })
    }
  })

  return (
    <SettingsSection title="면접관">
      <p className="text-sm text-muted-foreground">
        면접관은 이 계정으로 로그인해 지정된 면접 전형만 열어요. 면접 전형 화면 위쪽의 [면접관]에서
        전형마다 인사 · 실무 면접관을 지정해요.
      </p>
      {accounts.isPending ? (
        <Skeleton className="h-20 w-full" />
      ) : accounts.data?.length ? (
        <ul className="divide-y rounded-xl border">
          {accounts.data.map((account) => (
            <li key={account.memberId} className="flex items-center gap-3 px-4 py-3 text-sm">
              <span className="font-semibold">{account.name}</span>
              <span className="text-muted-foreground">{account.email}</span>
              <span className="ml-auto text-xs text-muted-foreground">
                {formatMonthDay(account.createdAt)} 추가
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="rounded-xl border border-dashed p-5 text-center text-sm text-muted-foreground">
          아직 면접관 계정이 없어요.
        </p>
      )}
      <form
        onSubmit={(event) => void onSubmit(event)}
        className="space-y-3 rounded-xl border p-4"
        aria-label="면접관 계정 추가"
        noValidate
      >
        <h3 className="text-sm font-semibold">면접관 계정 추가</h3>
        <div className="grid gap-3 sm:grid-cols-3">
          {FIELDS.map((field) => (
            <div key={field.name} className="space-y-1.5">
              <Label htmlFor={`interviewer-${field.name}`}>{field.label}</Label>
              <Input
                id={`interviewer-${field.name}`}
                type={field.type}
                autoComplete="off"
                {...form.register(field.name)}
              />
              {form.formState.errors[field.name]?.message && (
                <p className="text-xs text-destructive">
                  {form.formState.errors[field.name]?.message}
                </p>
              )}
            </div>
          ))}
        </div>
        {form.formState.errors.root?.message && (
          <p className="text-sm text-destructive">{form.formState.errors.root.message}</p>
        )}
        <Button type="submit" disabled={form.formState.isSubmitting}>
          계정 만들기
        </Button>
      </form>
    </SettingsSection>
  )
}
