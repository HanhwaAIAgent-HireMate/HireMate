import { Workflow } from 'lucide-react'

import { cn } from '@/lib/utils'

export function LogoMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex size-7 shrink-0 items-center justify-center rounded-lg bg-foreground text-background',
        className,
      )}
    >
      <Workflow className="size-4" strokeWidth={2.25} />
    </span>
  )
}
