import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap, type Schemas } from '@/lib/api/client'

export type CompanyProfile = Schemas['CompanyProfile']
export type PostingSettings = Schemas['PostingSettings']
export type NoticeTemplate = Schemas['NoticeTemplateInfo']
export type NoticeTemplateType = NoticeTemplate['type']
export type CompanyFile = Schemas['CompanyFileInfo']
export type FileCategory = CompanyFile['category']
export type MailStyle = Schemas['MailStyle']
export type ReceiptTemplate = Schemas['ReceiptTemplateView']

export const companyKeys = {
  profile: ['company', 'profile'] as const,
  postingSettings: ['company', 'posting-settings'] as const,
  noticeTemplates: ['company', 'notice-templates'] as const,
  files: (category: FileCategory) => ['company', 'files', category] as const,
  mailStyle: ['company', 'mail-style'] as const,
  receiptTemplate: ['company', 'receipt-template'] as const,
}

export function useCompanyProfile() {
  return useQuery({
    queryKey: companyKeys.profile,
    queryFn: () => unwrap(api.GET('/api/companies/me/profile')),
  })
}

export function useSaveCompanyProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Schemas['ProfileRequest']) =>
      unwrap(api.PUT('/api/companies/me/profile', { body })),
    onSuccess: (profile) => queryClient.setQueryData(companyKeys.profile, profile),
  })
}

export function usePostingSettings() {
  return useQuery({
    queryKey: companyKeys.postingSettings,
    queryFn: () => unwrap(api.GET('/api/companies/me/posting-settings')),
  })
}

export function useSavePostingSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Schemas['PostingSettingsRequest']) =>
      unwrap(api.PUT('/api/companies/me/posting-settings', { body })),
    onSuccess: (settings) => queryClient.setQueryData(companyKeys.postingSettings, settings),
  })
}

export function useNoticeTemplates() {
  return useQuery({
    queryKey: companyKeys.noticeTemplates,
    queryFn: () => unwrap(api.GET('/api/companies/me/notice-templates')),
  })
}

export function useSaveNoticeTemplate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ type, ...body }: NoticeTemplate) =>
      unwrap(
        api.PUT('/api/companies/me/notice-templates/{type}', { params: { path: { type } }, body }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: companyKeys.noticeTemplates }),
  })
}

export function useCompanyFiles(category: FileCategory) {
  return useQuery({
    queryKey: companyKeys.files(category),
    queryFn: () => unwrap(api.GET('/api/companies/me/files', { params: { query: { category } } })),
  })
}

export function useUploadCompanyFile(category: FileCategory) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return unwrap(
        api.POST('/api/companies/me/files', {
          params: { query: { category } },
          // openapi-fetch는 FormData를 그대로 보낸다
          body: form as unknown as { file: string },
        }),
      )
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: companyKeys.files(category) }),
  })
}

export function useDeleteCompanyFile(category: FileCategory) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (fileId: string) =>
      unwrap(api.DELETE('/api/companies/me/files/{fileId}', { params: { path: { fileId } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: companyKeys.files(category) }),
  })
}

export function companyFileUrl(fileId: string) {
  return `/api/companies/me/files/${fileId}/content`
}

/** 메일 꾸밈(색, 로고). 모든 안내 메일과 접수 확인 메일에 쓴다 */
export function useMailStyle() {
  return useQuery({
    queryKey: companyKeys.mailStyle,
    queryFn: () => unwrap(api.GET('/api/companies/me/mail-style')),
  })
}

export function useSaveMailColor() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (color: string) =>
      unwrap(api.PUT('/api/companies/me/mail-style', { body: { color } })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: companyKeys.mailStyle })
      void queryClient.invalidateQueries({ queryKey: companyKeys.receiptTemplate })
    },
  })
}

export function useUploadMailLogo() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return unwrap(
        api.POST('/api/companies/me/mail-style/logo', {
          // openapi-fetch는 FormData를 그대로 보낸다
          body: form as unknown as { file: string },
        }),
      )
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: companyKeys.mailStyle })
      void queryClient.invalidateQueries({ queryKey: companyKeys.receiptTemplate })
    },
  })
}

export function useDeleteMailLogo() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => unwrap(api.DELETE('/api/companies/me/mail-style/logo')),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: companyKeys.mailStyle })
      void queryClient.invalidateQueries({ queryKey: companyKeys.receiptTemplate })
    },
  })
}

/** 고르는 중인 색으로 만든 예시 메일. 색을 바꾸는 동안 앞 미리보기를 그대로 둔다 */
export function useMailStylePreview(color: string | null) {
  return useQuery({
    queryKey: [...companyKeys.mailStyle, 'preview', color],
    enabled: color !== null,
    placeholderData: keepPreviousData,
    queryFn: () =>
      unwrap(
        api.GET('/api/companies/me/mail-style/preview', {
          params: { query: { color: color ?? undefined } },
        }),
      ),
  })
}

/** 접수 확인 메일 양식. 지원서를 내면 바로 가는 메일이라 AI는 쓰지 않고, 모든 공고에 같이 쓴다 */
export function useReceiptTemplate() {
  return useQuery({
    queryKey: companyKeys.receiptTemplate,
    queryFn: () => unwrap(api.GET('/api/companies/me/receipt-template')),
  })
}

export function useSaveReceiptTemplate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { subject: string; body: string }) =>
      unwrap(api.PUT('/api/companies/me/receipt-template', { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: companyKeys.receiptTemplate }),
  })
}

/** 저장한 접수 확인 메일 양식으로 만든 예시 메일. 메일 색 · 로고를 바꾸면 새로 받는다 */
export function useReceiptTemplatePreview() {
  return useQuery({
    queryKey: [...companyKeys.receiptTemplate, 'preview'],
    queryFn: () => unwrap(api.GET('/api/companies/me/receipt-template/preview')),
  })
}
