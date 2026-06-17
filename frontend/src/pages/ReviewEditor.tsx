import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { ArrowLeft, Download, Save, CheckCircle2, Loader2 } from 'lucide-react'
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
  const [savedAt, setSavedAt] = useState<Date | null>(null)
  const autoSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

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
        inclusion_criteria: review.inclusion_criteria,
        exclusion_criteria: review.exclusion_criteria,
      })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [review?.id])

  const updateMutation = useMutation({
    mutationFn: (data: Partial<Review>) => updateReview(reviewId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['review', reviewId] })
      setSavedAt(new Date())
      setPicoDirty(false)
    },
    onError: () => toast.error('Error al guardar'),
  })

  // Auto-save PICO 2 seconds after last change
  const handlePicoChange = (field: string, value: string) => {
    setPico((p) => ({ ...p, [field]: value }))
    setPicoDirty(true)
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
    autoSaveTimer.current = setTimeout(() => {
      updateMutation.mutate({ ...pico, [field]: value } as Partial<Review>)
    }, 2000)
  }

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
        <div className="flex items-center gap-2">
          {/* Save indicator */}
          {updateMutation.isPending ? (
            <span className="flex items-center gap-1.5 text-xs text-gray-400">
              <Loader2 size={13} className="animate-spin" /> Guardando...
            </span>
          ) : savedAt ? (
            <span className="flex items-center gap-1.5 text-xs text-green-600">
              <CheckCircle2 size={13} /> Guardado {savedAt.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' })}
            </span>
          ) : picoDirty ? (
            <span className="text-xs text-amber-500">Cambios sin guardar</span>
          ) : null}

          <button
            onClick={() => { updateMutation.mutate(pico); toast.success('Guardado') }}
            disabled={updateMutation.isPending}
            className="btn-primary"
          >
            <Save size={15} /> Guardar
          </button>
          <button onClick={handleExportPdf} className="btn-secondary">
            <Download size={16} /> Exportar PDF
          </button>
        </div>
      </div>

      {/* PICO quick edit */}
      <div className="card p-5 mb-4">
        <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
          PICO y Configuración
        </h3>
        <div className="grid grid-cols-2 gap-3">
          {[
            { field: 'population',   label: 'Población (P)' },
            { field: 'intervention', label: 'Intervención (I)' },
            { field: 'comparison',   label: 'Comparación (C)' },
            { field: 'outcomes',     label: 'Desenlaces (O)' },
          ].map(({ field, label }) => (
            <div key={field}>
              <label className="label">{label}</label>
              <input
                className="input text-sm"
                value={(pico as any)[field] || ''}
                onChange={(e) => handlePicoChange(field, e.target.value)}
              />
            </div>
          ))}
          <div>
            <label className="label">Medida del efecto</label>
            <select
              className="input text-sm"
              value={pico.effect_measure || 'OR'}
              onChange={(e) => handlePicoChange('effect_measure', e.target.value)}
            >
              <option value="OR">OR – Odds Ratio</option>
              <option value="RR">RR – Riesgo Relativo</option>
              <option value="RD">RD – Diferencia de Riesgos</option>
              <option value="MD">MD – Diferencia de Medias</option>
              <option value="SMD">SMD – DM Estandarizada</option>
              <option value="PRECALCULATED">Precalculado</option>
            </select>
          </div>
          <div>
            <label className="label">Modelo estadístico</label>
            <select
              className="input text-sm"
              value={pico.model_type || 'random'}
              onChange={(e) => handlePicoChange('model_type', e.target.value)}
            >
              <option value="random">Efectos aleatorios</option>
              <option value="fixed">Efectos fijos</option>
            </select>
          </div>
        </div>

        {/* Criterios de selección */}
        <div className="mt-3 grid grid-cols-2 gap-3">
          <div>
            <label className="label text-green-700">Criterios de Inclusión</label>
            <textarea
              className="input text-sm resize-none border-green-200 focus:border-green-400"
              rows={3}
              value={(pico as any).inclusion_criteria || ''}
              onChange={(e) => handlePicoChange('inclusion_criteria', e.target.value)}
              placeholder="Ej: ECA, adultos ≥18 años, seguimiento ≥3 meses..."
            />
          </div>
          <div>
            <label className="label text-red-700">Criterios de Exclusión</label>
            <textarea
              className="input text-sm resize-none border-red-200 focus:border-red-400"
              rows={3}
              value={(pico as any).exclusion_criteria || ''}
              onChange={(e) => handlePicoChange('exclusion_criteria', e.target.value)}
              placeholder="Ej: Estudios observacionales, población pediátrica..."
            />
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
