import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { ArrowLeft, Download, Save } from 'lucide-react'
import { getReview, updateReview, generateSection, exportPdf, type Review } from '../services/api'
import SectionEditor from '../components/SectionEditor'
import StudiesTable from '../components/StudiesTable'
import AnalysisPanel from '../components/AnalysisPanel'
import PrismaPanel from '../components/PrismaPanel'
import ReferencesSection from '../components/ReferencesSection'

const SECTIONS = [
  { key: 'abstract', title: 'Resumen (Abstract)' },
  { key: 'background', title: 'Antecedentes (Background)' },
  { key: 'objectives', title: 'Objetivos (Objectives)' },
  { key: 'methods', title: 'Métodos (Methods)' },
  { key: 'results', title: 'Resultados (Results)' },
  { key: 'discussion', title: 'Discusión (Discussion)' },
]

const SECTION_FIELD: Record<string, keyof Review> = {
  abstract: 'abstract',
  background: 'background_text',
  objectives: 'objectives',
  methods: 'methods_text',
  results: 'results_text',
  discussion: 'discussion',
}

export default function ReviewEditor() {
  const { id } = useParams<{ id: string }>()
  const reviewId = Number(id)
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [generatingSection, setGeneratingSection] = useState<string | null>(null)
  const [pico, setPico] = useState<Partial<Review>>({})
  const [picoDirty, setPicoDirty] = useState(false)

  const { data: review, isLoading } = useQuery({
    queryKey: ['review', reviewId],
    queryFn: () => getReview(reviewId),
  })

  useEffect(() => {
    if (review && !picoDirty) {
      setPico({
        title: review.title, population: review.population,
        intervention: review.intervention, comparison: review.comparison,
        outcomes: review.outcomes, prospero_id: review.prospero_id,
        effect_measure: review.effect_measure, model_type: review.model_type,
      })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [review?.id])

  const updateMutation = useMutation({
    mutationFn: (data: Partial<Review>) => updateReview(reviewId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['review', reviewId] })
      toast.success('Guardado correctamente')
      setPicoDirty(false)
    },
    onError: () => toast.error('Error al guardar'),
  })

  const handleSaveSection = (field: keyof Review) => (text: string) => {
    updateMutation.mutate({ [field]: text } as Partial<Review>)
  }

  const handleGenerate = async (section: string) => {
    setGeneratingSection(section)
    try {
      const res = await generateSection(reviewId, section)
      const field = SECTION_FIELD[section]
      qc.setQueryData(['review', reviewId], (prev: Review | undefined) =>
        prev ? { ...prev, [field]: res.text } : prev
      )
      toast.success(`${section} generated`)
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Generation failed')
    } finally {
      setGeneratingSection(null)
    }
  }

  const handleExportPdf = async () => {
    try {
      const blob = await exportPdf(reviewId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${review?.title?.replace(/\s+/g, '_') || 'review'}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      toast.error('PDF export failed')
    }
  }

  if (isLoading) return (
    <div className="flex items-center justify-center min-h-screen">
      <p className="text-gray-400">Cargando revisión...</p>
    </div>
  )
  if (!review) return (
    <div className="flex items-center justify-center min-h-screen">
      <p className="text-red-500">Revisión no encontrada</p>
    </div>
  )

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <button
            onClick={() => navigate('/dashboard')}
            className="flex items-center gap-1 text-sm text-gray-400 hover:text-gray-700 mb-2"
          >
            <ArrowLeft size={15} /> Inicio (Dashboard)
          </button>
          <h2 className="text-xl font-bold text-gray-900 leading-tight">{review.title}</h2>
          <div className="flex items-center gap-3 mt-1 text-xs text-gray-400">
            {review.prospero_id && <span>PROSPERO: {review.prospero_id}</span>}
            <span>{review.studies?.length || 0} estudios</span>
            <span className="capitalize">{review.status}</span>
          </div>
        </div>
        <button onClick={handleExportPdf} className="btn-secondary">
          <Download size={16} /> Exportar PDF (Export PDF)
        </button>
      </div>

      {/* PICO quick edit */}
      <div className="card p-5 mb-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">PICO y Configuración (Settings)</h3>
          {picoDirty && (
            <button onClick={() => updateMutation.mutate(pico)} className="btn-secondary text-xs">
              <Save size={13} /> Guardar PICO (Save)
            </button>
          )}
        </div>
        <div className="grid grid-cols-2 gap-3">
          {[
            { field: 'population', label: 'Población (Population - P)' },
            { field: 'intervention', label: 'Intervención (Intervention - I)' },
            { field: 'comparison', label: 'Comparación (Comparison - C)' },
            { field: 'outcomes', label: 'Desenlaces (Outcomes - O)' },
          ].map(({ field, label }) => (
            <div key={field}>
              <label className="label">{label}</label>
              <input
                className="input text-sm"
                value={(pico as any)[field] || ''}
                onChange={(e) => {
                  setPico((p) => ({ ...p, [field]: e.target.value }))
                  setPicoDirty(true)
                }}
              />
            </div>
          ))}
          <div>
            <label className="label">Medida del efecto (Effect measure)</label>
            <select
              className="input text-sm"
              value={pico.effect_measure || 'OR'}
              onChange={(e) => { setPico((p) => ({ ...p, effect_measure: e.target.value })); setPicoDirty(true) }}
            >
              <option value="OR">OR – Razón de Momios (Odds Ratio)</option>
              <option value="RR">RR – Riesgo Relativo (Risk Ratio)</option>
              <option value="RD">RD – Diferencia de Riesgos (Risk Difference)</option>
              <option value="MD">MD – Diferencia de Medias (Mean Difference)</option>
              <option value="SMD">SMD – DM Estandarizada (Standardised MD)</option>
              <option value="PRECALCULATED">Precalculado (Pre-calculated ES)</option>
            </select>
          </div>
          <div>
            <label className="label">Modelo (Model)</label>
            <select
              className="input text-sm"
              value={pico.model_type || 'random'}
              onChange={(e) => { setPico((p) => ({ ...p, model_type: e.target.value })); setPicoDirty(true) }}
            >
              <option value="random">Efectos aleatorios (Random-effects)</option>
              <option value="fixed">Efectos fijos (Fixed-effects)</option>
            </select>
          </div>
        </div>
      </div>

      {/* Studies */}
      <div className="mb-4">
        <StudiesTable reviewId={reviewId} studies={review.studies || []} />
      </div>

      {/* Analysis */}
      <div className="mb-4">
        <AnalysisPanel reviewId={reviewId} />
      </div>

      {/* PRISMA 2020 */}
      <div className="mb-4">
        <PrismaPanel reviewId={reviewId} review={review} />
      </div>

      {/* Cochrane sections */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide pt-2">
          Secciones de la Revisión (Review Sections)
        </h3>
        {SECTIONS.map((s) => {
          const field = SECTION_FIELD[s.key] as keyof Review
          const value = (review[field] as string) || ''
          return (
            <SectionEditor
              key={s.key}
              title={s.title}
              sectionKey={s.key}
              value={value}
              onSave={handleSaveSection(field)}
              onGenerate={handleGenerate}
              generating={generatingSection === s.key}
              defaultOpen={s.key === 'abstract'}
            />
          )
        })}

        {/* Referencias bibliográficas */}
        <ReferencesSection
          reviewId={reviewId}
          currentStyle={review.citation_style || 'vancouver'}
          currentText={review.references || ''}
        />
      </div>
    </div>
  )
}
