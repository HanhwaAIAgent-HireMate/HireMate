import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, resetCsrf, unwrap, type Schemas } from '@/lib/api/client'

export type Member = Schemas['MemberResponse']

export const meQueryKey = ['auth', 'me'] as const

/** 로그인한 담당자. 로그인하지 않았으면 null이다. */
export function useMe() {
  return useQuery({
    queryKey: meQueryKey,
    queryFn: async (): Promise<Member | null> => {
      const { data, response } = await api.GET('/api/auth/me')
      if (response.status === 401) return null
      if (!response.ok || !data) throw new Error('me')
      return data
    },
    staleTime: 5 * 60 * 1000,
  })
}

export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: { email: string; password: string }) => {
      const member = await unwrap(api.POST('/api/auth/login', { body }))
      resetCsrf()
      return member
    },
    onSuccess: (member) => queryClient.setQueryData(meQueryKey, member),
  })
}

export function useSignup() {
  const login = useLogin()
  return useMutation({
    mutationFn: async (body: {
      companyName: string
      name: string
      email: string
      password: string
    }) => {
      await unwrap(api.POST('/api/auth/signup', { body }))
      // 가입은 자동 로그인하지 않으므로 바로 로그인한다
      return login.mutateAsync({ email: body.email, password: body.password })
    },
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      // 문서에 CSRF 헤더가 필수로 적혀 있어 빈 값을 넘기고, 실제 토큰은 CSRF 미들웨어가 채운다
      await api.POST('/api/auth/logout', { params: { header: { 'X-CSRF-TOKEN': '' } } })
      resetCsrf()
    },
    onSettled: () => {
      queryClient.clear()
      queryClient.setQueryData(meQueryKey, null)
    },
  })
}
