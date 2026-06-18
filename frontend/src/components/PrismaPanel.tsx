import { useState } from 'react'
import { GitBranch, ChevronDown, ChevronUp, RefreshCw, Download, Wand2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { updateReview, getPrismaDiagram, autofillPrisma, type Review } from '../services/api'

interface Props {
  reviewId: number
  review: Review
}

type PrismaKey =
  | 'prisma_db_names' | 'prisma_other_sources' | 'prisma_duplicates_removed'
  | 'prisma_other_removed' | 'prisma_screened' | 'prisma_excluded_screening'
  | 'prisma_sought' | 'prisma_not_retrieved' | 'prisma_assessed'
  | 'prisma_excluded_eligibility' | 'prisma_exclusion_reasons'
  | 'prisma_included' | 'prisma_reports_included'

const FIELDS: { key: PrismaKey; label: string; placeholder: string; type: 'text' | 'number'; hint?: string }[] = [
  {
    key: 'prisma_db_names',
    label: 'Bases de datos (DB names & counts)',
    placeholder: 'PubMed=45,Scopus=32,EMBASE=28',
    type: 'text',
    hint: 'Formato: Nombre=N, separados por comas',
  },
  {
    key: 'prisma_other_sources',
    label: 'Otras fuentes (Other sources)',
    placeholder: '5',
    type: 'number',
    hint: 'Registros de otras fuentes (registros, literatura gris)',
  },
  {
    key: 'prisma_duplicates_removed',
    label: 'Duplicados eliminados (Duplicates removed)',
    placeholder: '18',
    type: 'number',
  },
  {
    key: 'prisma_other_removed',
    label: 'Otros eliminados antes de cribado (Other removed)',
    placeholder: '3',
    type: 'number',
    hint: 'Registros inelegibles antes del cribado',
  },
  {
    key: 'prisma_screened',
    label: 'Registros cribados (Records screened)',
    placeholder: '86',
    type: 'number',
  },
  {
    key: 'prisma_excluded_screening',
    label: 'Excluidos en cribado (Excluded at screening)',
    placeholder: '61',
    type: 'number',
  },
  {
    key: 'prisma_sought',
    label: 'Textos completos buscados (Reports sought)',
    placeholder: '25',
    type: 'number',
  },
  {
    key: 'prisma_not_retrieved',
    label: 'No recuperados (Not retrieved)',
    placeholder: '2',
    type: 'number',
  },
  {
    key: 'prisma_assessed',
    label: 'Evaluados para elegibilidad (Assessed for eligibility)',
    placeholder: '23',
    type: 'number',
  },
  {
    key: 'prisma_excluded_eligibility',
    label: 'Excluidos en elegibilidad (Excluded at eligibility)',
    placeholder: '11',
    type: 'number',
  },
  {
    key: 'prisma_exclusion_reasons',
    label: 'Razones de exclusión (Exclusion reasons)',
    placeholder: 'Población incorrecta=5,Sin desenlace=4,Diseño inadecuado=2',
    type: 'text',
    hint: 'Formato: Razón=N, separadas por comas',
  },
  {
    key: 'prisma_included',
    label: 'Estudios incluidos (Studies included)',
    placeholder: '14',
    type: 'number',
    hint: 'Total de estudios marcados como incluidos (✓) en la tabla de Estudios',
  },
  {
    key: 'prisma_reports_included',
    label: 'Reportes incluidos en el meta-análisis (Reports included)',
    placeholder: '6',
    type: 'number',
    hint: 'Cuántos de los incluidos tienen datos suficientes para entrar al meta-análisis (k). Se actualiza automáticamente al correr el análisis estadístico — puede ser menor que "Estudios incluidos" si a algunos les faltan datos.',
  },
]

export default function PrismaPanel({ reviewId, review }: Props) {
  const [open, setOpen] = useState(false)
  const [prismaImg, setPrismaImg] = useState<string | null>(null)
  const [generating, setGenerating] = useState(false)
  const [autofilling, setAutofilling] = useState(false)
  const [form, setForm] = useState<Partial<Review>>({})
  const [dirty, setDirty] = useState(false)
  const qc = useQueryClient()

  const saveMutation = useMutation({
    mutationFn: (data: Partial<Review>) => updateReview(reviewId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['review', reviewId] })
      toast.success('Datos PRISMA guardados')
      setDirty(false)
    },
    onError: () => toast.error('Error al guardar datos PRISMA'),
  })

  const setField = (key: PrismaKey, value: string) => {
    setForm(f => ({ ...f, [key]: value === '' ? null : value }))
    setDirty(true)
  }

  const getValue = (key: PrismaKey): string => {
    const formVal = form[key as keyof Review]
    if (formVal !== undefined) return formVal == null ? '' : String(formVal)
    const reviewVal = review[key as keyof Review]
    return reviewVal == null ? '' : String(reviewVal)
  }

  const handleAutofill = async () => {
    setAutofilling(true)
    try {
      const res = await autofillPrisma(reviewId)
      // Populate the form with AI-generated values
      setForm(res.data as Partial<Review>)
      setDirty(true)
      qc.invalidateQueries({ queryKey: ['review', reviewId] })
      toast.success('Datos PRISMA auto-generados con IA. Revisa y guarda.')
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Error al auto-generar PRISMA')
    } finally {
      setAutofilling(false)
    }
  }

  const handleGenerate = async () => {
    if (dirty) {
      await saveMutation.mutateAsync(form)
    }
    setGenerating(true)
    try {
      const res = await getPrismaDiagram(reviewId)
      setPrismaImg(res.prisma_b64)
      toast.success('Diagrama PRISMA 2020 generado')
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Error al generar PRISMA')
    } finally {
      setGenerating(false)
    }
  }

  const handleDownload = () => {
    if (!prismaImg) return
    const a = document.createElement('a')
    a.href = `data:image/png;base64,${prismaImg}`
    a.download = `PRISMA_2020_${reviewId}.png`
    a.click()
  }

  return (
    <div className="card overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-gray-50"
      >
        <div className="flex items-center gap-2">
          <GitBranch size={18} className="text-cochrane-500" />
          <span className="font-semibold text-gray-800">
            Diagrama de flujo PRISMA 2020 (PRISMA 2020 Flow Diagram)
          </span>
          {prismaImg && (
            <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
              Generado
            </span>
          )}
        </div>
        {open ? <ChevronUp size={18} className="text-gray-400" /> : <ChevronDown size={18} className="text-gray-400" />}
      </button>

      {open && (
        <div className="border-t border-gray-100 p-5 space-y-5">
          <p className="text-xs text-gray-500">
            Ingresa los conteos del proceso de búsqueda y selección para generar el diagrama
            de flujo PRISMA 2020 estándar.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {FIELDS.map(({ key, label, placeholder, type, hint }) => (
              <div key={key}>
                <label className="label">{label}</label>
                <input
                  className="input text-xs"
                  type={type}
                  placeholder={placeholder}
                  value={getValue(key)}
                  onChange={e => setField(key, e.target.value)}
                />
                {hint && <p className="text-[10px] text-gray-400 mt-0.5">{hint}</p>}
              </div>
            ))}
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              type="button"
              onClick={handleAutofill}
              disabled={autofilling || generating}
              className="btn-secondary text-xs"
            >
              <Wand2 size={14} className={autofilling ? 'animate-spin' : ''} />
              {autofilling ? 'Generando con IA...' : 'Auto-generar con IA'}
            </button>
            {dirty && (
              <button
                type="button"
                onClick={() => saveMutation.mutate(form)}
                disabled={saveMutation.isPending}
                className="btn-secondary text-xs"
              >
                {saveMutation.isPending ? 'Guardando...' : 'Guardar datos'}
              </button>
            )}
            <button
              type="button"
              onClick={handleGenerate}
              disabled={generating || autofilling}
              className="btn-primary text-xs"
            >
              <RefreshCw size={14} className={generating ? 'animate-spin' : ''} />
              {generating ? 'Generando...' : 'Generar diagrama PRISMA 2020'}
            </button>
            {prismaImg && (
              <button
                type="button"
                onClick={handleDownload}
                className="btn-secondary text-xs"
              >
                <Download size={14} /> Descargar PNG
              </button>
            )}
          </div>

          {prismaImg && (
            <div>
              <p className="text-sm font-semibold text-gray-700 mb-2">
                Diagrama PRISMA 2020
              </p>
              <img
                src={`data:image/png;base64,${prismaImg}`}
                alt="PRISMA 2020 Flow Diagram"
                className="w-full rounded-lg border border-gray-200 shadow-sm"
              />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
