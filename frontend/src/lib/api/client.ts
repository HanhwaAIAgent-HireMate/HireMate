import createClient from 'openapi-fetch'

import type { paths } from './schema'

// 같은 출처의 /api로 요청한다. 개발 중에는 Vite 프록시가, 배포 후에는 Nginx가 Spring으로 넘긴다.
// 타입(schema.d.ts)은 backend를 띄운 뒤 `npm run api:generate`로 다시 만든다.
export const api = createClient<paths>()
