import { computed, ref } from 'vue'
import { api, type LicenseInfo, type Session } from './api'

export const sessions = ref<Session[]>([])
export const activeId = ref('')

// 当前档位放这里，各页面直接读，省得每页都去请求一次
export const me = ref<LicenseInfo | null>(null)

export const activeSession = computed(() => sessions.value.find((s) => s.id === activeId.value))
export const isGuest = computed(() => me.value?.tier === 'guest')
export const isFree = computed(() => me.value?.tier === 'free')

export async function loadLicense() {
  try {
    me.value = await api.license()
  } catch {
    me.value = null // 后端没起来也不影响看界面
  }
  return me.value
}

export async function loadSessions() {
  if (isGuest.value) {
    // 游客会话只在内存里，列表由对话页自己维护
    sessions.value = []
    return
  }
  try {
    sessions.value = await api.sessions()
  } catch {
    sessions.value = [] // 后端刚起或断线时先留空，避免整个面板挂掉
  }
  if (!activeId.value && sessions.value.length) activeId.value = sessions.value[0].id
  if (activeId.value && !sessions.value.some((s) => s.id === activeId.value)) activeId.value = ''
}

export async function createSession() {
  const s = await api.newSession()
  sessions.value = [s, ...sessions.value.filter((x) => x.id !== s.id)]
  activeId.value = s.id
  return s
}

export async function deleteSession(id: string) {
  await api.delSession(id)
  sessions.value = sessions.value.filter((s) => s.id !== id)
  if (activeId.value === id) activeId.value = sessions.value[0]?.id ?? ''
}

export function fmtTime(ts?: number) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  const pad = (n: number) => String(n).padStart(2, '0')
  return sameDay ? `${pad(d.getHours())}:${pad(d.getMinutes())}` : `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
