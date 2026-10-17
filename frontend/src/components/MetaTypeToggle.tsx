import { GitCompare, Percent } from 'lucide-react'

export const OBSERVATIONAL_TYPES = [
  'Estudio de cohorte prospectivo',
  'Estudio de cohorte retrospectivo',
  'Estudio transversal (corte transversal)',
  'Serie de casos',
]

/** Study types after switching to a proportion meta-analysis: keep the author's choice and add
 * the observational designs single-arm proportions come from. */
export function withObservationalTypes(typesOfStudies: string | null | undefined): string {
  const current = (typesOfStudies || '').split(', ').filter(Boolean)
  return [...current, ...OBSERVATIONAL_TYPES.filter(t => !current.includes(t))].join(', ')
}

interface Props {
  effectMeasure: string | null | undefined
  onSelect: (kind: 'comparative' | 'proportion') => void
}

export default function MetaTypeToggle({ effectMeasure, onSelect }: Props) {
  const isProp = effectMeasure === 'PROP'
  const base = 'flex-1 flex items-start gap-2 rounded-lg border-2 p-3 text-left transition-colors'
  const on = 'border-cochrane-500 bg-cochrane-50 text-cochrane-800'
  const off = 'border-gray-200 text-gray-600 hover:border-gray-300'
  return (
    <div>
      <label className="label">Tipo de metaanálisis</label>
      <div className="flex flex-col sm:flex-row gap-2">
        <button type="button" className={`${base} ${!isProp ? on : off}`} onClick={() => onSelect('comparative')}>
          <GitCompare size={18} className="mt-0.5 shrink-0" />
          <span>
            <span className="block text-sm font-semibold">Comparativo (dos grupos)</span>
            <span className="block text-xs opacity-80">Intervención vs. comparador: OR, RR, RD, MD o SMD.</span>
          </span>
        </button>
        <button type="button" className={`${base} ${isProp ? on : off}`} onClick={() => onSelect('proportion')}>
          <Percent size={18} className="mt-0.5 shrink-0" />
          <span>
            <span className="block text-sm font-semibold">Proporciones (un solo brazo)</span>
            <span className="block text-xs opacity-80">
              Estudios observacionales unicéntricos y multicéntricos, con análisis de sensibilidad
              restringido a los multicéntricos.
            </span>
          </span>
        </button>
      </div>
    </div>
  )
}
