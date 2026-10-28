import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PostingRolesTable } from '@/features/posting/PostingRolesTable'

describe('직무별 모집 표', () => {
  it('직무와 구분, 업무, 필수·우대 요건을 각 행에 보존한다', () => {
    render(
      <PostingRolesTable
        roles={['백엔드', '인사', '생산관리'].map((name) => ({
          name,
          career: '신입',
          duties: [`${name} 업무`],
          qualifications: ['기초 지식'],
          preferred: ['관련 경험'],
        }))}
      />,
    )
    expect(screen.getAllByRole('row')).toHaveLength(4)
    expect(screen.getByRole('columnheader', { name: '구분' })).toBeInTheDocument()
    expect(screen.getByText('생산관리 업무')).toBeInTheDocument()
    expect(screen.getAllByText('필수 사항')).toHaveLength(3)
  })
})
