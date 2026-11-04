import { useMutation, useQuery } from '@tanstack/react-query'

import { api, unwrap, type Schemas } from '@/lib/api/client'

export type ApplicationPage = Schemas['ApplicationPage']

export type ApplicationInput = {
  name: string
  email: string
  phone: string
  certificates: string
  consentPrivacy: boolean
  consentAi: boolean
  resume: File
  coverLetter: File
  portfolio: File | null
}

export function useSubmitApplication(postingId: string) {
  return useMutation({
    mutationFn: (input: ApplicationInput) => {
      const form = new FormData()
      form.append('name', input.name)
      form.append('email', input.email)
      form.append('phone', input.phone)
      if (input.certificates.trim()) form.append('certificates', input.certificates.trim())
      form.append('consentPrivacy', String(input.consentPrivacy))
      form.append('consentAi', String(input.consentAi))
      form.append('resume', input.resume)
      form.append('coverLetter', input.coverLetter)
      if (input.portfolio) form.append('portfolio', input.portfolio)
      return unwrap(
        api.POST('/api/public/postings/{postingId}/applications', {
          params: {
            path: { postingId },
            query: {
              name: input.name,
              email: input.email,
              phone: input.phone,
              consentPrivacy: input.consentPrivacy,
              consentAi: input.consentAi,
            },
          },
          // 개인정보가 주소에 남지 않도록 모든 값은 multipart 본문으로만 보낸다
          querySerializer: () => '',
          body: form as unknown as { resume: string; coverLetter: string },
        }),
      )
    },
  })
}

export type SchoolCheck = Schemas['SchoolCheck']

/** 블라인드 채용 지원서의 학교 이름 확인. 제출 전에 지원자에게 알리고, 제출을 막지는 않는다 */
export function useSchoolCheck(postingId: string) {
  return useMutation({
    mutationFn: (input: Pick<ApplicationInput, 'resume' | 'coverLetter' | 'portfolio'>) => {
      const form = new FormData()
      form.append('resume', input.resume)
      form.append('coverLetter', input.coverLetter)
      if (input.portfolio) form.append('portfolio', input.portfolio)
      return unwrap(
        api.POST('/api/public/postings/{postingId}/applications/school-check', {
          params: { path: { postingId } },
          body: form as unknown as { resume: string; coverLetter: string },
        }),
      )
    },
  })
}

export function useApplications(recruitmentId: string, size = 5) {
  return useQuery({
    queryKey: ['applications', recruitmentId, size],
    queryFn: () =>
      unwrap(
        api.GET('/api/recruitments/{recruitmentId}/applications', {
          params: { path: { recruitmentId }, query: { page: 0, size } },
        }),
      ),
    refetchInterval: 30_000,
  })
}

export const DOCUMENT_LABELS = {
  RESUME: '이력서',
  COVER_LETTER: '자기소개서',
  PORTFOLIO: '포트폴리오',
  CERTIFICATE: '자격증',
} as const
