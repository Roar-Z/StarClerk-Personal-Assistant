<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import AppIcon from '../components/AppIcon.vue'
import { api, type Msg } from '../api'
import { activeId, activeSession, createSession, loadSessions } from '../store'

const list = ref<Msg[]>([])
const input = ref('')
const useRag = ref(true)
const loading = ref(false)
const sources = ref<{ source: string; text: string }[]>([])
const box = ref<HTMLElement>()
const ta = ref<HTMLTextAreaElement>()

const title = computed(() => activeSession.value?.title || '新对话')
const count = computed(() => (list.value.length ? `${list.value.length} 条消息` : '准备就绪'))
const greeting = computed(() => {
  const h = new Date().getHours()
  return h < 6 ? '夜深了' : h < 11 ? '早上好' : h < 14 ? '中午好' : h < 19 ? '下午好' : '晚上好'
})
const SUGGESTIONS = [
  '总结知识库里最近新增的资料',
  '今天有哪些需要我关注的风险',
  '帮我记住：每周五下午做本周复盘',
  '检查支付链路的待办还有哪些没闭环',
]

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
  ta.value.style.height = `${Math.min(ta.value.scrollHeight, 140)}px`
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
  if (!activeId.value) await createSession()
  list.value.push({ id: `t${Date.now()}`, role: 'user', content, created_at: Date.now() / 1000 })
  scroll()
  loading.value = true
  try {
    const r = await api.chat({ session_id: activeId.value, message: content, use_rag: useRag.value })
    activeId.value = r.session_id
    list.value.push({ id: `a${Date.now()}`, role: 'assistant', content: r.answer, created_at: Date.now() / 1000 })
    sources.value = r.contexts
    await loadSessions()
  } catch (e: any) {
    ElMessage.error(e.message || '请求失败')
  } finally {
    loading.value = false
    scroll()
  }
}
function onFocusEvent() {
  ta.value?.focus()
}

watch(activeId, (id) => loadMessages(id), { immediate: true })
onMounted(() => {
  window.addEventListener('sc:focus', onFocusEvent)
  if (!activeId.value) setTimeout(() => ta.value?.focus(), 300)
})
onUnmounted(() => window.removeEventListener('sc:focus', onFocusEvent))
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div class="page-head-left">
        <span class="page-title">{{ title }}</span>
        <span class="page-sub">{{ count }}</span>
      </div>
      <button class="ghost-btn" :class="{ on: useRag }" title="开启后回答引用本地资料" @click="useRag = !useRag">
        <span class="tick" />检索本地资料
      </button>
    </header>

    <div ref="box" class="page-body sc-scroll">
      <div class="chat-inner" :class="{ centered: !list.length }">
        <div v-if="!list.length" class="intro">
          <h2>{{ greeting }}，需要我盯点什么？</h2>
          <p>我可以检索你的本地资料、记得你说过的事，也会在后台定时巡检后主动提醒你。</p>
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
          placeholder="输入问题，Enter 发送，Shift + Enter 换行"
          @input="autoGrow"
          @keydown.enter.exact.prevent="onEnter"
        />
        <div class="composer-bar">
          <span class="composer-hint">{{ activeId ? (useRag ? '回答会引用本地资料' : '仅使用模型自身知识') : '发送后将自动创建会话' }}</span>
          <button class="send" :disabled="!input.trim() || loading" title="发送" @click="send()">
            <AppIcon name="send" :size="15" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped src="../styles/chat.css"></style>
