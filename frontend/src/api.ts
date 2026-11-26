import { ElMessage } from 'element-plus'

const BASE = '/api'

export interface FocusSession {
  active: boolean
  mode: string
  minutes: number
  started_at: number
  end_at: number
  paused_at: number
  paused_total: number
  ended_at?: number
  last_complete?: boolean
}
export interface FocusStats {
  today_minutes: number
  today_count: number
  total_minutes: number
  total_count: number
  streak: number
  daily: { date: string; minutes: number; count: number }[]
  defaults: { focus: number; short: number; long: number; long_every: number }
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
  url?: string
  cron_minutes: number
  enabled: number
  last_result?: string
  last_run_at?: number
  next_run_at?: number
}
export interface Todo {
  id: string
  title: string
  note: string
  due_at: number | null
  end_at: number | null
  priority: 'low' | 'normal' | 'high'
  tags: string
  repeat: 'once' | 'daily' | 'weekly' | 'monthly'
  lead_minutes: number
  remind_at: number | null
  reminded: number
  done: number
  done_at: number | null
  created_at: number
  updated_at: number
}

// 内部还是 guest/free 两个值，界面上只说未登录和已登录
export type Tier = 'guest' | 'free'

export interface Quota {
  plan: Tier
  tier: Tier
  is_guest: boolean
  limit: number
  used: number
  remaining: number
}

/** 未登录免费模型的每小时余量，后端按滑动窗口算 */
export interface GuestQuota {
  model: string
  limit: number
  total: number
  used: number
  left: number
  window: number
  reset_in: number
}

/** 本机登录状态，界面上的锁都看它 */
export interface LicenseInfo {
  tier: Tier
  label: string
  is_guest: boolean
  is_logged_in: boolean
  mark: string
  logged_in_at: number
  machine: string
  perf_mode: boolean
  max_concurrency: number
  limits: { tasks: number; docs: number; memories: number; notes: number }
  llm?: { limit: number; busy: number; waiting: number }
  scheduler?: { interval: number; stagger: number; queue: { workers: number; queued: number; done: number } }
  tiers?: { name: Tier; label: string; desc: string }[]
  guest_quota?: GuestQuota
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
  group_name?: string
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

/** 系统页的版本信息，后端 /system/info 直接给 */
export interface SystemInfo {
  name: string
  version: string
  build: string
  built_at: string
  python: string
  system: string
  exe: string
  port: number
  data_dir: string
  log_dir: string
  uptime: number
  tier: Tier
  tier_label: string
  perf_mode: boolean
  max_concurrency: number
  counts: { sessions: number; tasks: number; memories: number; chunks: number; dim: number }
}

export interface LogFile {
  name: string
  size: number
  mtime: number
}

export interface AutoStart {
  supported: boolean
  enabled: boolean
  command: string
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
  // 搜会话是按内容搜的，和左边的列表不是一回事，所以单独开一个
  sessionSearch: (q: string) =>
    req<Session[]>(`/chat/sessions?q=${encodeURIComponent(q)}`, undefined, true),
  messages: (sid: string) => req<Msg[]>(`/chat/sessions/${sid}/messages`, undefined, true),
  ocr: (image: string) => req<{ text: string }>('/chat/ocr', { method: 'POST', body: JSON.stringify({ image }) }),
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
      quota?: GuestQuota // 未登录才有，答完顺手带回来
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
  memories: (group = '') => req<Memory[]>(`/memory?group=${encodeURIComponent(group)}`),
  addMemory: (content: string, group = '') =>
    req<Memory>('/memory', { method: 'POST', body: JSON.stringify({ content, group }) }),
  delMemory: (id: string) => req(`/memory/${id}`, { method: 'DELETE' }),
  memoryGroups: () =>
    req<{ items: { name: string; n: number }[]; ungrouped: number }>('/memory/groups', undefined, true),
  moveMemory: (id: string, group: string) =>
    req(`/memory/${id}/group`, { method: 'PATCH', body: JSON.stringify({ group }) }),
  importMemories: (items: { content: string; kind: string; group: string }[]) =>
    req<{ ok: boolean; added: number; skipped: number }>('/memory/backup', {
      method: 'POST',
      body: JSON.stringify(items),
    }),

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
    return req<{ source: string; chunks: number; total_chunks: number; pages?: number; ocr_pages?: number }>(
      `/rag/upload?workspace=${encodeURIComponent(workspace)}`,
      { method: 'POST', body: fd },
    )
  },
  delDoc: (docId: string) => req(`/rag/documents/${docId}`, { method: 'DELETE' }),
  // 批量摘要 / 翻译 / 抽表格，一次最多 10 份，后端串着跑
  batchAi: (body: { doc_ids: string[]; action: 'summary' | 'translate' | 'table'; lang?: string }) =>
    req<{
      action: string
      items: { doc_id: string; source: string; ok: boolean; text: string }[]
      csv: string
      ok_count: number
    }>('/rag/batch-ai', { method: 'POST', body: JSON.stringify(body) }),

  // 思维导图
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
  login: () => req<LicenseInfo>('/license/login', { method: 'POST' }),
  logout: () => req<LicenseInfo>('/license/logout', { method: 'POST' }),
  setPerf: (on: boolean) =>
    req<LicenseInfo>('/license/perf', { method: 'POST', body: JSON.stringify({ on }) }),

  // 系统 / 维护
  systemInfo: () => req<SystemInfo>('/system/info', undefined, true),
  systemLogs: () =>
    req<{ dir: string; items: LogFile[]; total: number }>('/system/logs', undefined, true),
  autostart: () => req<AutoStart>('/system/autostart', undefined, true),
  setAutostart: (on: boolean) =>
    req<AutoStart>('/system/autostart', { method: 'PUT', body: JSON.stringify({ on }) }),
  reveal: (target: 'logs' | 'data') =>
    req<{ ok: boolean; path: string }>('/system/reveal', {
      method: 'POST',
      body: JSON.stringify({ target }),
    }),
  clean: (what: 'sessions' | 'vector' | 'config') =>
    req<{ ok: boolean; done: string[]; need_restart: boolean }>('/system/clean', {
      method: 'POST',
      body: JSON.stringify({ what }),
    }),
  pruneLogs: () => req<{ ok: boolean; removed: number }>('/system/logs', { method: 'DELETE' }),
  uninstall: () => req<{ ok: boolean; path: string }>('/system/uninstall', { method: 'POST' }),

  // 笔记
  notes: (q = '', category = '') =>
    req<{ items: Note[]; total: number; categories: { category: string; n: number }[] }>(
      `/notes?q=${encodeURIComponent(q)}&category=${encodeURIComponent(category)}`,
    ),
  noteSearch: (q: string) =>
    req<{ q: string; notes: Note[]; docs: DocMeta[] }>(`/notes/search?q=${encodeURIComponent(q)}`),
  addNote: (body: Partial<Note>) => req<Note>('/notes', { method: 'POST', body: JSON.stringify(body) }),
  saveNote: (id: string, body: Partial<Note>) =>
    req<Note>(`/notes/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  delNote: (id: string) => req(`/notes/${id}`, { method: 'DELETE' }),

  // 待办与日程
  todos: (done = '0', tag = '', q = '') =>
    req<Todo[]>(
      `/todos?done=${done}&tag=${encodeURIComponent(tag)}&q=${encodeURIComponent(q)}`,
    ),
  parseTodo: (text: string) => req<Partial<Todo>>('/todos/parse', { method: 'POST', body: JSON.stringify({ text }) }),
  addTodo: (body: Partial<Todo>) =>
    req<{ item: Todo; conflicts: Todo[] }>('/todos', { method: 'POST', body: JSON.stringify(body) }),
  saveTodo: (id: string, body: Partial<Todo>) =>
    req<{ item: Todo }>(`/todos/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  finishTodo: (id: string) => req<{ ok: boolean; next: Todo | null }>(`/todos/${id}/done`, { method: 'POST' }),
  ackReminder: (id: string) => req(`/todos/${id}/remind/ack`, { method: 'POST' }),
  dismissReminder: (id: string, stage: number) =>
    req(`/todos/${id}/remind/dismiss?stage=${stage}`, { method: 'POST' }),
  delTodo: (id: string) => req(`/todos/${id}`, { method: 'DELETE' }),
  todoConflicts: (due_at: number, end_at: number, exclude = '') =>
    req<{ items: Todo[] }>(
      `/todos/conflicts?due_at=${due_at}&end_at=${end_at}&exclude=${encodeURIComponent(exclude)}`,
    ),
  exportTodos: (fmt: 'csv' | 'ics') => download(`/todos/export?fmt=${fmt}&done=all`),

  // 学习空间：学习通三时段作业提醒
  studyStatus: () =>
    req<{
      enabled: boolean
      cookie: { logged_in: boolean; at: number }
      last_sync: { at: number; status: string; new: number; reason: string }
      logs: { at: number; status: string; reason: string; new: number; detail: string }[]
      slots: string[]
    }>('/study/status'),
  studyEnable: () => req<{ ok: boolean; enabled: boolean }>('/study/enable', { method: 'POST' }),
  studyDisable: () => req<{ ok: boolean; enabled: boolean }>('/study/disable', { method: 'POST' }),
  studyQrStart: () => req<{ key: string; image: string }>('/study/qr/start', { method: 'POST' }),
  studyQrCheck: (key: string) =>
    req<{ status: string }>(`/study/qr/check?key=${encodeURIComponent(key)}`, { method: 'POST' }),
  studyLogout: () => req<{ ok: boolean }>('/study/logout', { method: 'POST' }),
  studyLogs: (limit = 50) => req<{ items: { at: number; status: string; reason: string; new: number; detail: string }[] }>(`/study/logs?limit=${limit}`),

  // 专注番茄钟
  focusStatus: (days = 7) =>
    req<{ session: FocusSession; stats: FocusStats }>(`/focus/status?days=${days}`),
  focusStart: (minutes: number, mode: string) =>
    req<{ ok: boolean; session: FocusSession }>('/focus/start', { method: 'POST', body: JSON.stringify({ minutes, mode }) }),
  focusPause: () => req<{ ok: boolean; session: FocusSession }>('/focus/pause', { method: 'POST' }),
  focusResume: () => req<{ ok: boolean; session: FocusSession }>('/focus/resume', { method: 'POST' }),
  focusStop: () => req<{ ok: boolean; session: FocusSession }>('/focus/stop', { method: 'POST' }),

  // 本地 OCR + 采购清单
  ocrLocal: (image: string) =>
    req<{ text: string; lines: { text: string; score: number }[]; count: number }>('/ocr/local', {
      method: 'POST',
      body: JSON.stringify({ image }),
    }),
  ocrParse: (body: { image?: string; text?: string; kind: 'express' | 'receipt' }) =>
    req<Record<string, any>>('/ocr/parse', { method: 'POST', body: JSON.stringify(body) }),
  shoppingMerge: (items: { id?: string; text: string }[]) =>
    req<{ groups: { place: string; items: { name: string; qty: number; sources: string[] }[] }[]; text: string; used: number }>(
      '/shopping/merge',
      { method: 'POST', body: JSON.stringify({ items }) },
    ),

  // 技能模板
  skills: (category = '') =>
    req<{ items: Skill[]; categories: string[]; total: number }>(
      `/skills?category=${encodeURIComponent(category)}`,
    ),
  addSkill: (body: { name: string; category: string; body: string }) =>
    req<Skill>('/skills', { method: 'POST', body: JSON.stringify(body) }),
  saveSkill: (id: string, body: Partial<Skill>) =>
    req<Skill>(`/skills/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  delSkill: (id: string) => req(`/skills/${id}`, { method: 'DELETE' }),
  useSkill: (id: string) => req<Skill>(`/skills/${id}/use`, { method: 'POST' }),
  importSkills: (items: { name: string; category: string; body: string }[]) =>
    req<{ ok: boolean; added: number }>('/skills/import', {
      method: 'POST',
      body: JSON.stringify({ items }),
    }),

  // 记忆
  memoryProfile: () =>
    req<{
      kinds: { kind: string; n: number }[]
      groups: { name: string; n: number }[]
      recent: { content: string; kind: string; group_name: string; updated_at: number }[]
      total: number
    }>('/memory/profile'),
  organizeMemory: () =>
    req<{ ok: boolean; moved: number; groups: { name: string; n: number }[] }>('/memory/organize', {
      method: 'POST',
    }),
  summarizeMemory: () => req<{ ok: boolean; text: string }>('/memory/summarize', { method: 'POST' }),

  // 用量明细
  usageDetail: (days = 30) =>
    req<{
      days: number
      by_session: { sid: string; title: string; calls: number; total_tokens: number }[]
      by_task: { tid: string; name: string; calls: number; total_tokens: number }[]
      alert: { days: number; used: number; limit: number; over: boolean }
    }>(`/stats/usage/detail?days=${days}`),

  // 数据迁移
  migrateInfo: () => req<MigrateInfo>('/migrate/info'),
  importPack: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return req<{ ok: boolean; restart: boolean; msg: string }>('/migrate/import', {
      method: 'POST',
      body: fd,
    })
  },

  // 帮助 / 引导 / 更新
  help: () => req<{ title: string; version: string; markdown: string }>('/system/help', undefined, true),
  guide: () =>
    req<{ items: { key: string; title: string; body: string; page: string }[]; done: boolean }>(
      '/system/guide',
      undefined,
      true,
    ),
  guideDone: () => req('/system/guide/done', { method: 'POST' }),
  checkUpdate: () =>
    req<{ current: string; latest: string; has_new: boolean; file: string; folder: string; checked_at: string }>(
      '/system/update',
      undefined,
      true,
    ),
}

export interface Note {
  id: string
  title: string
  body: string
  category: string
  tags: string
  pinned: number
  created_at: number
  updated_at: number
}

export interface Skill {
  id: string
  name: string
  category: string
  body: string
  builtin: number
  use_count: number
  updated_at: number
}

export interface MigrateInfo {
  data_dir: string
  db: string
  size: number
  counts: { sessions: number; notes: number; skills: number; memories: number; tasks: number }
  tier: Tier
  backups: string[]
}

export interface StreamHandlers {
  onMeta?: (sessionId: string) => void
  onDelta: (text: string) => void
  onDone: (r: {
    answer: string
    contexts: { source: string; text: string }[]
    quota?: GuestQuota
  }) => void
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

/**
 * 流式对话。自己读 SSE，一行行往下切；async 生成器在这不好用，就手写个循环。
 * 断开连接靠 AbortController，切会话或者关页面时调一下就行。
 */
export async function chatStream(
  body: { session_id?: string; message: string; use_rag: boolean; workspace?: string },
  h: StreamHandlers,
  ctrl?: AbortController,
): Promise<void> {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: ctrl?.signal,
  })
  if (!res.ok || !res.body) {
    let msg = `请求失败（${res.status}）`
    try {
      msg = (await res.json()).detail || msg
    } catch {
      /* 不是 JSON 就用默认那句 */
    }
    toast(msg)
    throw new Error(msg)
  }
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    const size = buf.split('\n\n')
    buf = size.pop() || ''
    for (const part of size) {
      const line = part.trim()
      if (!line.startsWith('data:')) continue
      let evt: any
      try {
        evt = JSON.parse(line.slice(5))
      } catch {
        continue
      }
      if (evt.type === 'meta') h.onMeta?.(evt.session_id)
      else if (evt.type === 'delta') h.onDelta(evt.text)
      else if (evt.type === 'done') h.onDone(evt)
      else if (evt.type === 'error') {
        toast(evt.message || '模型出错了')
        throw new Error(evt.message || '模型出错了')
      }
    }
  }
}

export function exportChat(sid: string, fmt: 'md' | 'txt' | 'docx') {
  download(`/chat/export?sid=${encodeURIComponent(sid)}&fmt=${fmt}`)
}
