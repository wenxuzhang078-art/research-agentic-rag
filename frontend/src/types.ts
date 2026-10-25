export type Mode = 'rag' | 'agent'

export interface Source {
  index: number
  chunk_id: string | null
  source: string
  page: number | null
  source_url: string | null
  content: string
  score: number | null
  score_type: string | null
  provider: string | null
}

export interface ChatResponse {
  request_id: string
  mode: Mode
  answer: string
  sources: Source[]
  steps: Record<string, unknown>[]
  attempts: number
  sufficient: boolean | null
  prefilter_stats: Record<string, unknown>
  duration_ms: number
}

export interface DocumentItem {
  filename: string
  size_bytes: number
  modified_at: string
}

export interface ServerStatus {
  service: string
  mcp_status: string
  mcp_tools: string[]
  max_pdf_mb: number
  session_memory: boolean
}

export interface ChatTurn {
  id: string
  question: string
  mode: Mode
  response?: ChatResponse
  error?: string
  createdAt: Date
}
