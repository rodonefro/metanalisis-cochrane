import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BarChart2, ChevronDown, ChevronUp, Play, Wand2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { runAnalysis, getLatestAnalysis, generateSection } from '../services/api'

interface Props {
  reviewId: number
}

export default function AnalysisPanel({ reviewId }: Props) {
  const [open, setOpen] = useState(false)
  const [interpretation, setInterpretation] = useState<string>('')
  const [interpreting, setInterpreting] = useState(false)
  const qc = useQueryClient()

  const { data: analysis } = useQuery({
    queryKey: ['analysis', reviewId],
    queryFn: () => getLatestAnalysis(reviewId),
    enabled: open,
    retry: false,
  })

  const runMutation = useMutation({
    mutationFn: () => runAnalysis(reviewId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['analysis', reviewId] })
      toast.success('Análisis completado')
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Error en el análisis'),
  })

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
        <div className="border-t border-gray-100 p-5 space-y-5">
          <button
            type="button"
            onClick={() => runMutation.mutate()}
            disabled={runMutation.isPending}
            className="btn-primary"
          >
            <Play size={15} />
            {runMutation.isPending ? 'Ejecutando análisis...' : 'Ejecutar Metaanálisis (Run Meta-Analysis)'}
          </button>

          {results && (
            <>
              {/* Resumen estadístico */}
              <div className="bg-cochrane-50 rounded-lg p-4">
                <p className="text-xs font-semibold text-cochrane-600 mb-2 uppercase tracking-wide">
                  Resumen de resultados (Results Summary)
                </p>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {[
                    { label: 'Estudios (k)', value: results.k },
                    { label: 'Participantes (N)', value: results.total_n },
                    {
                      label: `${results.effect_measure} combinado (Pooled)`,
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
                {results.prediction_interval?.lower != null && (
                  <p className="text-xs text-gray-500 mt-1">
                    Intervalo de predicción (Prediction interval):
                    [{results.prediction_interval.lower?.toFixed(2)}, {results.prediction_interval.upper?.toFixed(2)}]
                  </p>
                )}
              </div>

              {/* Diagrama de bosque */}
              {analysis?.forest_plot_b64 && (
                <div>
                  <p className="text-sm font-semibold text-gray-700 mb-2">
                    Diagrama de bosque (Forest Plot)
                  </p>
                  <img
                    src={`data:image/png;base64,${analysis.forest_plot_b64}`}
                    alt="Diagrama de bosque"
                    className="w-full rounded-lg border border-gray-200"
                  />
                </div>
              )}

              {/* Gráfico de embudo */}
              {analysis?.funnel_plot_b64 && (
                <div>
                  <p className="text-sm font-semibold text-gray-700 mb-2">
                    Gráfico de embudo (Funnel Plot)
                  </p>
                  <img
                    src={`data:image/png;base64,${analysis.funnel_plot_b64}`}
                    alt="Gráfico de embudo"
                    className="w-full max-w-lg rounded-lg border border-gray-200"
                  />
                </div>
              )}

              {/* Riesgo de sesgo */}
              {analysis?.rob_plot_b64 && (
                <div>
                  <p className="text-sm font-semibold text-gray-700 mb-2">
                    Riesgo de sesgo (Risk of Bias — Cochrane RoB 2)
                  </p>
                  <img
                    src={`data:image/png;base64,${analysis.rob_plot_b64}`}
                    alt="Riesgo de sesgo"
                    className="w-full rounded-lg border border-gray-200"
                  />
                </div>
              )}

              {/* Interpretación IA de los gráficos */}
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
                    {interpreting ? 'Interpretando...' : 'Interpretar con IA (Interpret with AI)'}
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
            </>
          )}
        </div>
      )}
    </div>
  )
}
