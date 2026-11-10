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
  /**
   * 둥근 차트(도넛 · 레이더)의 그림 폭(px). 이때 범례는 화면이 그림 옆에 글로 그리고,
   * 그림과 범례를 한 덩어리로 카드 가운데에 둔다
   */
  width?: number
  legend?: { label: string; value?: string; color: string }[]
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

// 모든 차트를 같은 자리에 맞춘다. 범례는 왼쪽 위, 그림은 카드 제목과 같은 왼쪽 끝에서 같은 높이로 시작한다
/** 범례 아래 그림이 시작하는 높이(px). 범례가 없는 차트도 같은 높이에서 시작해 나란한 카드가 맞는다 */
const PLOT_TOP = 30
/** 지원자 이름 칸 폭(px) */
const NAME_WIDTH = 120
/** 평가 항목 이름 칸 폭(px). 항목 이름은 길어 자르지 않고 두 줄까지 줄바꿈한다 */
const ITEM_WIDTH = 200
/** 막대 두께(px). 그룹 · 전체처럼 두 막대를 붙여 그리는 차트만 따로 얇게 한다 */
const BAR_WIDTH = 18
/** 막대 끝 값 글자 */
const VALUE_LABEL = { color: INK, fontSize: 11.5 }
/** 도넛의 바깥 반지름(px). 원 오른쪽에 범례를 세로로 두어 휴대폰 폭(카드 약 290px)에도 함께 들어가는 크기다 */
const RING = 60
/** 도넛 안쪽 구멍의 지름(px). 가운데 글자가 이 안에 들어가야 한다 */
const HOLE = 2 * Math.round(RING * 0.68)

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

/** 이름들의 같은 앞 낱말을 뺀다. 모두 같은 이름이거나 같은 앞부분이 없으면 그대로 둔다 */
export function withoutCommonPrefix(labels: string[]) {
  const words = labels.map((label) => label.split(' '))
  let shared = 0
  while (
    words.every((w) => w.length > shared + 1) &&
    words.every((w) => w[shared] === words[0][shared])
  )
    shared++
  return shared === 0 ? labels : words.map((w) => w.slice(shared).join(' '))
}

/**
 * 이름 축 차트의 그림 영역. 이름 칸 폭만큼 왼쪽을 비워 이름은 카드 왼쪽 끝(8px)에서, 막대는 칸 폭 뒤에서 시작한다.
 * 칸 폭이 같은 차트끼리는 막대 시작점이 같다. 가로축 눈금을 보이면 아래에 그 자리를 둔다
 */
function nameGrid(width: number, right: number, ticks: boolean) {
  return { left: width + 16, right, top: PLOT_TOP, bottom: ticks ? 26 : 8 }
}

/** 이 폭(px)보다 좁은 카드(휴대폰)에서는 이름 칸을 줄여 막대 자리를 남긴다 */
const NARROW_CARD = 480

/**
 * 이름 축 차트 옵션. 카드가 좁으면 이름 칸을 반쯤으로 줄인다(ECharts media).
 * 이름은 그만큼 줄바꿈하거나 말줄임한다
 */
function withNameColumn(option: EChartsCoreOption, width: number): EChartsCoreOption {
  const column = (size: number) => ({
    grid: { left: size + 16 },
    yAxis: { axisLabel: { width: size, margin: size + 8 } },
  })
  // 넓은 폭도 따로 적는다. 좁았다가 넓어질 때(창 크기 조절) 좁은 칸이 남지 않게 한다
  return {
    baseOption: option,
    media: [
      { query: { minWidth: NARROW_CARD + 1 }, option: column(width) },
      {
        query: { maxWidth: NARROW_CARD },
        option: column(Math.round(width * 0.55)),
      },
    ],
  }
}

/** 세로로 늘어놓는 이름 축. wrap이면 긴 이름(평가 항목)을 자르지 않고 두 줄까지 줄바꿈한다 */
function nameAxis(names: string[], width: number, wrap = false) {
  return {
    type: 'category',
    data: names,
    inverse: true,
    axisTick: { show: false },
    axisLine: { show: false },
    // 이름을 칸 왼쪽에 붙여 카드 제목과 같은 줄에서 시작하고, 칸 폭이 같으면 막대도 같은 곳에서 시작한다
    axisLabel: {
      color: INK,
      fontSize: 12,
      width,
      align: 'left',
      margin: width + 8,
      ...(wrap ? { overflow: 'break', lineHeight: 15 } : { overflow: 'truncate' }),
    },
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

/** 분포 기준선 이름표가 겹칠 때 한 층씩 올리는 간격(px) */
const LABEL_STEP = 14
/** 두 기준선이 이보다 가까우면(가로축 최댓값 대비) 이름표가 겹친다고 본다 */
const LABEL_GAP = 0.12

interface MarkInput {
  x: number
  text: string
  color: string | undefined
  line?: Record<string, unknown>
}

/** 같은 값의 지원자는 기준선 하나로 묶고 이름을 이어 쓴다. 색이 다르면 기본 글자색으로 그린다 */
function sameValueTogether(marks: MarkInput[]): MarkInput[] {
  const byValue = new Map<number, MarkInput[]>()
  for (const mark of marks) byValue.set(mark.x, [...(byValue.get(mark.x) ?? []), mark])
  return [...byValue.values()].map((group) =>
    group.length === 1
      ? group[0]
      : { x: group[0].x, text: group.map((mark) => mark.text).join(' · '), color: INK },
  )
}

/** 가까이 붙은 기준선의 이름표를 층을 나눠 위로 올려 서로 겹치지 않게 한다 */
function spreadLabels(marks: MarkInput[], top: number) {
  const sorted = [...marks].sort((a, b) => a.x - b.x)
  let layer = 0
  return sorted.map((mark, index) => {
    const previous = sorted[index - 1]
    layer = previous && mark.x - previous.x < top * LABEL_GAP ? layer + 1 : 0
    return {
      layer,
      xAxis: mark.x,
      label: {
        formatter: mark.text,
        position: 'end',
        distance: 5 + layer * LABEL_STEP,
        color: mark.color ?? INK,
        fontSize: 10.5,
      },
      lineStyle: mark.line ?? { color: mark.color ?? INK, type: 'solid', width: 2 },
    }
  })
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
      const marks = spreadLabels(
        [
          ...data.metrics(block.reference).map((r) => ({
            x: r.value,
            text: `${r.label} ${r.value}`,
            color: INK,
            line: { color: '#4A4F57', type: 'dashed', width: 1.3 },
          })),
          ...sameValueTogether(
            (block.highlight ?? []).map((number) => ({
              x: data.value(number, block.key),
              text: who(number),
              color: color(number),
            })),
          ),
        ],
        top,
      )
      series.push({
        type: 'line',
        xAxisIndex: 1,
        data: [],
        silent: true,
        markLine: { symbol: 'none', silent: true, data: marks },
      })
      const layers = Math.max(0, ...marks.map((mark) => mark.layer))
      return {
        height: 250 + layers * LABEL_STEP,
        option: base({
          legend: { ...legend, show: groups.length > 1 },
          grid: {
            left: 8,
            right: 16,
            top: 44 + layers * LABEL_STEP,
            bottom: 8,
            containLabel: true,
          },
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
      // 조각 이름의 같은 앞부분('최종 합격자 신입' · '최종 합격자 7년 이상'의 '최종 합격자')은 범례에서 뺀다
      const names = withoutCommonPrefix(parts.map((p) => p.label))
      // 가운데는 가장 큰 조각이다. 첫 조각이 0%여도 '0%'를 크게 보여 주지 않는다
      const biggest = parts.reduce((top, p, i) => (p.value > parts[top].value ? i : top), 0)
      // 그림은 원만 그리고, 범례(이름과 값)는 화면이 원 오른쪽에 글로 적는다
      const size = 2 * RING + 16
      return {
        height: size,
        width: size,
        legend: parts.map((p, i) => ({
          label: names[i],
          value: `${p.value}${p.unit}`,
          color: SLICES[i % SLICES.length],
        })),
        option: base({
          // 범례가 원 옆에 이름과 값을 이미 적으므로 툴팁은 띄우지 않는다. 좁은 그림 안에 갇힌 툴팁이 링을 가린다
          tooltip: { show: false },
          // 제목 상자를 그림 가운데에 둔다. textAlign까지 'center'로 주면 상자가 왼쪽으로 반 폭 밀려 링에 겹친다
          title: {
            text: `${Math.round((100 * parts[biggest].value) / total)}%`,
            subtext: names[biggest],
            left: 'center',
            top: 'middle',
            itemGap: 2,
            textStyle: { fontSize: 20, fontWeight: 700, color: INK, fontFamily: FONT },
            // 구멍 지름 안에 들어가도록 긴 이름은 자른다
            subtextStyle: {
              fontSize: 11,
              color: MUTED,
              fontFamily: FONT,
              width: HOLE - 12,
              overflow: 'truncate',
            },
          },
          series: [
            {
              type: 'pie',
              radius: [HOLE / 2, RING],
              center: ['50%', '50%'],
              padAngle: 1.5,
              itemStyle: { borderRadius: 3 },
              label: { show: false },
              data: parts.map((p, i) => ({
                name: names[i],
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
        option: withNameColumn(
          base({
            grid: nameGrid(NAME_WIDTH, 56, true),
            xAxis: valueAxis(top),
            yAxis: nameAxis(block.applicants.map(who), NAME_WIDTH),
            series: block.keys.map((key) => ({
              type: 'bar',
              name: data.label(key),
              barMaxWidth: BAR_WIDTH,
              data: block.applicants.map((number) => ({
                value: data.value(number, key),
                itemStyle: { color: color(number) ?? '#6A84B2', borderRadius: [0, 4, 4, 0] },
              })),
              label: {
                show: true,
                position: 'right',
                ...VALUE_LABEL,
                formatter: `{c}/${top}`,
              },
              markLine: refs.length
                ? {
                    symbol: 'none',
                    silent: true,
                    data: refs.map((r) => ({
                      xAxis: r.value,
                      // 이름 축이 위에서 아래로 늘어서므로 기준선 이름은 위쪽 끝(start)에 두어 가로축 눈금과 겹치지 않게 한다
                      label: {
                        formatter: `${r.label} ${r.value}`,
                        position: 'start',
                        color: INK,
                        fontSize: 10.5,
                      },
                      lineStyle: { color: '#4A4F57', type: 'dashed' },
                    })),
                  }
                : undefined,
            })),
          }),
          NAME_WIDTH,
        ),
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
        option: withNameColumn(
          base({
            legend,
            grid: nameGrid(NAME_WIDTH, 16, true),
            xAxis: valueAxis(top),
            yAxis: nameAxis(names, NAME_WIDTH),
            series: block.keys.map((key, i) => ({
              type: 'bar',
              name: `${data.label(key)} /${data.max(key) ?? 0}`,
              stack: 's',
              barMaxWidth: BAR_WIDTH,
              itemStyle: { color: PARTS[i % PARTS.length] },
              data: block.applicants.map((number) => data.value(number, key)),
              label: { show: true, color: i === 0 ? '#fff' : INK, fontSize: 11.5, fontWeight: 600 },
            })),
          }),
          NAME_WIDTH,
        ),
      }
    }
    case 'share': {
      const shares = sharePercents(bundle, block.keys, block.groupKey, block.groupValue)
      const group = block.groupValue === 'PASS' ? '합격자' : word(block.groupValue)
      return {
        height: 50 + 40 * block.keys.length,
        option: withNameColumn(
          base({
            legend,
            grid: nameGrid(ITEM_WIDTH, 40, true),
            xAxis: valueAxis(100, {
              axisLabel: { color: MUTED, fontSize: 11, formatter: '{value}%' },
            }),
            yAxis: nameAxis(block.keys.map(data.label), ITEM_WIDTH, true),
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
                ...VALUE_LABEL,
                color: i === 0 ? INK : MUTED,
                formatter: '{c}%',
              },
            })),
          }),
          ITEM_WIDTH,
        ),
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
      // 항목마다 그린 막대는 항목 이름이 길어 자르면 어떤 항목인지 알 수 없으므로 줄바꿈해 다 보여 준다
      const items = block.type === 'tally' && block.by === 'key'
      return {
        height: 50 + (items ? 50 : 34) * values.length,
        option: withNameColumn(
          base({
            legend,
            tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
            grid: nameGrid(items ? ITEM_WIDTH : NAME_WIDTH, 16, false),
            xAxis: valueAxis(100, { show: false }),
            yAxis: items ? nameAxis(rowNames, ITEM_WIDTH, true) : nameAxis(rowNames, NAME_WIDTH),
            series: bands.map((band, j) => ({
              type: 'bar',
              name: band,
              stack: 'p',
              barMaxWidth: BAR_WIDTH,
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
                return {
                  value: Number(pct.toFixed(1)),
                  label: { formatter: pct >= 5 ? shown : '' },
                }
              }),
            })),
          }),
          items ? ITEM_WIDTH : NAME_WIDTH,
        ),
      }
    }
    case 'radar':
      // 도넛처럼 범례(지원자)는 화면이 그림 오른쪽에 글로 적는다
      return {
        height: 260,
        width: 300,
        legend: block.applicants.map((number) => ({
          label: who(number),
          color: color(number) ?? '#6A84B2',
        })),
        option: base({
          radar: {
            center: ['50%', '52%'],
            radius: '62%',
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
