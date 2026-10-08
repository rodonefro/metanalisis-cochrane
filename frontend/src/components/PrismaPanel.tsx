import { useState } from 'react'
import { GitBranch, ChevronDown, ChevronUp, RefreshCw, Download, Plus, Trash2, AlertTriangle, CheckCircle2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  updateReview, getPrismaDiagram, computePrisma, listSearches, createSearch, updateSearch, deleteSearch,
  type Review, type SearchSource, type PrismaFlow,
} from '../services/api'

interface Props {
  reviewId: number
  review: Review
}

const FLOW_ROWS: { key: string; label: string }[] = [
  { key: 'prisma_duplicates_removed', label: 'Duplicados eliminados' },
  { key: 'prisma_other_removed', label: 'Eliminados por otras razones antes del cribado' },
  { key: 'prisma_screened', label: 'Registros cribados (título/resumen)' },
  { key: 'prisma_excluded_screening', label: 'Excluidos en el cribado' },
  { key: 'prisma_sought', label: 'Textos completos buscados' },
  { key: 'prisma_not_retrieved', label: 'Textos completos no recuperados' },
  { key: 'prisma_assessed', label: 'Evaluados a texto completo' },
  { key: 'prisma_excluded_eligibility', label: 'Excluidos a texto completo' },
  { key: 'prisma_included', label: 'Estudios incluidos en la revisión' },
  { key: 'prisma_reports_included', label: 'Incluidos en el metaanálisis (k)' },
]

const TYPE_LABEL: Record<string, string> = {
  database: 'Base de datos', register: 'Registro', other: 'Otros métodos',
}

function SearchRow({ reviewId, s, onChanged }: { reviewId: number; s: SearchSource; onChanged: () => void }) {
  const [draft, setDraft] = useState<Partial<SearchSource>>({})
  const val = <K extends keyof SearchSource>(k: K) => (k in draft ? draft[k] : s[k]) as SearchSource[K]
  const dirty = Object.keys(draft).length > 0

  const save = useMutation({
    mutationFn: () => updateSearch(reviewId, s.id, draft),
    onSuccess: () => { setDraft({}); onChanged(); toast.success('Búsqueda actualizada') },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Error al guardar'),
  })
  const del = useMutation({
    mutationFn: () => deleteSearch(reviewId, s.id),
    onSuccess: onChanged,
  })

  const set = (k: keyof SearchSource) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setDraft(d => ({ ...d, [k]: k === 'results_count' ? (e.target.value === '' ? null : Number(e.target.value)) : e.target.value }))

  return (
    <tr className="align-top">
      <td className="px-2 py-2">
        <input className="input text-xs" value={val('database_name') || ''} onChange={set('database_name')} />
        <select className="input text-[11px] mt-1 py-0.5" value={val('source_type')} onChange={set('source_type')}>
          {Object.entries(TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </td>
      <td className="px-2 py-2">
        <input type="date" className="input text-xs" value={val('search_date') || ''} onChange={set('search_date')} />
      </td>
      <td className="px-2 py-2 min-w-[220px]">
        <textarea className="input text-[11px] font-mono" rows={2} value={val('search_string') || ''} onChange={set('search_string')}
          placeholder="Cadena de búsqueda exacta" />
      </td>
      <td className="px-2 py-2 w-24">
        <input type="number" min={0} className="input text-xs" value={val('results_count') ?? ''} onChange={set('results_count')}
          placeholder={String(s.records_imported || 0)} title="Número de resultados que mostró la base de datos (si está vacío se usa lo importado)" />
      </td>
      <td className="px-2 py-2 text-xs text-gray-600 whitespace-nowrap">
        {s.records_imported || 0}
        <span className="text-gray-400"> ({s.duplicates_found || 0} dup.)</span>
      </td>
      <td className="px-2 py-2 whitespace-nowrap">
        {dirty && (
          <button type="button" onClick={() => save.mutate()} className="btn-primary text-[11px] px-2 py-1 mr-1">Guardar</button>
        )}
        <button
          type="button"
          onClick={() => {
            if (confirm(`¿Quitar "${s.database_name}" del registro de búsquedas? Los registros importados se conservan.`)) del.mutate()
          }}
          className="text-gray-300 hover:text-red-500"
        >
          <Trash2 size={14} />
        </button>
      </td>
    </tr>
  )
}

export default function PrismaPanel({ reviewId, review }: Props) {
  const [open, setOpen] = useState(false)
  const [prismaImg, setPrismaImg] = useState<string | null>(null)
  const [flow, setFlow] = useState<PrismaFlow | null>(null)
  const [generating, setGenerating] = useState(false)
  const [newSource, setNewSource] = useState({ database_name: '', source_type: 'database', search_date: '', search_string: '', results_count: '' })
  const [otherRemoved, setOtherRemoved] = useState<string | null>(null)
  const qc = useQueryClient()

  const { data: searches = [] } = useQuery({
    queryKey: ['searches', reviewId],
    queryFn: () => listSearches(reviewId),
    enabled: open,
  })

  const refresh = async () => {
    qc.invalidateQueries({ queryKey: ['searches', reviewId] })
    try {
      setFlow(await computePrisma(reviewId))
    } catch {
      /* shown on next generate */
    }
  }

  const addSource = useMutation({
    mutationFn: () => createSearch(reviewId, {
      database_name: newSource.database_name.trim(),
      source_type: newSource.source_type as SearchSource['source_type'],
      search_date: newSource.search_date || null,
      search_string: newSource.search_string || null,
      results_count: newSource.results_count === '' ? null : Number(newSource.results_count),
    }),
    onSuccess: () => {
      setNewSource({ database_name: '', source_type: 'database', search_date: '', search_string: '', results_count: '' })
      refresh()
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Error al agregar la fuente'),
  })

  const saveOtherRemoved = useMutation({
    mutationFn: (n: number) => updateReview(reviewId, { prisma_other_removed: n }),
    onSuccess: () => {
      setOtherRemoved(null)
      qc.invalidateQueries({ queryKey: ['review', reviewId] })
      refresh()
    },
  })

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      const res = await getPrismaDiagram(reviewId)
      setPrismaImg(res.prisma_b64)
      setFlow(res)
      qc.invalidateQueries({ queryKey: ['review', reviewId] })
      toast.success('Diagrama PRISMA 2020 generado a partir de los registros')
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

  const fields = flow?.fields
  const otherRemovedValue = otherRemoved ?? String(review.prisma_other_removed ?? 0)

  return (
    <div className="card overflow-hidden">
      <button
        type="button"
        onClick={() => { const next = !open; setOpen(next); if (next && !flow) refresh() }}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-gray-50"
      >
        <div className="flex items-center gap-2">
          <GitBranch size={18} className="text-cochrane-500" />
          <span className="font-semibold text-gray-800">
            Diagrama de flujo PRISMA 2020 (PRISMA 2020 Flow Diagram)
          </span>
          {prismaImg && (
            <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">Generado</span>
          )}
        </div>
        {open ? <ChevronUp size={18} className="text-gray-400" /> : <ChevronDown size={18} className="text-gray-400" />}
      </button>

      {open && (
        <div className="border-t border-gray-100 p-5 space-y-5">
          <p className="text-xs text-gray-500">
            El diagrama se calcula exactamente a partir de las fuentes donde se buscó y de la decisión de cribado de
            cada registro (Gestor de referencias). No se estima ningún número: si algo no cuadra, se muestra una
            advertencia para corregirlo en los datos.
          </p>

          {/* Search log */}
          <div>
            <p className="text-sm font-semibold text-gray-700 mb-2">Fuentes donde se buscó</p>
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="w-full text-xs">
                <thead className="bg-gray-50 text-gray-600">
                  <tr>
                    <th className="px-2 py-2 text-left">Fuente</th>
                    <th className="px-2 py-2 text-left">Fecha</th>
                    <th className="px-2 py-2 text-left">Estrategia de búsqueda</th>
                    <th className="px-2 py-2 text-left" title="Resultados que reportó la base de datos">N reportado</th>
                    <th className="px-2 py-2 text-left">Importados</th>
                    <th />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {searches.map(s => <SearchRow key={s.id} reviewId={reviewId} s={s} onChanged={refresh} />)}
                  <tr className="bg-gray-50 align-top">
                    <td className="px-2 py-2">
                      <input className="input text-xs" placeholder="Nueva fuente (p. ej. LILACS)" value={newSource.database_name}
                        onChange={e => setNewSource(n => ({ ...n, database_name: e.target.value }))} />
                      <select className="input text-[11px] mt-1 py-0.5" value={newSource.source_type}
                        onChange={e => setNewSource(n => ({ ...n, source_type: e.target.value }))}>
                        {Object.entries(TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                      </select>
                    </td>
                    <td className="px-2 py-2">
                      <input type="date" className="input text-xs" value={newSource.search_date}
                        onChange={e => setNewSource(n => ({ ...n, search_date: e.target.value }))} />
                    </td>
                    <td className="px-2 py-2">
                      <textarea className="input text-[11px] font-mono" rows={2} value={newSource.search_string}
                        onChange={e => setNewSource(n => ({ ...n, search_string: e.target.value }))} />
                    </td>
                    <td className="px-2 py-2">
                      <input type="number" min={0} className="input text-xs" value={newSource.results_count}
                        onChange={e => setNewSource(n => ({ ...n, results_count: e.target.value }))} />
                    </td>
                    <td className="px-2 py-2 text-gray-400">—</td>
                    <td className="px-2 py-2">
                      <button type="button" className="btn-secondary text-[11px] px-2 py-1"
                        disabled={!newSource.database_name.trim() || addSource.isPending}
                        onClick={() => addSource.mutate()}>
                        <Plus size={12} /> Agregar
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="text-[10px] text-gray-400 mt-1">
              Las fuentes se crean solas al importar en el Gestor de referencias. Agrega aquí una fuente sin
              resultados exportables (p. ej. una base que devolvió 0 registros) para que figure en el diagrama.
            </p>
          </div>

          {/* Computed flow */}
          {fields && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="rounded-lg border border-gray-200 p-3">
                <p className="text-xs font-semibold text-gray-700 mb-2">Identificación ({flow!.identified} registros)</p>
                <ul className="text-xs text-gray-600 space-y-0.5 mb-3">
                  {flow!.sources.map(s => (
                    <li key={s.name} className="flex justify-between">
                      <span>{s.name}{s.type === 'other' && <span className="text-gray-400"> (otros métodos)</span>}</span>
                      <span className="font-mono">n = {s.n}</span>
                    </li>
                  ))}
                  {flow!.sources.length === 0 && <li className="text-gray-400">Sin fuentes registradas.</li>}
                </ul>
                <ul className="text-xs text-gray-600 space-y-0.5">
                  {FLOW_ROWS.map(r => (
                    <li key={r.key} className="flex justify-between">
                      <span>{r.label}</span>
                      <span className="font-mono">{fields[r.key] ?? '—'}</span>
                    </li>
                  ))}
                </ul>
                {fields.prisma_exclusion_reasons && (
                  <p className="text-[11px] text-gray-500 mt-2">
                    Motivos a texto completo: {String(fields.prisma_exclusion_reasons).split(',').join(' · ').replace(/=/g, ': ')}
                  </p>
                )}
                <div className="flex items-end gap-2 mt-3">
                  <div>
                    <label className="label">Eliminados por otras razones antes del cribado</label>
                    <input type="number" min={0} className="input text-xs w-28" value={otherRemovedValue}
                      onChange={e => setOtherRemoved(e.target.value)} />
                  </div>
                  {otherRemoved !== null && (
                    <button type="button" className="btn-secondary text-xs"
                      onClick={() => saveOtherRemoved.mutate(Math.max(0, Number(otherRemoved) || 0))}>
                      Guardar
                    </button>
                  )}
                </div>
                <p className="text-[10px] text-gray-400 mt-1">
                  Único valor manual: registros descartados por herramientas de automatización u otros motivos documentados.
                </p>
              </div>
              <div className={`rounded-lg border p-3 ${flow!.warnings.length ? 'border-amber-200 bg-amber-50' : 'border-green-200 bg-green-50'}`}>
                {flow!.warnings.length ? (
                  <>
                    <p className="text-xs font-semibold text-amber-800 mb-2 flex items-center gap-1">
                      <AlertTriangle size={14} /> Revisar antes de publicar
                    </p>
                    <ul className="text-xs text-amber-900 space-y-1 list-disc pl-4">
                      {flow!.warnings.map((w, i) => <li key={i}>{w}</li>)}
                    </ul>
                  </>
                ) : (
                  <p className="text-xs font-semibold text-green-800 flex items-center gap-1">
                    <CheckCircle2 size={14} /> El flujo cuadra con las búsquedas y las decisiones registradas.
                  </p>
                )}
              </div>
            </div>
          )}

          <div className="flex items-center gap-2 flex-wrap">
            <button type="button" onClick={handleGenerate} disabled={generating} className="btn-primary text-xs">
              <RefreshCw size={14} className={generating ? 'animate-spin' : ''} />
              {generating ? 'Generando...' : 'Calcular y generar diagrama PRISMA 2020'}
            </button>
            {prismaImg && (
              <button type="button" onClick={handleDownload} className="btn-secondary text-xs">
                <Download size={14} /> Descargar PNG
              </button>
            )}
          </div>

          {prismaImg && (
            <div>
              <p className="text-sm font-semibold text-gray-700 mb-2">Diagrama PRISMA 2020</p>
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
