import { useMemo, useState } from 'react'
import {
  FileSearch, ChevronDown, ChevronUp, ExternalLink, Copy, Download, CheckCircle2, XCircle, Upload, FileText,
  Trash2, Wand2, Loader2,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  setScreeningDecision, uploadFullText, uploadFullTextMatched, deleteFullText, aiFullTextScreen, type Study,
} from '../services/api'
import { decisionOf } from './ReferenceManager'

interface Props {
  reviewId: number
  studies: Study[]
}

const FULL_TEXT_PREFIX = 'Requiere revisión a texto completo'

/** The criterion the AI could not verify from title/abstract ("Requiere revisión… — <criterio>"). */
function pendingCriterion(s: Study): string {
  const r = s.exclusion_reason || ''
  return r.startsWith(FULL_TEXT_PREFIX) ? r.slice(FULL_TEXT_PREFIX.length).replace(/^\s*[—-]\s*/, '') : r
}

function links(s: Study): { label: string; href: string; hint: string }[] {
  const q = encodeURIComponent(s.title || s.study_label || '')
  const out = []
  if (s.doi) out.push({ label: 'Editorial (DOI)', href: `https://doi.org/${s.doi}`, hint: 'Página del artículo en la revista' })
  if (s.url && !(s.doi && s.url.includes(s.doi))) out.push({ label: 'Enlace del registro', href: s.url, hint: 'URL importada con la referencia' })
  out.push({
    label: 'Europe PMC (acceso abierto)',
    href: `https://europepmc.org/search?query=${s.doi ? encodeURIComponent(`DOI:"${s.doi}"`) : q}`,
    hint: 'Texto completo gratuito cuando existe en PMC',
  })
  out.push({
    label: 'PubMed',
    href: s.pmid ? `https://pubmed.ncbi.nlm.nih.gov/${s.pmid}/` : `https://pubmed.ncbi.nlm.nih.gov/?term=${q}`,
    hint: 'El botón «Full text» de PubMed lleva al PDF del editor o de PMC',
  })
  out.push({ label: 'Google Académico', href: `https://scholar.google.com/scholar?q=${q}`, hint: 'Busca versiones [PDF] en repositorios' })
  return out
}

function csvCell(v: unknown) {
  const t = String(v ?? '')
  return /[",\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t
}

export default function FullTextPanel({ reviewId, studies }: Props) {
  const [open, setOpen] = useState(false)
  const qc = useQueryClient()
  const pending = useMemo(() => studies.filter(s => decisionOf(s) === 'maybe'), [studies])
  const retrieved = pending.filter(s => s.full_text_status === 'retrieved').length
  const notRetrieved = pending.filter(s => s.full_text_status === 'not_retrieved').length

  const decide = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Parameters<typeof setScreeningDecision>[2] }) =>
      setScreeningDecision(reviewId, id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['review', reviewId] }),
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Error al guardar'),
  })

  const refresh = () => qc.invalidateQueries({ queryKey: ['review', reviewId] })
  const [busy, setBusy] = useState<string | null>(null)
  const withPdf = pending.filter(s => s.full_text_filename && s.screening_stage !== 'full_text').length

  const errorText = (e: any) => e.response?.data?.detail || e.message || 'Error'

  const uploadOne = async (s: Study, file: File) => {
    setBusy(`row-${s.id}`)
    try {
      await uploadFullText(reviewId, s.id, file)
      toast.success(`PDF cargado: ${file.name}`)
    } catch (e: any) {
      toast.error(errorText(e))
    } finally {
      setBusy(null)
      refresh()
    }
  }

  const uploadMany = async (files: FileList) => {
    const list = Array.from(files)
    setBusy('bulk')
    const unmatched: string[] = []
    let matched = 0
    for (const [i, f] of list.entries()) {
      toast.loading(`Leyendo PDF ${i + 1} de ${list.length}: ${f.name}`, { id: 'pdf-upload' })
      try {
        const res = await uploadFullTextMatched(reviewId, f)
        if (res.matched) matched++
        else unmatched.push(f.name)
      } catch (e: any) {
        unmatched.push(`${f.name} (${errorText(e)})`)
      }
    }
    setBusy(null)
    refresh()
    toast.success(`${matched} de ${list.length} PDFs asignados a su artículo.`, { id: 'pdf-upload', duration: 8000 })
    if (unmatched.length) {
      toast.error(`Sin asignar (súbelos desde la fila del artículo):\n${unmatched.join('\n')}`, { duration: 15000 })
    }
  }

  const removePdf = async (s: Study) => {
    if (!confirm(`¿Quitar el PDF «${s.full_text_filename}»?`)) return
    try { await deleteFullText(reviewId, s.id) } catch (e: any) { toast.error(errorText(e)) }
    refresh()
  }

  const analyze = async () => {
    setBusy('ai')
    const t = { screened: 0, included: 0, excluded: 0, uncertain: 0 }
    try {
      while (true) {
        const res = await aiFullTextScreen(reviewId)
        t.screened += res.screened; t.included += res.included; t.excluded += res.excluded; t.uncertain += res.uncertain
        refresh()
        toast.loading(`Analizando textos completos: ${t.screened} listos, quedan ${res.remaining}...`, { id: 'ft-ai' })
        if (res.remaining === 0 || res.screened === 0) break
      }
      toast.success(
        `Texto completo analizado: ${t.screened} artículos — ${t.included} incluidos, ${t.excluded} excluidos, ` +
        `${t.uncertain} sin datos suficientes.`, { id: 'ft-ai', duration: 12000 },
      )
    } catch (e: any) {
      toast.error(`${errorText(e)} — lo analizado quedó guardado; vuelve a pulsar para continuar.`, { id: 'ft-ai' })
    } finally {
      setBusy(null)
      refresh()
    }
  }

  const exclude = (s: Study) => {
    const reason = prompt(`Motivo de exclusión a texto completo para «${s.study_label || s.title}»:`, pendingCriterion(s))
    if (reason?.trim()) decide.mutate({ id: s.id, data: { decision: 'exclude', stage: 'full_text', reason: reason.trim() } })
  }

  const copyDois = async () => {
    const dois = pending.map(s => s.doi).filter(Boolean).join('\n')
    if (!dois) { toast('Ninguno de estos artículos tiene DOI.'); return }
    try {
      await navigator.clipboard.writeText(dois)
      toast.success('DOIs copiados. En Zotero: «Añadir elemento por identificador» y pégalos; luego «Buscar PDF disponible».', { duration: 9000 })
    } catch {
      toast.error('No se pudo copiar al portapapeles.')
    }
  }

  const downloadCsv = () => {
    const header = ['Estudio', 'Título', 'Revista', 'Año', 'DOI', 'PMID', 'Criterio por verificar', 'Enlace DOI', 'Estado']
    const rows = pending.map(s => [
      s.study_label || s.authors, s.title, s.journal, s.year, s.doi, s.pmid, pendingCriterion(s),
      s.doi ? `https://doi.org/${s.doi}` : '',
      s.full_text_status === 'retrieved' ? 'Recuperado' : s.full_text_status === 'not_retrieved' ? 'No recuperado' : 'Por buscar',
    ])
    const csv = '﻿' + [header, ...rows].map(r => r.map(csvCell).join(',')).join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'articulos_texto_completo.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="card overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-gray-50"
      >
        <div className="flex items-center gap-2 flex-wrap">
          <FileSearch size={18} className="text-cochrane-500" />
          <span className="font-semibold text-gray-800">Artículos a revisar en texto completo</span>
          <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">{pending.length} por decidir</span>
          {retrieved > 0 && <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">{retrieved} recuperados</span>}
          {notRetrieved > 0 && <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{notRetrieved} no recuperados</span>}
        </div>
        {open ? <ChevronUp size={18} className="text-gray-400" /> : <ChevronDown size={18} className="text-gray-400" />}
      </button>

      {open && (
        <div className="border-t border-gray-100 p-5 space-y-4">
          <p className="text-xs text-gray-600">
            La IA no pudo verificar uno de tus criterios con el título y el resumen. Abre el texto completo, comprueba el
            criterio indicado y decide <strong>Incluir</strong> o <strong>Excluir</strong>. Si no consigues el artículo,
            márcalo como <strong>No recuperado</strong> (PRISMA lo reporta aparte).
          </p>

          {pending.length === 0 ? (
            <p className="text-sm text-gray-500">No hay artículos pendientes de revisión a texto completo.</p>
          ) : (
            <>
              <div className="rounded-lg border border-cochrane-100 bg-cochrane-50/50 p-3 space-y-2">
                <p className="text-xs text-gray-700">
                  <strong>1.</strong> Sube los PDF (puedes seleccionar varios a la vez: cada uno se asigna a su artículo
                  por DOI, PMID o título). Solo se guarda el texto, sin la lista de referencias.{' '}
                  <strong>2.</strong> Pulsa «Analizar con IA»: decide incluir o excluir con el texto completo. Después,
                  la extracción de datos y el riesgo de sesgo del pipeline también usarán el texto completo.
                </p>
                <div className="flex flex-wrap gap-2">
                  <label className={`btn-primary text-xs cursor-pointer ${busy ? 'opacity-50 pointer-events-none' : ''}`}>
                    {busy === 'bulk' ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                    Subir PDFs (varios)
                    <input
                      type="file"
                      accept="application/pdf,.pdf"
                      multiple
                      className="hidden"
                      onChange={e => { if (e.target.files?.length) uploadMany(e.target.files); e.target.value = '' }}
                    />
                  </label>
                  <button type="button" onClick={analyze} disabled={!!busy || withPdf === 0} className="btn-primary text-xs">
                    {busy === 'ai' ? <Loader2 size={14} className="animate-spin" /> : <Wand2 size={14} />}
                    Analizar con IA ({withPdf} PDF{withPdf === 1 ? '' : 's'} sin analizar)
                  </button>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={copyDois} className="btn-secondary text-xs">
                  <Copy size={14} /> Copiar DOIs (para Zotero)
                </button>
                <button type="button" onClick={downloadCsv} className="btn-secondary text-xs">
                  <Download size={14} /> Descargar lista con enlaces (CSV)
                </button>
              </div>

              <ol className="space-y-3">
                {pending.map((s, i) => (
                  <li key={s.id} className="border border-gray-200 rounded-lg p-3">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-gray-800">
                          {i + 1}. {s.title || s.study_label || `Registro ${s.id}`}
                        </p>
                        <p className="text-xs text-gray-500">
                          {[s.study_label || s.authors, s.journal, s.year].filter(Boolean).join(' · ')}
                        </p>
                        <p className="text-xs text-amber-700 mt-1">
                          <strong>Criterio por verificar:</strong> {pendingCriterion(s) || 'no indicado'}
                        </p>
                        {s.ai_screening_note && <p className="text-xs text-gray-500 mt-0.5">{s.ai_screening_note}</p>}
                      </div>
                      <select
                        value={s.full_text_status || ''}
                        onChange={e => decide.mutate({ id: s.id, data: { full_text_status: (e.target.value || '') as any } })}
                        className="text-xs border border-gray-200 rounded px-2 py-1"
                      >
                        <option value="">Por buscar</option>
                        <option value="retrieved">Recuperado</option>
                        <option value="not_retrieved">No recuperado</option>
                      </select>
                    </div>

                    <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2">
                      {links(s).map(l => (
                        <a key={l.label} href={l.href} target="_blank" rel="noreferrer" title={l.hint}
                           className="text-xs text-cochrane-600 hover:underline inline-flex items-center gap-1">
                          {l.label} <ExternalLink size={11} />
                        </a>
                      ))}
                    </div>

                    <div className="flex flex-wrap items-center gap-2 mt-2 text-xs">
                      {s.full_text_filename ? (
                        <>
                          <span className="inline-flex items-center gap-1 text-green-700">
                            <FileText size={12} /> {s.full_text_filename}
                            {s.screening_stage === 'full_text' ? ' — analizado por IA' : ' — pendiente de analizar'}
                          </span>
                          <button type="button" onClick={() => removePdf(s)} title="Quitar PDF"
                                  className="text-gray-400 hover:text-red-600"><Trash2 size={12} /></button>
                        </>
                      ) : (
                        <label className={`inline-flex items-center gap-1 px-2 py-1 rounded border border-gray-200 text-gray-600 hover:bg-gray-50 cursor-pointer ${busy ? 'opacity-50 pointer-events-none' : ''}`}>
                          {busy === `row-${s.id}` ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
                          Subir PDF
                          <input
                            type="file"
                            accept="application/pdf,.pdf"
                            className="hidden"
                            onChange={e => { const f = e.target.files?.[0]; if (f) uploadOne(s, f); e.target.value = '' }}
                          />
                        </label>
                      )}
                    </div>

                    <div className="flex gap-2 mt-2">
                      <button
                        type="button"
                        disabled={decide.isPending}
                        onClick={() => decide.mutate({ id: s.id, data: { decision: 'include', stage: 'full_text' } })}
                        className="text-xs px-2 py-1 rounded border border-green-200 text-green-700 hover:bg-green-50 inline-flex items-center gap-1"
                      >
                        <CheckCircle2 size={12} /> Incluir
                      </button>
                      <button
                        type="button"
                        disabled={decide.isPending}
                        onClick={() => exclude(s)}
                        className="text-xs px-2 py-1 rounded border border-red-200 text-red-700 hover:bg-red-50 inline-flex items-center gap-1"
                      >
                        <XCircle size={12} /> Excluir
                      </button>
                    </div>
                  </li>
                ))}
              </ol>
            </>
          )}
        </div>
      )}
    </div>
  )
}
