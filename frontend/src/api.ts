import { ElMessage } from 'element-plus'

const BASE = '/api'

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
export type Tier = 'guest' | 'free' | 'pro'

export interface Quota {
  plan: Tier
  tier: Tier
  is_pro: boolean
  is_guest: boolean
  limit: number
  used: number
  remaining: number
}

/** 三档权限和本地授权状态，界面上的锁都看它 */
export interface LicenseInfo {
  tier: Tier
  label: string
  is_guest: boolean
  is_pro: boolean
  code: string
  activated_at: number
  machine: string
  perf_mode: boolean
  max_concurrency: number
  limits: { tasks: number; docs: number; memories: number }
  llm?: { limit: number; busy: number; waiting: number }
  scheduler?: { interval: number; stagger: number; queue: { workers: number; queued: number; done: number } }
  tiers?: { name: Tier; label: string; desc: string }[]
  feature?: string
}

export interface WorkSpace {
  name: string
  docs: number
  chunks: number
}

export interface TaskLog {
  id: string
  task_id: string
  name: string
  ok: boolean
  level: string
  result: string
  elapsed_ms: number
  created_at: number
}

export interface MindMap {
  id: string
  title: string
  markdown: string
  nodes: number
  model: string
  elapsed_ms: number
}
export interface RunResult {
  result: string
  should_notify: boolean
  level: string
  elapsed_ms: number
}
export interface Memory {
  id: string
  content: string
  kind: string
  created_at?: number
}
export interface DocMeta {
  doc_id: string
  source: string
  chunks: number
  workspace: string
}
export interface UsageSummary {
  days: number
  totals: { calls: number; prompt_tokens: number; completion_tokens: number; total_tokens: number }
  by_scope: { scope: string; calls: number; total_tokens: number }[]
  by_model: { provider: string; model: string; calls: number; total_tokens: number }[]
  daily: { day: string; calls: number; total_tokens: number }[]
}

let lastToast = 0
/** 错误提示集中在这里弹，页面里只管切 loading，免得同一条报错连弹好几次 */
function toast(msg: string) {
  const now = Date.now()
  if (now - lastToast < 600) return
  lastToast = now
  ElMessage({ message: msg, type: 'error', duration: 3200, grouping: true })
}

async function req<T>(path: string, init?: RequestInit, quiet = false): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(180_000),
      ...init,
    })
  } catch (e) {
    const msg = (e as Error).name === 'TimeoutError' ? '请求超时，请检查模型服务' : '连不上本地服务，确认后台已启动'
    if (!quiet) toast(msg)
    throw new Error(msg)
  }
  if (!res.ok) {
    let msg = `请求失败（${res.status}）`
    try {
      msg = (await res.json()).detail || msg
    } catch {
      /* 非 JSON 响应就保留默认提示 */
    }
    if (!quiet) toast(msg)
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

export const api = {
  // 对话
  sessions: () => req<Session[]>('/chat/sessions', undefined, true),
  messages: (sid: string) => req<Msg[]>(`/chat/sessions/${sid}/messages`, undefined, true),
  newSession: (title = '新对话') =>
    req<Session>('/chat/sessions', { method: 'POST', body: JSON.stringify({ title }) }),
  delSession: (sid: string) => req(`/chat/sessions/${sid}`, { method: 'DELETE' }),
  chat: (body: { session_id?: string; message: string; use_rag: boolean; workspace?: string }) =>
    req<{
      answer: string
      session_id: string
      contexts: { source: string; text: string }[]
      should_notify: boolean
      tier: Tier
    }>('/chat', { method: 'POST', body: JSON.stringify(body) }),

  // 托管任务
  tasks: () => req<Task[]>('/tasks'),
  quota: () => req<Quota>('/tasks/quota'),
  addTask: (body: Partial<Task>) => req<Task>('/tasks', { method: 'POST', body: JSON.stringify(body) }),
  toggleTask: (id: string, enabled: boolean) =>
    req<Task>(`/tasks/${id}`, { method: 'PATCH', body: JSON.stringify({ enabled }) }),
  delTask: (id: string) => req(`/tasks/${id}`, { method: 'DELETE' }),
  runTask: (id: string) => req<RunResult>(`/tasks/${id}/run`, { method: 'POST' }),
  taskLogs: (taskId = '', limit = 50) =>
    req<{ items: TaskLog[]; total: number; exportable: boolean }>(
      `/tasks/logs?task_id=${encodeURIComponent(taskId)}&limit=${limit}`,
    ),

  // 记忆
  memories: () => req<Memory[]>('/memory'),
  addMemory: (content: string, group = '') =>
    req<Memory>('/memory', { method: 'POST', body: JSON.stringify({ content, group }) }),
  delMemory: (id: string) => req(`/memory/${id}`, { method: 'DELETE' }),
  memoryGroups: () => req<{ items: { name: string; n: number }[] }>('/memory/groups', undefined, true),

  // 知识库
  stats: () => req<{ chunks: number; memories: number; dim: number }>('/rag/stats', undefined, true),
  documents: (workspace = '') => req<DocMeta[]>(`/rag/documents?workspace=${encodeURIComponent(workspace)}`),
  workspaces: () => req<{ items: WorkSpace[]; default: string }>('/rag/workspaces', undefined, true),
  addText: (text: string, source: string, workspace = '') =>
    req<{ source: string; chunks: number }>('/rag/text', {
      method: 'POST',
      body: JSON.stringify({ text, source, workspace }),
    }),
  upload: (file: File, workspace = '') => {
    const fd = new FormData()
    fd.append('file', file)
    return req<{ source: string; chunks: number; total_chunks: number }>(
      `/rag/upload?workspace=${encodeURIComponent(workspace)}`,
      { method: 'POST', body: fd },
    )
  },
  delDoc: (docId: string) => req(`/rag/documents/${docId}`, { method: 'DELETE' }),

  // 思维导图（Pro）
  mindmaps: () => req<{ id: string; title: string; size: number }[]>('/mindmap'),
  mindmap: (body: { text?: string; doc_id?: string; title?: string }) =>
    req<MindMap>('/mindmap', { method: 'POST', body: JSON.stringify(body) }),

  // 用量
  overview: () => req<any>('/stats/overview'),
  usage: (days = 7) => req<UsageSummary>(`/stats/usage?days=${days}`),

  // 模型配置
  settings: () => req<any>('/config'),
  saveSettings: (body: any) => req<any>('/config', { method: 'PUT', body: JSON.stringify(body) }),
  testLLM: () => req<{ ok: boolean; reply?: string; error?: string }>('/config/test', { method: 'POST' }, true),
  rebuildVector: () => req<{ ok: boolean }>('/config/rebuild-vector', { method: 'POST' }),

  // 本地授权
  license: () => req<LicenseInfo>('/license', undefined, true),
  activate: (code: string) =>
    req<LicenseInfo>('/license/activate', { method: 'POST', body: JSON.stringify({ code }) }),
  resetLicense: () => req<LicenseInfo>('/license', { method: 'DELETE' }),
  setPerf: (on: boolean) =>
    req<LicenseInfo>('/license/perf', { method: 'POST', body: JSON.stringify({ on }) }),
}

/** 带文件头的下载交给浏览器，导出接口都在后端拼好了 Content-Disposition */
export function download(path: string) {
  const a = document.createElement('a')
  a.href = `${BASE}${path}`
  a.download = ''
  document.body.appendChild(a)
  a.click()
  a.remove()
}
