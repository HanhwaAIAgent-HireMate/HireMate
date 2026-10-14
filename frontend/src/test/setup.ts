import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Vitest 전역 API를 쓰지 않아 Testing Library가 자동으로 정리하지 못하므로 테스트마다 화면을 비운다
afterEach(() => {
  cleanup()
})
