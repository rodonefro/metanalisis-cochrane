import axios from 'axios'

// In production (Cloudflare Pages), VITE_API_BASE_URL is set to the Render.com backend URL.
// In development, requests go through the Vite proxy at /api → localhost:8000.
const _base = import.meta.env.VITE_API_BASE_URL ?? '/api'
export const API_BASE = _base

const api = axios.create({ baseURL: _base })

export interface ReviewSummary {
  id: number
  title: string
  prospero_id: string | null
  status: string
  created_at: string
  updated_at: string
  study_count: number
}

export interface Review extends ReviewSummary {
  population: string | null
  intervention: string | null
  comparison: string | null
  outcomes: string | null
  study_design: string | null
  abstract: string | null
  background_condition: string | null
  background_intervention: string | null
  background_mechanism: string | null
  background_importance: string | null
  background_text: string | null
  objectives: string | null
  inclusion_criteria: string | null
  exclusion_criteria: string | null
  types_of_studies: string | null
  types_of_participants: string | null
  types_of_interventions: string | null
  types_of_outcomes: string | null
  primary_outcomes: string | null
  secondary_outcomes: string | null
  search_strategy: string | null
  study_selection_method: string | null
  data_extraction_method: string | null
  risk_of_bias_method: string | null
  effect_measures: string | null
  heterogeneity_method: string | null
  methods_text: string | null
  description_of_studies: string | null
  risk_of_bias_results: string | null
  intervention_effects: string | null
  results_text: string | null
  discussion: string | null
  authors_conclusions: string | null
  references: string | null
  plot_interpretation: string | null
  citation_style: string
  effect_measure: string
  model_type: string
  // PRISMA 2020
  prisma_db_names: string | null
  prisma_other_sources: number | null
  prisma_duplicates_removed: number | null
  prisma_other_removed: number | null
  prisma_screened: number | null
  prisma_excluded_screening: number | null
  prisma_sought: number | null
  prisma_not_retrieved: number | null
  prisma_assessed: number | null
  prisma_excluded_eligibility: number | null
  prisma_exclusion_reasons: string | null
  prisma_included: number | null
  prisma_reports_included: number | null
  studies: Study[]
}

export interface Study {
  id: number
  review_id: number
  study_label: string | null
  authors: string | null
  year: number | null
  title: string | null
  journal: string | null
  study_design: string | null
  sample_size: number | null
  events_intervention: number | null
  total_intervention: number | null
  events_control: number | null
  total_control: number | null
  mean_intervention: number | null
  sd_intervention: number | null
  n_intervention: number | null
  mean_control: number | null
  sd_control: number | null
  n_control: number | null
  effect_size: number | null
  effect_size_lower: number | null
  effect_size_upper: number | null
  rob_random_sequence: string | null
  rob_allocation_concealment: string | null
  rob_blinding_participants: string | null
  rob_blinding_outcome: string | null
  rob_incomplete_data: string | null
  rob_selective_reporting: string | null
  rob_other: string | null
  rob_overall: string | null
  included: boolean
  exclusion_reason: string | null
  // Bibliographic metadata
  publication_type: string | null
  volume: string | null
  issue: string | null
  doi: string | null
  abstract_text: string | null
  first_page: string | null
  last_page: string | null
  url: string | null
  // Data extraction
  objective_text: string | null
  methods_used: string | null
  study_results: string | null
  findings: string | null
  insights: string | null
  practical_implications: string | null
  research_gap: string | null
  // Clinical meta-analysis fields
  patient_population: string | null
  group_comparison: string | null
  survival_outcomes: string | null
  mortality_factors: string | null
  key_findings: string | null
  reasoning_study_design: string | null
  source_database: string | null
  notes: string | null
}

export interface Analysis {
  id: number
  review_id: number
  name: string | null
  effect_measure: string | null
  model_type: string | null
  created_at: string
  results_json: string | null
  forest_plot_b64: string | null
  funnel_plot_b64: string | null
  rob_plot_b64: string | null
}

// Reviews
export const listReviews = () => api.get<ReviewSummary[]>('/reviews/').then(r => r.data)
export const getReview = (id: number) => api.get<Review>(`/reviews/${id}`).then(r => r.data)
export const createReview = (data: Partial<Review>) => api.post<Review>('/reviews/', data).then(r => r.data)
export const updateReview = (id: number, data: Partial<Review>) =>
  api.put<Review>(`/reviews/${id}`, data).then(r => r.data)
export const deleteReview = (id: number) => api.delete(`/reviews/${id}`)

// Studies
export const listStudies = (reviewId: number) =>
  api.get<Study[]>(`/reviews/${reviewId}/studies/`).then(r => r.data)
export const createStudy = (reviewId: number, data: Partial<Study>) =>
  api.post<Study>(`/reviews/${reviewId}/studies/`, data).then(r => r.data)
export const updateStudy = (reviewId: number, studyId: number, data: Partial<Study>) =>
  api.put<Study>(`/reviews/${reviewId}/studies/${studyId}`, data).then(r => r.data)
export const deleteStudy = (reviewId: number, studyId: number) =>
  api.delete(`/reviews/${reviewId}/studies/${studyId}`)
export const uploadStudies = (reviewId: number, file: File) => {
  const form = new FormData()
  form.append('file', file)
  return api.post(`/reviews/${reviewId}/studies/upload`, form).then(r => r.data)
}

export const mergeStudyDatabases = (reviewId: number, files: File[]) => {
  const form = new FormData()
  files.forEach(f => form.append('files', f))
  return api.post<{
    files_processed: number
    added: number
    merged: number
    skipped_exact_duplicates: number
    errors?: string[]
  }>(`/reviews/${reviewId}/studies/upload-merge`, form).then(r => r.data)
}

// Analysis
export const runAnalysis = (reviewId: number) =>
  api.post<Analysis>(`/reviews/${reviewId}/analysis/run`).then(r => r.data)
export const getLatestAnalysis = (reviewId: number) =>
  api.get<Analysis>(`/reviews/${reviewId}/analysis/latest`).then(r => r.data)

// AI generation
export const generateSection = (reviewId: number, section: string, includeMetaResults = true) =>
  api.post<{ section: string; text: string }>(
    `/reviews/${reviewId}/generate/${section}`,
    { include_meta_results: includeMetaResults }
  ).then(r => r.data)

// Individual plots
export const getForestPlot = (reviewId: number) =>
  api.get<{ forest_b64: string }>(`/reviews/${reviewId}/analysis/forest`).then(r => r.data)
export const getFunnelPlot = (reviewId: number) =>
  api.get<{ funnel_b64: string }>(`/reviews/${reviewId}/analysis/funnel`).then(r => r.data)
export const getGradeTable = (reviewId: number) =>
  api.get<{ grade_b64: string }>(`/reviews/${reviewId}/analysis/grade`).then(r => r.data)

// PRISMA 2020
export const getPrismaDiagram = (reviewId: number) =>
  api.get<{ prisma_b64: string }>(`/reviews/${reviewId}/analysis/prisma`).then(r => r.data)
export const autofillPrisma = (reviewId: number) =>
  api.post<{ message: string; data: Record<string, unknown> }>(`/reviews/${reviewId}/analysis/prisma/autofill`).then(r => r.data)
export const aiScreenStudies = (reviewId: number) =>
  api.post<{ message: string; included: number; excluded: number }>(`/reviews/${reviewId}/analysis/ai-screen`).then(r => r.data)
export const aiExtractData = (reviewId: number) =>
  api.post<{ message: string; updated: number; total_included: number }>(`/reviews/${reviewId}/analysis/ai-extract`).then(r => r.data)

// Export
export const exportPdf = (reviewId: number) =>
  api.get(`/reviews/${reviewId}/export/pdf`, { responseType: 'blob' }).then(r => r.data)

export default api
