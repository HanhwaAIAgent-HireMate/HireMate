import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router'
import { z } from 'zod'

import { AuthLayout } from '@/app/AuthLayout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { errorMessage } from '@/lib/api/client'
import { useLogin, useMe } from '@/lib/auth'

const schema = z.object({
  email: z.email('이메일 형식으로 입력해 주세요.'),
  password: z.string().min(1, '비밀번호를 입력해 주세요.'),
})

/** 이동할 경로는 같은 앱 안의 /hr 경로만 허용한다. */
function safeNext(next: string | null) {
  return next?.startsWith('/hr') ? next : '/hr'
}

export function LoginPage() {
  const me = useMe()
  const login = useLogin()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const form = useForm({
    resolver: zodResolver(schema),
    defaultValues: { email: '', password: '' },
  })

  if (me.data) return <Navigate to={next} replace />

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await login.mutateAsync(values)
      await navigate(next, { replace: true })
    } catch (error) {
      form.setError('root', { message: errorMessage(error) })
    }
  })

  return (
    <AuthLayout
      title="로그인"
      description="채용 담당자 계정으로 로그인해요."
      footer={
        <>
          처음이신가요?{' '}
          <Link
            to="/signup"
            className="font-medium text-foreground underline-offset-4 hover:underline"
          >
            기업 가입
          </Link>
        </>
      }
    >
      <form onSubmit={(event) => void onSubmit(event)} className="space-y-4" noValidate>
        <div className="space-y-1.5">
          <Label htmlFor="email">이메일</Label>
          <Input id="email" type="email" autoComplete="email" {...form.register('email')} />
          <FieldError message={form.formState.errors.email?.message} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="password">비밀번호</Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            {...form.register('password')}
          />
          <FieldError message={form.formState.errors.password?.message} />
        </div>
        <FieldError message={form.formState.errors.root?.message} />
        <Button type="submit" className="h-10 w-full" disabled={form.formState.isSubmitting}>
          로그인
        </Button>
      </form>
    </AuthLayout>
  )
}

export function FieldError({ message }: { message?: string }) {
  if (!message) return null
  return (
    <p role="alert" className="text-xs text-destructive">
      {message}
    </p>
  )
}
