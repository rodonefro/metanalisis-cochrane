import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { ClipboardList, ChevronDown, ChevronUp, RefreshCw, Save, Loader2, AlertTriangle, Copy } from 'lucide-react'
import { getProspero, generateProspero, saveProspero, type ProsperoState } from '../services/api'

export default function ProsperoPanel({ reviewId }: { reviewId: number }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(true)
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const dirty = Object.keys(drafts).length > 0

  const { data } = useQuery({ queryKey: ['prospero', reviewId], queryFn: () => getProspero(reviewId) })

  const generate = useMutation({
    mutationFn: () => generateProspero(reviewId),
    onSuccess: (res: ProsperoState) => {
      qc.setQueryData(['prospero', reviewId], res)
      setDrafts({})
      toast.success('Registro PROSPERO actualizado (en inglés)')
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Error al generar el registro PROSPERO'),
  })

  const save = useMutation({
    mutationFn: () => saveProspero(reviewId, drafts),
    onSuccess: (res: ProsperoState) => {
      qc.setQueryData(['prospero', reviewId], res)
      setDrafts({})
      toast.success('Cambios guardados')
    },
    onError: () => toast.error('Error al guardar los cambios'),
  })

  // Answer automatically whenever a research question exists and the answers are missing or
  // were written for an earlier version of the question. Never overwrite unsaved edits, and
  // don't retry in a loop after a failure (the button retries manually).
  useEffect(() => {
    if (!data || generate.isPending || generate.isError || dirty) return
    if (data.has_question && (!data.generated || data.stale)) generate.mutate()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, generate.isPending])

  const copyAll = async () => {
    if (!data) return
    const text = data.fields
      .map(f => `${f.label}\n${drafts[f.key] ?? data.answers[f.key] ?? ''}`)
      .join('\n\n')
    await navigator.clipboard.writeText(text)
    toast.success('Registro copiado al portapapeles')
  }

  return (
    <div className="card overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-gray-50"
      >
        <div className="flex items-center gap-2">
          <ClipboardList size={18} className="text-cochrane-600" />
          <span className="font-semibold text-gray-800">Registro PROSPERO</span>
          <span className="text-xs text-gray-400">(respuestas en inglés)</span>
          {generate.isPending && (
            <span className="flex items-center gap-1 text-xs text-cochrane-600">
              <Loader2 size={12} className="animate-spin" /> Generando...
            </span>
          )}
          {!generate.isPending && data?.stale && (
            <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">
              La pregunta cambió
            </span>
          )}
        </div>
        {open ? <ChevronUp size={18} className="text-gray-400" /> : <ChevronDown size={18} className="text-gray-400" />}
      </button>

      {open && (
        <div className="border-t border-gray-100 px-5 py-4 space-y-4">
          {!data?.has_question && (
            <p className="text-sm text-gray-500">
              Escribe el título y la pregunta de investigación (PICO o criterios de inclusión) y el
              registro PROSPERO se completará automáticamente en inglés.
            </p>
          )}

          {data?.stale && dirty && (
            <div className="flex items-start gap-2 text-xs text-amber-700 bg-amber-50 rounded-lg p-3">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              La pregunta de investigación cambió, pero tienes ediciones sin guardar: guárdalas o
              pulsa «Regenerar» para actualizar el registro con la nueva pregunta.
            </div>
          )}

          {data?.has_question && (
            <div className="flex items-center gap-2 flex-wrap">
              <button
                type="button"
                className="btn-secondary text-xs"
                disabled={generate.isPending}
                onClick={() => {
                  if (!dirty || confirm('¿Regenerar el registro? Se perderán las ediciones sin guardar.')) generate.mutate()
                }}
              >
                <RefreshCw size={14} className={generate.isPending ? 'animate-spin' : ''} />
                {generate.isPending ? 'Generando...' : 'Regenerar'}
              </button>
              <button
                type="button"
                className="btn-primary text-xs"
                disabled={!dirty || save.isPending}
                onClick={() => save.mutate()}
              >
                <Save size={14} /> Guardar cambios
              </button>
              {data.generated && (
                <button type="button" className="btn-secondary text-xs" onClick={copyAll}>
                  <Copy size={14} /> Copiar todo
                </button>
              )}
            </div>
          )}

          {data?.generated && (
            <div className="space-y-3">
              {data.fields.map(f => {
                const value = drafts[f.key] ?? data.answers[f.key] ?? ''
                return (
                  <div key={f.key}>
                    <label className="label">{f.label}</label>
                    <textarea
                      className="input text-sm"
                      rows={Math.min(10, Math.max(2, Math.ceil(value.length / 95) + value.split('\n').length - 1))}
                      value={value}
                      onChange={e => setDrafts(d => ({ ...d, [f.key]: e.target.value }))}
                    />
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
