import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap, type Schemas } from '@/lib/api/client'

export type CompanyProfile = Schemas['CompanyProfile']
export type PostingSettings = Schemas['PostingSettings']
export type NoticeTemplate = Schemas['NoticeTemplateInfo']
export type NoticeTemplateType = NoticeTemplate['type']
export type CompanyFile = Schemas['CompanyFileInfo']
export type FileCategory = CompanyFile['category']

export const companyKeys = {
  profile: ['company', 'profile'] as const,
  postingSettings: ['company', 'posting-settings'] as const,
  noticeTemplates: ['company', 'notice-templates'] as const,
  files: (category: FileCategory) => ['company', 'files', category] as const,
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
