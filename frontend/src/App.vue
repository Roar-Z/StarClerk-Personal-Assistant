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
  { key: 'tasks', icon: 'tasks', label: '任务', min: 'free', group: '工作台' },
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
const PAGE_TAB: Record<string, Tab> = { settings: 'model', chat: 'chat', knowledge: 'kb', tasks: 'tasks', system: 'sys' }

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

/** 托盘/快捷键唤起时后端会调它，直接跳对话页 */
function bindEvents() {
  const es = new EventSource('/api/events')
  es.onmessage = (e) => {
    const ev = JSON.parse(e.data)
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
  window.addEventListener('hashchange', syncFromHash)
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
  <div class="shell">
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
          <TasksView v-else-if="tab === 'tasks'" />
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
  </div>
</template>
