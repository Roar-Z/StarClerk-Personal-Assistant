<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElNotification } from 'element-plus'
import AppIcon from './components/AppIcon.vue'
import ChatView from './views/ChatView.vue'
import KnowledgeView from './views/KnowledgeView.vue'
import TasksView from './views/TasksView.vue'
import SettingsView from './views/SettingsView.vue'
import { activeId, createSession, deleteSession, fmtTime, loadSessions, sessions } from './store'

type Tab = 'chat' | 'kb' | 'tasks' | 'cfg'
const tab = ref<Tab>('chat')
const nav = [
  { key: 'kb', icon: 'knowledge', label: '知识库' },
  { key: 'tasks', icon: 'tasks', label: '巡检' },
  { key: 'cfg', icon: 'settings', label: '设置' },
] as const

async function onNewChat() {
  await createSession()
  tab.value = 'chat'
  window.dispatchEvent(new Event('sc:focus'))
}

function openSession(id: string) {
  activeId.value = id
  tab.value = 'chat'
  window.dispatchEvent(new Event('sc:focus'))
}

async function onDelete(id: string) {
  await deleteSession(id)
  if (!activeId.value) tab.value = 'chat'
}

function focusChat() {
  tab.value = 'chat'
  window.dispatchEvent(new Event('sc:focus'))
}

function listenEvents() {
  const es = new EventSource('/api/events')
  es.onmessage = (e) => {
    const ev = JSON.parse(e.data)
    if (ev.type === 'notify') {
      ElNotification({
        title: ev.title,
        message: ev.body,
        type: ev.level === 'warn' ? 'warning' : 'success',
        duration: 8000,
        position: 'bottom-right',
      })
    }
  }
  es.onerror = () => setTimeout(listenEvents, 5000)
}

onMounted(async () => {
  ;(window as any).__starclerkFocus = focusChat
  listenEvents()
  await loadSessions()
})
</script>

<template>
  <div class="app">
    <aside class="sidebar">
      <div class="brand">
        <span class="mark">S</span>
        <span class="brand-name">StarClerk</span>
        <span class="brand-tag">本地版</span>
      </div>

      <button class="new-chat" @click="onNewChat">
        <AppIcon name="plus" :size="15" />
        <span>新对话</span>
      </button>

      <div class="sess-sec">
        <div class="sess-label">最近对话</div>
        <div class="sess-list sc-scroll">
          <div
            v-for="s in sessions"
            :key="s.id"
            class="sess"
            :class="{ active: tab === 'chat' && s.id === activeId }"
            @click="openSession(s.id)"
          >
            <span class="sess-title">{{ s.title }}</span>
            <span class="sess-time">{{ fmtTime(s.updated_at) }}</span>
            <button class="sess-del" title="删除会话" @click.stop="onDelete(s.id)">
              <AppIcon name="trash" :size="12" />
            </button>
          </div>
          <div v-if="!sessions.length" class="sess-empty">还没有对话</div>
        </div>
      </div>

      <nav class="foot-nav">
        <button
          v-for="n in nav"
          :key="n.key"
          class="foot-btn"
          :class="{ active: tab === n.key }"
          @click="tab = n.key"
        >
          <AppIcon :name="n.icon" :size="15" />
          <span>{{ n.label }}</span>
        </button>
      </nav>

      <div class="status"><i />本地服务运行中</div>
    </aside>

    <main class="main">
      <ChatView v-show="tab === 'chat'" />
      <KnowledgeView v-if="tab === 'kb'" />
      <TasksView v-if="tab === 'tasks'" />
      <SettingsView v-if="tab === 'cfg'" />
    </main>
  </div>
</template>

<style scoped>
.app {
  height: 100%;
  display: flex;
  background: var(--sc-bg);
}
.sidebar {
  width: 248px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--sc-sidebar);
  border-right: 1px solid var(--sc-line);
  padding: 14px 12px 10px;
}
.brand {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 4px 14px;
}
.mark {
  width: 24px;
  height: 24px;
  border-radius: 7px;
  background: var(--sc-text);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  display: grid;
  place-items: center;
}
.brand-name {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.brand-tag {
  margin-left: auto;
  font-size: 10px;
  color: var(--sc-muted);
  border: 1px solid var(--sc-line);
  border-radius: 5px;
  padding: 0 5px;
  line-height: 16px;
  background: var(--sc-surface);
}
.new-chat {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  width: 100%;
  height: 34px;
  border-radius: 9px;
  border: 1px solid var(--sc-line-strong);
  background: var(--sc-surface);
  color: var(--sc-text);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  box-shadow: var(--sc-shadow-xs);
  transition: border-color 0.14s ease, box-shadow 0.14s ease;
}
.new-chat:hover {
  border-color: #c9d0dc;
  box-shadow: var(--sc-shadow-sm);
}

.sess-sec {
  margin-top: 18px;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.sess-label {
  font-size: 11px;
  color: var(--sc-muted);
  padding: 0 6px 6px;
  letter-spacing: 0.02em;
}
.sess-list {
  flex: 1;
  min-height: 0;
  margin-right: -6px;
  padding-right: 6px;
}
.sess {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  height: 32px;
  padding: 0 8px;
  border-radius: 8px;
  cursor: pointer;
  color: var(--sc-text-2);
  transition: background 0.12s ease, color 0.12s ease;
}
.sess:hover {
  background: rgba(21, 27, 38, 0.04);
  color: var(--sc-text);
}
.sess.active {
  background: var(--sc-surface);
  color: var(--sc-text);
  font-weight: 500;
  box-shadow: var(--sc-shadow-xs), inset 0 0 0 1px var(--sc-line-strong);
}
.sess-title {
  flex: 1;
  min-width: 0;
  font-size: 12.5px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.sess-time {
  font-size: 11px;
  color: var(--sc-muted);
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}
.sess-del {
  position: absolute;
  right: 5px;
  top: 50%;
  transform: translateY(-50%);
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 5px;
  background: var(--sc-surface);
  color: #b9c0cc;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.12s ease, color 0.12s ease;
}
.sess:hover .sess-del {
  opacity: 1;
}
.sess-del:hover {
  color: var(--sc-danger);
}
.sess:hover .sess-time {
  visibility: hidden;
}
.sess-empty {
  padding: 8px 6px;
  font-size: 12px;
  color: var(--sc-muted);
}

.foot-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 0;
  border-top: 1px solid var(--sc-line);
  margin-top: 8px;
}
.foot-btn {
  display: flex;
  align-items: center;
  gap: 9px;
  height: 32px;
  padding: 0 8px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--sc-text-2);
  font-size: 12.5px;
  cursor: pointer;
  text-align: left;
  transition: background 0.12s ease, color 0.12s ease;
}
.foot-btn:hover {
  background: rgba(21, 27, 38, 0.04);
  color: var(--sc-text);
}
.foot-btn.active {
  background: var(--sc-surface);
  color: var(--sc-text);
  box-shadow: var(--sc-shadow-xs), inset 0 0 0 1px var(--sc-line);
}
.status {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px 2px;
  font-size: 11px;
  color: var(--sc-muted);
}
.status i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #4c9a72;
}
.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--sc-bg);
}
.main > * {
  flex: 1;
  min-height: 0;
}
</style>
