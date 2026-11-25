<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ElNotification } from 'element-plus'
import AppIcon from './components/AppIcon.vue'
import TitleBar from './components/TitleBar.vue'
import ChatView from './views/ChatView.vue'
import TasksView from './views/TasksView.vue'
import MemoryView from './views/MemoryView.vue'
import KnowledgeView from './views/KnowledgeView.vue'
import SettingsView from './views/SettingsView.vue'
import UsageView from './views/UsageView.vue'
import { loadSessions } from './store'

type Tab = 'chat' | 'tasks' | 'memory' | 'kb' | 'model' | 'usage'

// 用 hash 记住当前页，刷新或者从托盘唤起时不至于跳回对话
const fromHash = (location.hash.replace('#', '') || 'chat') as Tab
const tab = ref<Tab>(fromHash)
watch(tab, (v) => (location.hash = v))

function syncFromHash() {
  const h = location.hash.replace('#', '') as Tab
  if (tabs.some((t) => t.key === h) && h !== tab.value) tab.value = h
}
const tabs = [
  { key: 'chat', icon: 'chat', label: '对话' },
  { key: 'tasks', icon: 'tasks', label: '任务' },
  { key: 'memory', icon: 'memory', label: '记忆' },
  { key: 'kb', icon: 'knowledge', label: '资料' },
  { key: 'model', icon: 'settings', label: '模型' },
  { key: 'usage', icon: 'usage', label: '用量' },
] as const

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
  await loadSessions()
})
</script>

<template>
  <div class="shell">
    <TitleBar />

    <main class="shell-body">
      <ChatView v-show="tab === 'chat'" />
      <TasksView v-if="tab === 'tasks'" />
      <MemoryView v-if="tab === 'memory'" />
      <KnowledgeView v-if="tab === 'kb'" />
      <SettingsView v-if="tab === 'model'" />
      <UsageView v-if="tab === 'usage'" />
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
      </button>
    </nav>
  </div>
</template>
