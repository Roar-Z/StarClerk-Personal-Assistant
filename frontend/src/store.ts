import { computed, ref } from 'vue'
import { api, type Session } from './api'

export const sessions = ref<Session[]>([])
export const activeId = ref('')

export const activeSession = computed(() => sessions.value.find((s) => s.id === activeId.value))

export async function loadSessions() {
  try {
    sessions.value = await api.sessions()
  } catch {
    sessions.value = []  // 后端刚起或断线时先留空，避免整个面板挂掉
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
