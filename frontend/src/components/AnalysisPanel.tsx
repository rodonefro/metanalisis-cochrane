import { useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BarChart2, ChevronDown, ChevronUp, Play, Wand2, Download, Filter, Table } from 'lucide-react'
import toast from 'react-hot-toast'
import { runAnalysis, getLatestAnalysis, generateSection, getForestPlot, getFunnelPlot, getGradeTable } from '../services/api'
import type { Analysis } from '../services/api'

interface Props {
  reviewId: number
}

function PlotCard({
  title,
  subtitle,
  icon: Icon,
  iconColor,
  b64,
  loading,
  interpretation,
  onGenerate,
  imgClass = 'w-full',
}: {
  title: string
  subtitle: string
  icon: React.ElementType
  iconColor: string
  b64: string | null
  loading: boolean
  interpretation?: string
  onGenerate: () => void
  imgClass?: string
}) {
  const handleDownload = () => {
    if (!b64) return
    const a = document.createElement('a')
    a.href = `data:image/png;base64,${b64}`
    a.download = `${title.replace(/\s+/g, '_')}.png`
    a.click()
  }

  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden bg-white shadow-sm">
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <Icon size={16} className={iconColor} />
          <div>
            <p className="text-sm font-semibold text-gray-800">{title}</p>
            <p className="text-xs text-gray-400">{subtitle}</p>
          </div>
        </div>
        <div className="flex gap-2">
          {b64 && (
            <button
              type="button"
              onClick={handleDownload}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded-md border border-gray-200 hover:bg-gray-100 text-gray-600"
            >
              <Download size={12} />
              PNG
            </button>
          )}
          <button
            type="button"
            onClick={onGenerate}
            disabled={loading}
            className="btn-primary text-xs py-1"
          >
            <Play size={12} />
            {loading ? 'Generando + interpretando...' : b64 ? 'Regenerar' : 'Generar'}
          </button>
        </div>
      </div>

      {b64 ? (
        <div className="p-3 space-y-3">
          <img
            src={`data:image/png;base64,${b64}`}
            alt={title}
            className={`${imgClass} rounded-lg border border-gray-100`}
          />
          {interpretation && (
            <div className="bg-cochrane-50 border border-cochrane-100 rounded-lg p-3">
              <div className="flex items-center gap-1.5 mb-1.5">
                <Wand2 size={12} className="text-cochrane-500" />
                <p className="text-xs font-semibold text-cochrane-700">Interpretación IA (Claude)</p>
              </div>
              <p className="text-xs text-gray-700 leading-relaxed whitespace-pre-wrap">{interpretation}</p>
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-10 text-gray-300">
          <Icon size={40} strokeWidth={1} />
          <p className="text-xs mt-2">
            {loading ? 'Generando gráfica e interpretación IA...' : 'Presiona "Generar" para crear esta gráfica'}
          </p>
        </div>
      )}
    </div>
  )
}

export default function AnalysisPanel({ reviewId }: Props) {
  const [open, setOpen] = useState(true)
  const [forestB64, setForestB64] = useState<string | null>(null)
  const [funnelB64, setFunnelB64] = useState<string | null>(null)
  const [gradeB64, setGradeB64] = useState<string | null>(null)
  const [forestInterp, setForestInterp] = useState<string>('')
  const [funnelInterp, setFunnelInterp] = useState<string>('')
  const [gradeInterp, setGradeInterp] = useState<string>('')
  const [loadingForest, setLoadingForest] = useState(false)
  const [loadingFunnel, setLoadingFunnel] = useState(false)
  const [loadingGrade, setLoadingGrade] = useState(false)
  // Legacy manual interpretation (kept for full Cochrane-style combined text)
  const [interpretation, setInterpretation] = useState<string>('')
  const [interpreting, setInterpreting] = useState(false)
  const qc = useQueryClient()

  const { data: analysis } = useQuery<Analysis>({
    queryKey: ['analysis', reviewId],
    queryFn: () => getLatestAnalysis(reviewId),
    enabled: open,
    retry: false,
  })

  useEffect(() => {
    if (analysis?.forest_plot_b64) setForestB64(analysis.forest_plot_b64)
    if (analysis?.funnel_plot_b64) setFunnelB64(analysis.funnel_plot_b64)
  }, [analysis])

  const runMutation = useMutation({
    mutationFn: () => runAnalysis(reviewId),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['analysis', reviewId] })
      if (data.forest_plot_b64) setForestB64(data.forest_plot_b64)
      if (data.funnel_plot_b64) setFunnelB64(data.funnel_plot_b64)
      toast.success('Análisis completado')
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Error en el análisis'),
  })

  const handleForest = async () => {
    setLoadingForest(true)
    try {
      const res = await getForestPlot(reviewId)
      setForestB64(res.forest_b64)
      if (res.interpretation) setForestInterp(res.interpretation)
      toast.success('Forest Plot generado')
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Ejecuta primero el meta-análisis')
    } finally {
      setLoadingForest(false)
    }
  }

  const handleFunnel = async () => {
    setLoadingFunnel(true)
    try {
      const res = await getFunnelPlot(reviewId)
      setFunnelB64(res.funnel_b64)
      if (res.interpretation) setFunnelInterp(res.interpretation)
      toast.success('Funnel Plot generado')
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Ejecuta primero el meta-análisis')
    } finally {
      setLoadingFunnel(false)
    }
  }

  const handleGrade = async () => {
    setLoadingGrade(true)
    try {
      const res = await getGradeTable(reviewId)
      setGradeB64(res.grade_b64)
      if (res.interpretation) setGradeInterp(res.interpretation)
      toast.success('Tabla GRADE generada')
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Ejecuta primero el meta-análisis')
    } finally {
      setLoadingGrade(false)
    }
  }

  const handleInterpret = async () => {
    setInterpreting(true)
    try {
      const res = await generateSection(reviewId, 'plot_interpretation')
      setInterpretation(res.text)
      toast.success('Interpretación generada')
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Error al interpretar los gráficos')
    } finally {
      setInterpreting(false)
    }
  }

  const results = (() => {
    if (!analysis?.results_json) return null
    try { return JSON.parse(analysis.results_json) } catch { return null }
  })()

  return (
    <div className="card overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-gray-50"
      >
        <div className="flex items-center gap-2">
          <BarChart2 size={18} className="text-cochrane-500" />
          <span className="font-semibold text-gray-800">Análisis Estadístico (Statistical Analysis)</span>
          {analysis && (
            <span className="text-xs bg-cochrane-100 text-cochrane-600 px-2 py-0.5 rounded-full">
              {new Date(analysis.created_at).toLocaleDateString()}
            </span>
          )}
        </div>
        {open ? <ChevronUp size={18} className="text-gray-400" /> : <ChevronDown size={18} className="text-gray-400" />}
      </button>

      {open && (
        <div className="border-t border-gray-100 p-5 space-y-6">
          {/* Step 1: Run analysis */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => runMutation.mutate()}
              disabled={runMutation.isPending}
              className="btn-primary"
            >
              <Play size={15} />
              {runMutation.isPending ? 'Ejecutando análisis...' : 'Ejecutar Metaanálisis (Run Meta-Analysis)'}
            </button>
            <p className="text-xs text-gray-400">Paso 1: ejecuta el análisis estadístico para activar las gráficas</p>
          </div>

          {/* Summary stats */}
          {results && (
            <div className="bg-cochrane-50 rounded-lg p-4">
              <p className="text-xs font-semibold text-cochrane-600 mb-2 uppercase tracking-wide">
                Resumen de resultados
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  { label: 'Estudios (k)', value: results.k },
                  { label: 'Participantes (N)', value: results.total_n },
                  {
                    label: `${results.effect_measure} combinado`,
                    value: results.pooled
                      ? `${results.pooled.effect?.toFixed(2)} [${results.pooled.ci_lower?.toFixed(2)}, ${results.pooled.ci_upper?.toFixed(2)}]`
                      : '—',
                  },
                  { label: 'Heterogeneidad I²', value: `${results.heterogeneity?.I2?.toFixed(0)}%` },
                ].map(({ label, value }) => (
                  <div key={label} className="bg-white rounded-lg p-3">
                    <p className="text-xs text-gray-500">{label}</p>
                    <p className="font-bold text-gray-900 mt-0.5">{String(value)}</p>
                  </div>
                ))}
              </div>
              <p className="text-xs text-gray-500 mt-2">
                Q={results.heterogeneity?.Q?.toFixed(1)}, df={results.heterogeneity?.Q_df},
                p={results.heterogeneity?.Q_pvalue?.toFixed(3)}, τ²={results.heterogeneity?.tau2?.toFixed(4)},
                modelo: {results.model === 'random' ? 'efectos aleatorios' : 'efectos fijos'}
              </p>
            </div>
          )}

          {/* Step 2: Individual plot buttons */}
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
              Paso 2 — Generar gráficas individualmente
            </p>
            <div className="grid grid-cols-1 gap-4">
              <PlotCard
                title="Forest Plot (Diagrama de bosque)"
                subtitle="Efecto combinado por estudio con intervalos de confianza"
                icon={BarChart2}
                iconColor="text-cochrane-500"
                b64={forestB64}
                loading={loadingForest}
                interpretation={forestInterp}
                onGenerate={handleForest}
              />

              <PlotCard
                title="Funnel Plot (Gráfico de embudo)"
                subtitle="Detección de sesgo de publicación"
                icon={Filter}
                iconColor="text-blue-500"
                b64={funnelB64}
                loading={loadingFunnel}
                interpretation={funnelInterp}
                onGenerate={handleFunnel}
                imgClass="w-full max-w-lg mx-auto block"
              />

              <PlotCard
                title="Tabla GRADE (Certeza de la evidencia)"
                subtitle="Evaluación GRADE: riesgo de sesgo, inconsistencia, imprecisión"
                icon={Table}
                iconColor="text-emerald-500"
                b64={gradeB64}
                loading={loadingGrade}
                interpretation={gradeInterp}
                onGenerate={handleGrade}
              />
            </div>
          </div>

          {/* AI interpretation */}
          {results && (
            <div className="border border-dashed border-cochrane-300 rounded-lg p-4 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-cochrane-700">
                  Interpretación IA de gráficos (AI Plot Interpretation)
                </p>
                <button
                  type="button"
                  onClick={handleInterpret}
                  disabled={interpreting}
                  className="btn-primary text-xs"
                >
                  <Wand2 size={13} />
                  {interpreting ? 'Interpretando...' : 'Interpretar con IA'}
                </button>
              </div>
              {interpretation && (
                <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
                  {interpretation}
                </p>
              )}
              {!interpretation && !interpreting && (
                <p className="text-xs text-gray-400 italic">
                  La IA analizará el diagrama de bosque, gráfico de embudo y heterogeneidad,
                  generando una interpretación académica Cochrane.
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
