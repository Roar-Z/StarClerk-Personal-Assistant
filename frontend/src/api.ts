const BASE = '/api'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let msg = res.statusText
    try {
      msg = (await res.json()).detail || msg
    } catch {
      /* ignore */
    }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

export interface Msg {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: number
}
export interface Session {
  id: string
  title: string
  updated_at: number
}
export interface Task {
  id: string
  name: string
  prompt: string
  kind: string
  doc_scope?: string
  cron_minutes: number
  enabled: number
  last_result?: string
  last_run_at?: number
  next_run_at?: number
}
export interface Quota {
  plan: 'free' | 'pro'
  is_pro: boolean
  limit: number
  used: number
  remaining: number
}
export interface RunResult {
  result: string
  should_notify: boolean
  level: string
  elapsed_ms: number
}

export const api = {
  // chat
  sessions: () => req<Session[]>('/chat/sessions'),
  messages: (sid: string) => req<Msg[]>(`/chat/sessions/${sid}/messages`),
  newSession: (title = '新对话') =>
    req<Session>('/chat/sessions', { method: 'POST', body: JSON.stringify({ title }) }),
  delSession: (sid: string) => req(`/chat/sessions/${sid}`, { method: 'DELETE' }),
  chat: (body: { session_id?: string; message: string; use_rag: boolean }) =>
    req<{ answer: string; session_id: string; contexts: { source: string; text: string }[]; should_notify: boolean }>(
      '/chat',
      { method: 'POST', body: JSON.stringify(body) },
    ),
  // task
  tasks: () => req<Task[]>('/tasks'),
  quota: () => req<Quota>('/tasks/quota'),
  addTask: (body: Partial<Task>) => req<Task>('/tasks', { method: 'POST', body: JSON.stringify(body) }),
  toggleTask: (id: string, enabled: boolean) =>
    req<Task>(`/tasks/${id}`, { method: 'PATCH', body: JSON.stringify({ enabled }) }),
  delTask: (id: string) => req(`/tasks/${id}`, { method: 'DELETE' }),
  runTask: (id: string) => req<RunResult>(`/tasks/${id}/run`, { method: 'POST' }),
  // memory
  memories: () => req<{ id: string; content: string; kind: string }[]>('/memory'),
  addMemory: (content: string) => req('/memory', { method: 'POST', body: JSON.stringify({ content }) }),
  delMemory: (id: string) => req(`/memory/${id}`, { method: 'DELETE' }),
  // rag
  stats: () => req<{ chunks: number; memories: number; dim: number }>('/rag/stats'),
  documents: () => req<{ doc_id: string; source: string; chunks: number }[]>('/rag/documents'),
  addText: (text: string, source: string) =>
    req('/rag/text', { method: 'POST', body: JSON.stringify({ text, source }) }),
  upload: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return req<{ source: string; chunks: number }>('/rag/upload', { method: 'POST', body: fd })
  },
  // stats
  overview: () => req<any>('/stats/overview'),
  usage: (days = 7) => req<any>(`/stats/usage?days=${days}`),
  // config
  settings: () => req<any>('/config'),
  saveSettings: (body: any) => req<any>('/config', { method: 'PUT', body: JSON.stringify(body) }),
  setPlan: (plan: 'free' | 'pro') =>
    req<Quota>('/config/plan', { method: 'PUT', body: JSON.stringify({ plan }) }),
  testLLM: () => req<{ ok: boolean; reply?: string; error?: string }>('/config/test', { method: 'POST' }),
}
