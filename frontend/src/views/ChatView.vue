<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import { api, download, type Msg } from '../api'
import {
  activeId,
  activeSession,
  createSession,
  deleteSession,
  fmtTime,
  isGuest,
  loadSessions,
  me,
  sessions,
} from '../store'

const list = ref<Msg[]>([])
const input = ref('')
const useRag = ref(true)
const loading = ref(false)
const sources = ref<{ source: string; text: string }[]>([])
const menu = ref(false)
const box = ref<HTMLElement>()
const ta = ref<HTMLTextAreaElement>()

const title = computed(() => activeSession.value?.title || '新对话')
// 游客的免费模型余量，发一条消息后端会带最新的回来
const gq = computed(() => me.value?.guest_quota)
const greeting = computed(() => {
  const h = new Date().getHours()
  return h < 6 ? '夜深了' : h < 11 ? '早上好' : h < 14 ? '中午好' : h < 19 ? '下午好' : '晚上好'
})
const SUGGESTIONS = computed(() =>
  isGuest.value
    ? ['用三句话解释一下 RAG 是什么', '帮我把这段话改简洁一点', '列一个每周复盘的清单']
    : [
        '总结知识库里最近新增的资料',
        '今天有哪些需要我关注的风险',
        '帮我记住：每周五下午做本周复盘',
        '检查支付链路的待办还有哪些没闭环',
      ],
)

async function loadMessages(id: string) {
  if (!id) {
    list.value = []
    return
  }
  try {
    list.value = await api.messages(id)
  } catch {
    list.value = []
  }
  sources.value = []
  scroll()
}
async function scroll() {
  await nextTick()
  if (box.value) box.value.scrollTop = box.value.scrollHeight
}
function autoGrow() {
  if (!ta.value) return
  ta.value.style.height = 'auto'
  ta.value.style.height = `${Math.min(ta.value.scrollHeight, 132)}px`
}
function onEnter(e: KeyboardEvent) {
  if (e.isComposing) return
  send()
}
async function send(text?: string) {
  const content = (text ?? input.value).trim()
  if (!content || loading.value) return
  input.value = ''
  autoGrow()
  // 游客不建会话，第一条消息发出去时后端会顺手建一个内存会话并把 id 带回来
  if (!activeId.value && !isGuest.value) await createSession()
  list.value.push({ id: `t${Date.now()}`, role: 'user', content, created_at: Date.now() / 1000 })
  scroll()
  loading.value = true
  try {
    const r = await api.chat({ session_id: activeId.value, message: content, use_rag: useRag.value })
    activeId.value = r.session_id
    list.value.push({ id: `a${Date.now()}`, role: 'assistant', content: r.answer, created_at: Date.now() / 1000 })
    sources.value = r.contexts
    if (r.quota && me.value) me.value.guest_quota = r.quota
    if (isGuest.value) {
      if (!sessions.value.some((s) => s.id === r.session_id)) {
        sessions.value = [
          { id: r.session_id, title: content.slice(0, 24), created_at: Date.now() / 1000, updated_at: Date.now() / 1000 },
          ...sessions.value,
        ]
      }
    } else {
      await loadSessions()
    }
  } catch {
    // 错误提示由 api 层统一弹，这里只把输入的内容退回去方便重发
    input.value = content
    list.value = list.value.filter((m) => m.role !== 'user' || m.content !== content)
  } finally {
    loading.value = false
    scroll()
  }
}
async function newChat() {
  menu.value = false
  if (isGuest.value) {
    // 游客只在内存里开一段新对话，刷新后自然就没了
    activeId.value = ''
    list.value = []
    sources.value = []
  } else {
    await createSession()
  }
  focusInput()
}
async function switchTo(id: string) {
  activeId.value = id
  menu.value = false
  focusInput()
}
async function remove(id: string) {
  if (isGuest.value) {
    sessions.value = sessions.value.filter((s) => s.id !== id)
    if (activeId.value === id) {
      activeId.value = ''
      list.value = []
    }
  } else {
    await deleteSession(id)
  }
  if (!sessions.value.length) menu.value = false
}

function exportChat() {
  if (activeId.value) download(`/chat/export?sid=${encodeURIComponent(activeId.value)}`)
}
function focusInput() {
  nextTick(() => ta.value?.focus())
}
function onFocusEvent() {
  focusInput()
}

watch(activeId, (id) => loadMessages(id), { immediate: true })
onMounted(() => {
  window.addEventListener('sc:focus', onFocusEvent)
  if (!activeId.value) setTimeout(focusInput, 300)
})
onUnmounted(() => window.removeEventListener('sc:focus', onFocusEvent))
</script>

<template>
  <div class="page">
    <header class="page-head">
      <el-popover v-model:visible="menu" trigger="click" placement="bottom-start" :width="252" :show-arrow="false">
        <template #reference>
          <button class="sess-trigger" title="切换会话">
            <span class="sess-trigger-name">{{ title }}</span>
            <AppIcon name="chevron" :size="12" />
          </button>
        </template>

        <div class="sess-menu">
          <button class="sess-new" @click="newChat">
            <AppIcon name="plus" :size="13" />
            <span>新建对话</span>
          </button>
          <div class="sess-items sc-scroll">
            <div
              v-for="s in sessions"
              :key="s.id"
              class="sess-item"
              :class="{ active: s.id === activeId }"
              @click="switchTo(s.id)"
            >
              <span class="sess-name">{{ s.title }}</span>
              <span class="sess-time">{{ fmtTime(s.updated_at) }}</span>
              <button class="sess-x" title="删除" @click.stop="remove(s.id)">
                <AppIcon name="close" :size="11" />
              </button>
            </div>
            <p v-if="!sessions.length" class="sess-none">还没有对话记录</p>
          </div>
        </div>
      </el-popover>

      <div class="head-ops">
        <button v-if="!isGuest" class="pill" :class="{ on: useRag }" title="回答时检索本地资料" @click="useRag = !useRag">
          本地资料
        </button>
        <button v-if="!isGuest && activeId" class="pill" title="导出当前对话" @click="exportChat">导出</button>
        <button class="icon-btn" title="新建对话" @click="newChat">
          <AppIcon name="plus" :size="15" />
        </button>
      </div>
    </header>

    <div ref="box" class="page-body sc-scroll">
      <div class="chat-inner" :class="{ centered: !list.length }">
        <div v-if="!list.length" class="intro">
          <h2>{{ greeting }}，需要我盯点什么？</h2>
          <p>
            {{
              isGuest
                ? `游客用 Kilo 免费模型，每小时 ${gq?.limit ?? 0} 次；激活后能换自己的模型，额度也是现在的两倍。`
                : '可以检索本地资料、记住你说过的事，也会在后台定时巡检后主动提醒。'
            }}
          </p>
          <div class="suggest">
            <button v-for="q in SUGGESTIONS" :key="q" class="suggest-row" @click="send(q)">
              <span>{{ q }}</span>
              <AppIcon name="send" :size="13" />
            </button>
          </div>
        </div>

        <template v-for="m in list" :key="m.id">
          <div v-if="m.role === 'user'" class="msg-user">{{ m.content }}</div>
          <div v-else class="msg-ai">
            <div class="who"><AppIcon name="spark" :size="12" /><span>StarClerk</span></div>
            <div class="text">{{ m.content }}</div>
          </div>
        </template>

        <div v-if="loading" class="msg-ai">
          <div class="who"><AppIcon name="spark" :size="12" /><span>StarClerk</span></div>
          <div class="thinking"><i /><i /><i /></div>
        </div>

        <div v-if="sources.length" class="citations">
          <span class="cite-label">参考</span>
          <span v-for="(s, i) in sources" :key="i" class="cite" :title="s.text">{{ s.source }}</span>
        </div>
      </div>
    </div>

    <div class="composer-wrap">
      <div class="composer">
        <textarea
          ref="ta"
          v-model="input"
          rows="1"
          placeholder="输入问题，Enter 发送"
          @input="autoGrow"
          @keydown.enter.exact.prevent="onEnter"
        />
        <div class="composer-bar">
          <span class="composer-hint">
            {{
              isGuest
                ? `游客 · 免费模型剩 ${gq?.left ?? 0}/${gq?.limit ?? 0} 次/时 · 对话不保存`
                : useRag
                  ? '回答会引用本地资料'
                  : '仅用模型自身知识'
            }}
          </span>
          <button class="send" :disabled="!input.trim() || loading" title="发送" @click="send()">
            <AppIcon name="send" :size="15" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped src="../styles/chat.css"></style>
