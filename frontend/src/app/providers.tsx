import { QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { OfflineBanner } from '@/components/OfflineBanner'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { createQueryClient } from '@/app/query-client'

const queryClient = createQueryClient()

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={300}>
        <OfflineBanner />
        {children}
        <Toaster position="bottom-center" />
      </TooltipProvider>
    </QueryClientProvider>
  )
}
