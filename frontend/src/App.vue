<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElNotification } from 'element-plus'
import AppIcon from './components/AppIcon.vue'
import TitleBar from './components/TitleBar.vue'
import LockCard from './components/LockCard.vue'
import ChatView from './views/ChatView.vue'
import TasksView from './views/TasksView.vue'
import MemoryView from './views/MemoryView.vue'
import KnowledgeView from './views/KnowledgeView.vue'
import SettingsView from './views/SettingsView.vue'
import UsageView from './views/UsageView.vue'
import SystemView from './views/SystemView.vue'
import NotesView from './views/NotesView.vue'
import SkillsView from './views/SkillsView.vue'
import TodoView from './views/TodoView.vue'
import StudyView from './views/StudyView.vue'
import ScanView from './views/ScanView.vue'
import CommandPalette from './components/CommandPalette.vue'
import ReminderToast, { type ReminderItem } from './components/ReminderToast.vue'
import HelpView from './views/HelpView.vue'
import MigrateView from './views/MigrateView.vue'
import { loadLicense, loadSessions, me } from './store'
import { api, type Tier } from './api'

type Tab =
  | 'chat'
  | 'tasks'
  | 'memory'
  | 'kb'
  | 'notes'
  | 'skills'
  | 'todos'
  | 'study'
  | 'scan'
  | 'model'
  | 'usage'
  | 'help'
  | 'migrate'
  | 'sys'

const RANK: Record<Tier, number> = { guest: 0, free: 1 }

// 用 hash 记住当前页，刷新或者从托盘唤起时不至于跳回对话
const fromHash = (location.hash.replace('#', '') || 'chat') as Tab
const tab = ref<Tab>(fromHash)
watch(tab, (v) => (location.hash = v))

function syncFromHash() {
  const h = location.hash.replace('#', '') as Tab
  if (tabs.some((t) => t.key === h) && h !== tab.value) tab.value = h
}

// min 是这个页面对应的最低档位，和后端 access.py 的表保持一致
const tabs = [
  { key: 'chat', icon: 'chat', label: '对话', min: 'guest', group: '工作台' },
  { key: 'todos', icon: 'todo', label: '待办', min: 'free', group: '工作台' },
  { key: 'study', icon: 'book', label: '学习', min: 'free', group: '工作台' },
  { key: 'tasks', icon: 'tasks', label: '任务', min: 'free', group: '工作台' },
  { key: 'scan', icon: 'image', label: '扫描', min: 'guest', group: '工作台' },
  { key: 'memory', icon: 'memory', label: '记忆', min: 'free', group: '工作台' },
  { key: 'kb', icon: 'knowledge', label: '资料', min: 'free', group: '工作台' },
  { key: 'notes', icon: 'note', label: '笔记', min: 'free', group: '工作台' },
  { key: 'skills', icon: 'key', label: '技能', min: 'free', group: '工作台' },
  { key: 'model', icon: 'settings', label: '模型', min: 'guest', group: '设置' },
  { key: 'usage', icon: 'usage', label: '用量', min: 'free', group: '设置' },
  { key: 'help', icon: 'help', label: '帮助', min: 'guest', group: '设置' },
  { key: 'migrate', icon: 'book', label: '迁移', min: 'free', group: '设置' },
  { key: 'sys', icon: 'shield', label: '系统', min: 'guest', group: '设置' },
] as const

// 侧栏分两组，上面干活下面调设置，比一长串平铺清楚
const groups = computed(() =>
  ['工作台', '设置'].map((name) => ({
    name,
    items: tabs.filter((t) => t.group === name),
  })),
)

const myRank = computed(() => RANK[(me.value?.tier || 'guest') as Tier])
const locked = computed(() => {
  const t = tabs.find((x) => x.key === tab.value)
  return !!t && myRank.value < RANK[t.min as Tier]
})
const lockMeta = computed(() => ({
  title: tabs.find((x) => x.key === tab.value)?.label || '',
  need: 'free' as const,
  desc: '未登录只能对话，模型走免费网关、聊完不留记录。登录后所有功能都开着，不用再升级。',
}))

const lockPoints = computed(() => [
  '会话保存到本地，可搜索、可导出',
  '知识库最多 500 份文档，支持多工作区',
  '20 个托管巡检任务，日志可导出',
  '记忆画像、思维导图、笔记模板和数据迁移',
])

function tabNeed(key: string) {
  return tabs.find((x) => x.key === key)?.min || 'guest'
}
function tabLocked(key: string) {
  return myRank.value < RANK[tabNeed(key) as Tier]
}

function focusChat() {
  tab.value = 'chat'
  window.dispatchEvent(new Event('sc:focus'))
}

// 新手引导：第一次进来浮在右下角，点完「知道了」就不再自己弹，帮助页还能重新打开
const guide = ref<{ key: string; title: string; body: string; page: string }[]>([])
const guideOpen = ref(false)
const PAGE_TAB: Record<string, Tab> = {
  settings: 'model',
  chat: 'chat',
  knowledge: 'kb',
  tasks: 'tasks',
  todo: 'todos',
  system: 'sys',
}

async function loadGuide() {
  try {
    const r = await api.guide()
    guide.value = r.items
    guideOpen.value = !r.done
  } catch {
    /* 引导只是锦上添花，读不到就算了 */
  }
}
function goStep(page: string) {
  tab.value = PAGE_TAB[page] || 'chat'
}
async function closeGuide() {
  guideOpen.value = false
  try {
    await api.guideDone()
  } catch {
    /* 标不上也没关系，下次再弹一遍 */
  }
}

// 外观设置：主题写在 html 的 data-theme 上，悬浮窗只改这一层的 class
const floatMode = ref(false)
type ThemeMode = 'light' | 'dark' | 'system'
function applyTheme(mode: ThemeMode) {
  const dark = mode === 'dark' || (mode === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
}

// 快捷键唤起的命令面板，后端只负责弹窗，动作都在前端派发
const paletteOpen = ref(false)
function runCommand(key: string, text?: string) {
  if (key === 'todos') return (tab.value = 'todos')
  if (key === 'scan') return (tab.value = 'scan')
  if (key === 'send') tab.value = 'chat'
  else if (key !== 'todo') tab.value = 'chat'
  const name = key === 'todo' ? 'sc:todo-new' : key === 'send' ? 'sc:send' : `sc:${key}`
  // 等目标页切出来再喊，不然组件还没挂上，白喊一声
  window.setTimeout(() => window.dispatchEvent(new CustomEvent(name, text ? { detail: text } : undefined)), 40)
}

// 右下角待办提醒卡片，和托盘气泡不是一套；确认会停掉后续阶段，关闭只关当前
const reminders = ref<ReminderItem[]>([])
async function ackReminder(item: ReminderItem) {
  reminders.value = reminders.value.filter((x) => x.todo_id !== item.todo_id)
  try {
    await api.ackReminder(item.todo_id)
  } catch {
    /* 后端没连上也先把卡片收了 */
  }
}
async function closeReminder(item: ReminderItem) {
  reminders.value = reminders.value.filter((x) => x.event_id !== item.event_id)
  try {
    await api.dismissReminder(item.todo_id, item.stage)
  } catch {
    /* 同上 */
  }
}

/** 托盘/快捷键唤起时后端会调它，直接跳对话页 */
function bindEvents() {
  const es = new EventSource('/api/events')
  es.onmessage = (e) => {
    const ev = JSON.parse(e.data)
    if (ev.type === 'command') {
      paletteOpen.value = true
      return
    }
    if (ev.type === 'todo_reminder') {
      if (!reminders.value.some((x) => x.event_id === ev.event_id)) reminders.value.push(ev)
      return
    }
    if (ev.type === 'study_session_expired') {
      tab.value = 'study'
      // 等页面挂上再发，不然没人接这个事件
      window.setTimeout(() => window.dispatchEvent(new CustomEvent('sc:study-expired', { detail: ev.reason || '' })), 120)
      return
    }
    if (ev.type !== 'notify') return
    ElNotification({
      title: ev.title,
      message: ev.body,
      type: ev.level === 'warn' ? 'warning' : 'success',
      duration: 8000,
      position: 'bottom-right',
    })
  }
  es.onerror = () => setTimeout(bindEvents, 5000)
}

onMounted(async () => {
  ;(window as any).__starclerkFocus = focusChat
  ;(window as any).__starclerkCommand = () => (paletteOpen.value = true)
  window.addEventListener('hashchange', syncFromHash)
  window.addEventListener('sc:theme', ((e: CustomEvent) => applyTheme(e.detail)) as EventListener)
  window.addEventListener('sc:float', ((e: CustomEvent) => (floatMode.value = !!e.detail)) as EventListener)
  applyTheme((localStorage.getItem('sc-theme') as ThemeMode) || 'light')
  window.addEventListener('sc:guide', () => {
    guideOpen.value = true
  })
  bindEvents()
  await loadLicense()
  await loadSessions()
  await loadGuide()
})
</script>

<template>
  <div class="shell" :class="{ float: floatMode }">
    <TitleBar />

    <div class="shell-main">
      <nav class="sidenav">
        <template v-for="g in groups" :key="g.name">
          <p class="nav-cap">{{ g.name }}</p>
          <button
            v-for="t in g.items"
            :key="t.key"
            class="nav-item"
            :class="{ active: tab === t.key }"
            @click="tab = t.key"
          >
            <AppIcon :name="t.icon" :size="16" />
            <span>{{ t.label }}</span>
            <i v-if="tabLocked(t.key)" class="nav-lock" />
          </button>
        </template>

        <div class="nav-foot">
          <span class="nav-tier" :class="`tier-${me?.tier || 'guest'}`">{{ me?.label || '加载中' }}</span>
          <button class="nav-link" @click="tab = 'model'">授权</button>
        </div>
      </nav>

      <main class="shell-body">
        <ChatView v-show="tab === 'chat'" />
        <template v-if="tab !== 'chat'">
          <LockCard
            v-if="locked"
            :title="lockMeta.title"
            :desc="lockMeta.desc"
            :need="lockMeta.need"
            :points="lockPoints"
            @go="tab = 'model'"
          />
          <TodoView v-else-if="tab === 'todos'" />
          <StudyView v-else-if="tab === 'study'" />
          <TasksView v-else-if="tab === 'tasks'" />
          <ScanView v-else-if="tab === 'scan'" />
          <MemoryView v-else-if="tab === 'memory'" />
          <KnowledgeView v-else-if="tab === 'kb'" />
          <NotesView v-else-if="tab === 'notes'" />
          <SkillsView v-else-if="tab === 'skills'" />
          <SettingsView v-else-if="tab === 'model'" />
          <UsageView v-else-if="tab === 'usage'" />
          <HelpView v-else-if="tab === 'help'" />
          <MigrateView v-else-if="tab === 'migrate'" />
          <SystemView v-else-if="tab === 'sys'" />
        </template>
      </main>
    </div>

    <div v-if="guideOpen && guide.length" class="guide">
      <div class="guide-head">
        <b>第一次用？几步就上手</b>
        <button class="guide-x" title="关掉" @click="closeGuide">
          <AppIcon name="close" :size="11" />
        </button>
      </div>
      <ol class="guide-list">
        <li v-for="(g, i) in guide" :key="g.key" @click="goStep(g.page)">
          <span class="guide-no">{{ i + 1 }}</span>
          <div>
            <b>{{ g.title }}</b>
            <p>{{ g.body }}</p>
          </div>
        </li>
      </ol>
      <button class="btn primary guide-ok" @click="closeGuide">知道了，别再弹</button>
    </div>

    <CommandPalette :open="paletteOpen" @close="paletteOpen = false" @run="runCommand" />
    <ReminderToast :items="reminders" @ack="ackReminder" @close="closeReminder" />
  </div>
</template>
