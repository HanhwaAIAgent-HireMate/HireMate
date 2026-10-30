// 차트 부품의 ECharts 옵션. 숫자는 묶음 값과 derive.ts 계산만 쓴다.
import type { EChartsCoreOption } from 'echarts/core'

import { scopeOf, sharePercents, valuesOf } from './derive'
import {
  GRID,
  INK,
  MUTED,
  PARTS,
  PEOPLE,
  SEQ,
  SLICES,
  SPLIT,
  STATUS,
  SUB,
  valueBand,
  word,
} from './palette'
import type { Block, Fact, Metric, ReportBundle } from './types'

export const CHART_TYPES = new Set([
  'distribution',
  'donut',
  'bar',
  'stacked',
  'share',
  'composition',
  'tally',
  'radar',
])

const FONT = "'Pretendard Variable', Pretendard, system-ui, sans-serif"

/** 리포트 한 건에서 차트가 함께 쓰는 자료 */
export interface ChartContext {
  bundle: ReportBundle
  /** 지원자 이름. 이름이 없거나 PDF로 내보낼 때(지원자번호만 보여 줌)는 null */
  name: (number: string) => string | null
  /** 화면에 쓰는 지원자 표기. 웹은 '이름(지원자번호)', PDF는 지원자번호만 */
  who: (number: string) => string
  color: (number: string) => string | undefined
}

export interface Chart {
  option: EChartsCoreOption
  height: number
}

function base(extra: EChartsCoreOption): EChartsCoreOption {
  return {
    animation: false,
    textStyle: { fontFamily: FONT, color: SUB, fontSize: 12 },
    tooltip: { trigger: 'item', confine: true, textStyle: { fontFamily: FONT, fontSize: 12 } },
    ...extra,
  }
}

const legend = { top: 0, left: 0, itemWidth: 11, itemHeight: 11, textStyle: { color: SUB } }

function valueAxis(max: number, extra: Record<string, unknown> = {}) {
  return {
    type: 'value',
    min: 0,
    max,
    splitLine: { lineStyle: { color: GRID } },
    axisLabel: { color: MUTED, fontSize: 11 },
    ...extra,
  }
}

function nameAxis(names: string[], width = 120) {
  return {
    type: 'category',
    data: names,
    inverse: true,
    axisTick: { show: false },
    axisLine: { show: false },
    axisLabel: { color: INK, fontSize: 12, width, overflow: 'truncate' },
  }
}

function lookup(bundle: ReportBundle) {
  const facts = new Map<string, Fact>()
  const labels = new Map<string, string>()
  const maxes = new Map<string, number>()
  for (const fact of bundle.facts) {
    facts.set(`${fact.applicant}|${fact.key}`, fact)
    labels.set(fact.key, fact.label)
    if (fact.max) maxes.set(fact.key, fact.max)
  }
  const metrics = new Map<string, Metric>(bundle.metrics.map((m) => [m.id, m]))
  return {
    value: (number: string, key: string) => Number(facts.get(`${number}|${key}`)?.value ?? 0),
    verdict: (number: string, key: string) => facts.get(`${number}|${key}`)?.value,
    label: (key: string) => labels.get(key) ?? key,
    max: (key: string) => maxes.get(key),
    metrics: (ids: string[] = []) => ids.flatMap((id) => metrics.get(id) ?? []),
  }
}

/** 부품 하나의 ECharts 옵션과 높이(px) */
export function chartFor(block: Block, ctx: ChartContext): Chart {
  const { bundle, who, color } = ctx
  const data = lookup(bundle)
  switch (block.type) {
    case 'distribution': {
      const top = data.max(block.key) ?? 100
      const bins = 10
      const width = top / bins
      const groups = block.split ? ['PASS', 'FAIL'] : ['_']
      const counts = new Map(groups.map((g) => [g, Array<number>(bins).fill(0)]))
      for (const [number, value] of valuesOf(bundle, block.key)) {
        if (typeof value !== 'number') continue
        const group = block.split ? String(data.verdict(number, block.split)) : '_'
        const row = counts.get(group)
        if (row) row[Math.min(bins - 1, Math.floor(value / width))] += 1
      }
      const totals = Array.from({ length: bins }, (_, i) =>
        groups.reduce((sum, g) => sum + (counts.get(g)?.[i] ?? 0), 0),
      )
      const series: Record<string, unknown>[] = groups.map((g, gi) => ({
        type: 'bar',
        name: g === '_' ? '인원' : word(g),
        stack: 'n',
        barCategoryGap: '14%',
        itemStyle: {
          color: SPLIT[g] ?? '#CBD2DC',
          borderRadius: gi === groups.length - 1 ? [3, 3, 0, 0] : 0,
        },
        data: (counts.get(g) ?? []).map((count, i) => ({
          value: count,
          label: {
            show: gi === groups.length - 1 && totals[i] > 0,
            position: 'top',
            formatter: String(totals[i]),
            color: SUB,
            fontSize: 10.5,
          },
        })),
      }))
      const marks = [
        ...data.metrics(block.reference).map((r) => ({
          xAxis: r.value,
          label: {
            formatter: `${r.label} ${r.value}`,
            position: 'end',
            color: INK,
            fontSize: 10.5,
          },
          lineStyle: { color: '#4A4F57', type: 'dashed', width: 1.3 },
        })),
        ...(block.highlight ?? []).map((number) => ({
          xAxis: data.value(number, block.key),
          label: { formatter: who(number), position: 'end', color: color(number), fontSize: 10.5 },
          lineStyle: { color: color(number) ?? INK, type: 'solid', width: 2 },
        })),
      ]
      series.push({
        type: 'line',
        xAxisIndex: 1,
        data: [],
        silent: true,
        markLine: { symbol: 'none', silent: true, data: marks },
      })
      return {
        height: 250,
        option: base({
          legend: { ...legend, show: groups.length > 1 },
          grid: { left: 30, right: 16, top: 44, bottom: 26 },
          xAxis: [
            {
              type: 'category',
              data: Array.from({ length: bins }, (_, i) => `${i * width}~${(i + 1) * width}`),
              axisTick: { show: false },
              axisLine: { lineStyle: { color: '#B9BDC4' } },
              axisLabel: { color: MUTED, fontSize: 10.5 },
            },
            { type: 'value', min: 0, max: top, show: false },
          ],
          yAxis: { type: 'value', show: false },
          series,
        }),
      }
    }
    case 'donut': {
      const parts = data.metrics(block.metrics)
      const total = parts.reduce((sum, p) => sum + p.value, 0) || 1
      return {
        height: 200,
        option: base({
          legend: {
            orient: 'vertical',
            right: 0,
            top: 'middle',
            itemWidth: 11,
            itemHeight: 11,
            itemGap: 9,
            textStyle: { color: INK, fontSize: 12 },
          },
          title: {
            text: `${Math.round((100 * parts[0].value) / total)}%`,
            subtext: parts[0].label.split(' ').at(-1),
            left: '29%',
            top: '36%',
            textAlign: 'center',
            itemGap: 2,
            textStyle: { fontSize: 20, fontWeight: 700, color: INK, fontFamily: FONT },
            subtextStyle: { fontSize: 11, color: MUTED, fontFamily: FONT },
          },
          series: [
            {
              type: 'pie',
              radius: ['46%', '68%'],
              center: ['30%', '50%'],
              padAngle: 1.5,
              itemStyle: { borderRadius: 3 },
              label: { show: false },
              data: parts.map((p, i) => ({
                name: `${p.label}  ${p.value}${p.unit}`,
                value: p.value,
                itemStyle: { color: SLICES[i % SLICES.length] },
              })),
            },
          ],
        }),
      }
    }
    case 'bar': {
      const top = Math.max(...block.keys.map((k) => data.max(k) ?? 100))
      const refs = data.metrics(block.reference)
      return {
        height: 60 + 36 * block.applicants.length,
        option: base({
          grid: { left: 8, right: 56, top: 26, bottom: 8, containLabel: true },
          xAxis: valueAxis(top),
          yAxis: nameAxis(block.applicants.map(who)),
          series: block.keys.map((key) => ({
            type: 'bar',
            name: data.label(key),
            barMaxWidth: 16,
            data: block.applicants.map((number) => ({
              value: data.value(number, key),
              itemStyle: { color: color(number) ?? '#6A84B2', borderRadius: [0, 4, 4, 0] },
            })),
            label: {
              show: true,
              position: 'right',
              color: INK,
              fontSize: 12,
              formatter: `{c}/${top}`,
            },
            markLine: refs.length
              ? {
                  symbol: 'none',
                  silent: true,
                  data: refs.map((r) => ({
                    xAxis: r.value,
                    label: {
                      formatter: `${r.label} ${r.value}`,
                      position: 'end',
                      color: INK,
                      fontSize: 10.5,
                    },
                    lineStyle: { color: '#4A4F57', type: 'dashed' },
                  })),
                }
              : undefined,
          })),
        }),
      }
    }
    case 'stacked': {
      const top = block.keys.reduce((sum, k) => sum + (data.max(k) ?? 0), 0) || 100
      const names = block.applicants.map((number) => {
        const total = block.keys.reduce((sum, k) => sum + data.value(number, k), 0)
        return `${who(number)}  ${total}점`
      })
      return {
        height: 70 + 36 * block.applicants.length,
        option: base({
          legend,
          grid: { left: 8, right: 16, top: 30, bottom: 8, containLabel: true },
          xAxis: valueAxis(top),
          yAxis: nameAxis(names),
          series: block.keys.map((key, i) => ({
            type: 'bar',
            name: `${data.label(key)} /${data.max(key) ?? 0}`,
            stack: 's',
            barMaxWidth: 20,
            itemStyle: { color: PARTS[i % PARTS.length] },
            data: block.applicants.map((number) => data.value(number, key)),
            label: { show: true, color: i === 0 ? '#fff' : INK, fontSize: 11.5, fontWeight: 600 },
          })),
        }),
      }
    }
    case 'share': {
      const shares = sharePercents(bundle, block.keys, block.groupKey, block.groupValue)
      const group = block.groupValue === 'PASS' ? '합격자' : word(block.groupValue)
      return {
        height: 50 + 34 * block.keys.length,
        option: base({
          legend,
          grid: { left: 8, right: 40, top: 28, bottom: 8, containLabel: true },
          xAxis: valueAxis(100, {
            axisLabel: { color: MUTED, fontSize: 11, formatter: '{value}%' },
          }),
          yAxis: nameAxis(block.keys.map(data.label), 110),
          series: [
            [group, '#6F9C85'],
            ['전체', '#C9CCD2'],
          ].map(([label, fill], i) => ({
            type: 'bar',
            name: label,
            barMaxWidth: 10,
            barGap: '20%',
            itemStyle: { color: fill, borderRadius: [0, 3, 3, 0] },
            data: block.keys.map((k) => shares.get(k)?.[i] ?? 0),
            label: {
              show: true,
              position: 'right',
              color: i === 0 ? INK : MUTED,
              fontSize: 11,
              formatter: '{c}%',
            },
          })),
        }),
      }
    }
    case 'composition':
    case 'tally': {
      let rowNames: string[]
      let bands: string[]
      let colors: string[]
      let values: number[][]
      if (block.type === 'composition') {
        const rows = block.rows.map((row) => ({
          label: row.label,
          parts: data.metrics(row.metrics),
        }))
        bands = rows[0].parts.map((p) => p.label.replace(rows[0].label, '').trim())
        colors = SEQ
        rowNames = rows.map(
          (row) => `${row.label}  ${row.parts.reduce((sum, p) => sum + p.value, 0)}명`,
        )
        values = rows.map((row) => row.parts.map((p) => p.value))
      } else {
        const people = block.applicants?.length ? block.applicants : scopeOf(bundle)
        const cells =
          block.by === 'key'
            ? block.keys.map((key) => people.map((n) => data.verdict(n, key)))
            : people.map((n) => block.keys.map((key) => data.verdict(n, key)))
        // 칸은 실제로 나온 값만 둔다. 판정은 충족 → 미충족 순, 결정(합격 · 불합격) 같은 값은 그 뒤에 나온 순서다
        const found = new Set(cells.flat().filter((v): v is string => typeof v === 'string'))
        const statuses = [
          ...Object.keys(STATUS).filter((s) => found.has(s)),
          ...[...found].filter((s) => !(s in STATUS)),
        ]
        bands = statuses.map((s, i) => valueBand(s, i).label)
        colors = statuses.map((s, i) => valueBand(s, i).color)
        rowNames = block.by === 'key' ? block.keys.map(data.label) : people.map(who)
        values = cells.map((row) => statuses.map((s) => row.filter((v) => v === s).length))
      }
      return {
        height: 50 + 34 * values.length,
        option: base({
          legend,
          tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
          grid: { left: 8, right: 16, top: 30, bottom: 8, containLabel: true },
          xAxis: valueAxis(100, { show: false }),
          yAxis: nameAxis(rowNames, 140),
          series: bands.map((band, j) => ({
            type: 'bar',
            name: band,
            stack: 'p',
            barMaxWidth: 22,
            itemStyle: { color: colors[j % colors.length] },
            label: {
              show: true,
              color: block.type === 'composition' && j >= 3 ? '#fff' : INK,
              fontSize: 11,
              fontWeight: 600,
            },
            data: values.map((row) => {
              const total = row.reduce((sum, v) => sum + v, 0) || 1
              const pct = (100 * row[j]) / total
              const shown = block.type === 'composition' ? `${pct.toFixed(0)}%` : String(row[j])
              return { value: Number(pct.toFixed(1)), label: { formatter: pct >= 5 ? shown : '' } }
            }),
          })),
        }),
      }
    }
    case 'radar':
      return {
        height: 260,
        option: base({
          legend: { top: 0 },
          radar: {
            indicator: block.keys.map((k) => ({ name: data.label(k), max: data.max(k) ?? 100 })),
            splitLine: { lineStyle: { color: GRID } },
            axisName: { color: SUB },
          },
          series: [
            {
              type: 'radar',
              data: block.applicants.map((number) => ({
                name: who(number),
                value: block.keys.map((k) => data.value(number, k)),
                itemStyle: { color: color(number) ?? '#6A84B2' },
                areaStyle: { opacity: 0.12 },
              })),
            },
          ],
        }),
      }
    default:
      throw new Error(`차트가 아닌 부품: ${block.type}`)
  }
}

/** 비교 대상 고정 색 */
export function peopleColors(targets: string[]) {
  const colors = new Map(targets.map((number, i) => [number, PEOPLE[i % PEOPLE.length]]))
  return (number: string) => colors.get(number)
}
