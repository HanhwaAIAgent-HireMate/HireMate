import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Link, Navigate } from 'react-router'
import { z } from 'zod'

import { AuthLayout } from '@/app/AuthLayout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { errorMessage } from '@/lib/api/client'
import { useMe, useSignup } from '@/lib/auth'
import { FieldError } from '@/pages/hr/LoginPage'

const schema = z.object({
  companyName: z.string().trim().min(1, '회사 이름을 입력해 주세요.').max(100),
  name: z.string().trim().min(1, '이름을 입력해 주세요.').max(100),
  email: z.email('이메일 형식으로 입력해 주세요.'),
  password: z
    .string()
    .min(12, '비밀번호는 12자 이상이에요.')
    .max(128)
    .refine((value) => value.trim().length > 0, '비밀번호를 입력해 주세요.'),
})

type Values = z.infer<typeof schema>

const FIELDS: { name: keyof Values; label: string; type: string; autoComplete: string }[] = [
  { name: 'companyName', label: '회사 이름', type: 'text', autoComplete: 'organization' },
  { name: 'name', label: '담당자 이름', type: 'text', autoComplete: 'name' },
  { name: 'email', label: '이메일', type: 'email', autoComplete: 'email' },
  {
    name: 'password',
    label: '비밀번호 (12자 이상)',
    type: 'password',
    autoComplete: 'new-password',
  },
]

// 가입하면 새 기업과 첫 채용 담당자(HR) 계정이 함께 만들어진다
export function SignupPage() {
  const me = useMe()
  const signup = useSignup()
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { companyName: '', name: '', email: '', password: '' },
  })

  if (signup.isSuccess) return <Navigate to="/hr/settings" replace />
  if (me.data && !signup.isPending) return <Navigate to="/hr" replace />

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await signup.mutateAsync(values)
    } catch (error) {
      form.setError('root', { message: errorMessage(error) })
    }
  })

  return (
    <AuthLayout
      title="기업 가입"
      description="회사와 채용 담당자 계정을 함께 만들어요."
      footer={
        <>
          이미 계정이 있나요?{' '}
          <Link
            to="/login"
            className="font-medium text-foreground underline-offset-4 hover:underline"
          >
            로그인
          </Link>
        </>
      }
    >
      <form onSubmit={(event) => void onSubmit(event)} className="space-y-4" noValidate>
        {FIELDS.map((field) => (
          <div key={field.name} className="space-y-1.5">
            <Label htmlFor={field.name}>{field.label}</Label>
            <Input
              id={field.name}
              type={field.type}
              autoComplete={field.autoComplete}
              {...form.register(field.name)}
            />
            <FieldError message={form.formState.errors[field.name]?.message} />
          </div>
        ))}
        <FieldError message={form.formState.errors.root?.message} />
        <Button type="submit" className="h-10 w-full" disabled={form.formState.isSubmitting}>
          가입하고 시작하기
        </Button>
      </form>
    </AuthLayout>
  )
}
