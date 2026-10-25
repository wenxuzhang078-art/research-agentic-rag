import type { ChatResponse, DocumentItem, Mode, ServerStatus } from './types.ts'

async function jsonRequest<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, options)
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json() as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
      else if (body.detail) detail = JSON.stringify(body.detail)
    } catch { /* 不是 JSON 错误，保持 HTTP 状态码 */ }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export async function chat(question: string, mode: Mode, topK: number): Promise<ChatResponse> {
  return jsonRequest('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, mode, top_k: topK, show_steps: true }),
  })
}

export function getStatus() {
  return jsonRequest<ServerStatus>('/api/status')
}

export async function getDocuments() {
  return jsonRequest<{ documents: DocumentItem[], note: string }>('/api/documents')
}

export async function uploadPdf(file: File) {
  const data = new FormData()
  data.append('file', file)
  return jsonRequest<{ original_filename: string, saved_filename: string, result: { pages: number, chunks: number } }>(
    '/api/documents/upload', { method: 'POST', body: data }
  )
}
