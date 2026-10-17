import type { Review } from '../services/api'

export const GENERIC_EXCLUSION_REASONS = [
  'Población incorrecta',
  'Intervención incorrecta',
  'Comparador incorrecto',
  'Desenlace no evaluado',
  'Diseño de estudio incorrecto',
  'Tipo de publicación (revisión, editorial, carta, resumen de congreso)',
  'Estudio en animales o in vitro',
  'Datos insuficientes o no extraíbles',
  'Idioma o fecha fuera de los criterios',
  'Duplicado',
]

const MAX_LEN = 160

const clip = (s: string) => (s.length > MAX_LEN ? `${s.slice(0, MAX_LEN - 1).trimEnd()}…` : s)
const clean = (s: string) => s.replace(/\*\*|__|`/g, '').replace(/\s+/g, ' ').trim()

const TOP_HEADING = /^(criterios?\s+de\s+(inclusi[oó]n|exclusi[oó]n)|(inclusion|exclusion|eligibility)\s+criteria)\s*:?$/i

/** A short line with no sentence punctuation ("Población", "## Outcomes", "**Diseño**:")
 * names a group of criteria rather than being a criterion itself. */
function headingOf(line: string): string | null {
  if (/^#{1,6}\s+/.test(line)) return clean(line.replace(/^#{1,6}\s+/, '')).replace(/:$/, '')
  const bold = line.match(/^\*\*([^*]+)\*\*\s*:?$/)
  if (bold) return clean(bold[1])
  const plain = clean(line).replace(/:$/, '')
  if (plain.length <= 40 && plain.split(/\s+/).length <= 5 && !/[.;,]|\d/.test(plain)) return plain
  return null
}

/** Split the author's free-text criteria (bullets, numbered lines, sub-headings or a Markdown
 * table) into items; items under a sub-heading are prefixed with it ("Población: …"). */
export function parseCriteria(text: string | null | undefined): string[] {
  const items: string[] = []
  let group = ''
  for (const raw of (text || '').split(/\r?\n/)) {
    const line = raw.trim()
    if (!line) continue
    if (line.startsWith('|')) {
      const cells = line.split('|').slice(1, -1).map(clean)
      if (cells.every(c => /^:?-{2,}:?$/.test(c) || !c)) continue
      if (cells.length >= 2 && /^(aspecto|criterio|dominio|elemento|aspect|criterion|domain)s?$/i.test(cells[0])) continue
      const content = cells.filter(Boolean)
      if (content.length >= 2) items.push(`${content[0]}: ${content.slice(1).join(' — ')}`)
      else if (content.length === 1) items.push(content[0])
      continue
    }
    const bulleted = /^(\d+[.)]|[-*•·]|[a-z][.)])\s+/i.test(line)
    const item = clean(line.replace(/^(\d+[.)]|[-*•·]|[a-z][.)])\s+/i, ''))
    if (!item || TOP_HEADING.test(item)) continue
    const heading = bulleted ? null : headingOf(line)
    if (heading) {
      group = heading
      continue
    }
    items.push(group ? `${group}: ${item}` : item)
  }
  return items
}

export function loadCustomReasons(review: Review | undefined): string[] {
  try {
    const parsed = JSON.parse(review?.custom_exclusion_reasons || '[]')
    return Array.isArray(parsed) ? parsed.filter((r) => typeof r === 'string' && r.trim()) : []
  } catch {
    return []
  }
}

export interface ReasonGroup {
  label: string
  reasons: string[]
}

/** Exclusion reasons offered while screening: the review's own criteria first, then the
 * reasons the author saved, then generic ones. */
export function exclusionReasonGroups(review: Review | undefined): ReasonGroup[] {
  // The text before ":" is what PRISMA counts and the report groups by, so it names the criterion.
  const inclusion = parseCriteria(review?.inclusion_criteria).map((c, i) => {
    const sep = c.indexOf(': ')
    return clip(sep > 0 && sep <= 45
      ? `No cumple inclusión (${c.slice(0, sep)}): ${c.slice(sep + 2)}`
      : `No cumple criterio de inclusión ${i + 1}: ${c}`)
  })
  const exclusion = parseCriteria(review?.exclusion_criteria).map((c, i) => clip(`Criterio de exclusión ${i + 1}: ${c}`))
  const custom = loadCustomReasons(review)
  const taken = new Set([...inclusion, ...exclusion, ...custom])
  return [
    { label: 'No cumple los criterios de inclusión', reasons: inclusion },
    { label: 'Cumple un criterio de exclusión', reasons: exclusion },
    { label: 'Motivos guardados en esta revisión', reasons: custom },
    { label: 'Motivos generales', reasons: GENERIC_EXCLUSION_REASONS.filter(r => !taken.has(r)) },
  ].filter(g => g.reasons.length > 0)
}
