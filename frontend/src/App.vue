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
import { isGuest, loadLicense, loadSessions, me } from './store'
import type { Tier } from './api'

type Tab = 'chat' | 'tasks' | 'memory' | 'kb' | 'model' | 'usage'

const RANK: Record<Tier, number> = { guest: 0, free: 1, pro: 2 }

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
  { key: 'chat', icon: 'chat', label: '对话', min: 'guest' },
  { key: 'tasks', icon: 'tasks', label: '任务', min: 'free' },
  { key: 'memory', icon: 'memory', label: '记忆', min: 'free' },
  { key: 'kb', icon: 'knowledge', label: '资料', min: 'free' },
  { key: 'model', icon: 'settings', label: '模型', min: 'guest' },
  { key: 'usage', icon: 'usage', label: '用量', min: 'free' },
] as const

const myRank = computed(() => RANK[(me.value?.tier || 'guest') as Tier])
const locked = computed(() => {
  const t = tabs.find((x) => x.key === tab.value)
  return !!t && myRank.value < RANK[t.min as Tier]
})
const lockMeta = computed(() => ({
  title: tabs.find((x) => x.key === tab.value)?.label || '',
  need: isGuest.value ? ('free' as const) : ('pro' as const),
  desc: isGuest.value
    ? '游客模式只开放对话和模型配置，激活后会话才会保存到本地，知识库和托管任务也会跟着开放。'
    : '这个功能在 Pro 版里，激活后可以用思维导图、多工作区、记忆分组和日志导出。',
}))

const lockPoints = computed(() =>
  isGuest.value
    ? ['会话本地保存，可搜索导出', '轻量知识库（5 份文档）', '5 个托管巡检任务', '基础长期记忆与用量']
    : ['长文档思维导图', '多知识库工作区', '记忆分组与备份', '巡检日志导出'],
)

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
  bindEvents()
  await loadLicense()
  await loadSessions()
})
</script>

<template>
  <div class="shell">
    <TitleBar />

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
        <SettingsView v-else-if="tab === 'model'" />
        <UsageView v-else-if="tab === 'usage'" />
      </template>
    </main>

    <nav class="tabbar">
      <button
        v-for="t in tabs"
        :key="t.key"
        class="tab"
        :class="{ active: tab === t.key }"
        @click="tab = t.key"
      >
        <AppIcon :name="t.icon" :size="17" />
        <span>{{ t.label }}</span>
        <i v-if="tabLocked(t.key)" class="tab-lock" />
      </button>
    </nav>
  </div>
</template>
