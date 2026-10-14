import { useQuery } from '@tanstack/react-query'

import { api, unwrap } from '@/lib/api/client'

export const companyKeys = {
  profile: ['company', 'profile'] as const,
  postingSettings: ['company', 'posting-settings'] as const,
  noticeTemplates: ['company', 'notice-templates'] as const,
  files: (category: 'INTRO' | 'POSTING') => ['company', 'files', category] as const,
}

export function useCompanyProfile() {
  return useQuery({
    queryKey: companyKeys.profile,
    queryFn: () => unwrap(api.GET('/api/companies/me/profile')),
  })
}
