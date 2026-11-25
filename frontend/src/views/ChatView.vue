<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import AppIcon from '../components/AppIcon.vue'
import { api, chatStream, download, exportChat, type Msg, type Session } from '../api'
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
const stream = ref(true)
const listening = ref(false)
const talking = ref(false)
const ocrBusy = ref(false)
const imgEl = ref<HTMLInputElement>()
// 会话搜索：输入了就查后端（能搜到消息内容），清空了回本地列表
const sq = ref('')
const found = ref<Session[] | null>(null)

const title = computed(() => activeSession.value?.title || '新对话')
// 未登录的免费模型余量，发一条消息后端会带最新的回来
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
  // 未登录的对话只在当前内存里，别去后端拉，拉回来是空的
  if (isGuest.value) return
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
// 未登录的几段对话都放这里，切来切去还能看到刚才聊的
const guestMsgs = new Map<string, Msg[]>()

/** 回完之后收个尾：未登录把内存会话补进列表，付费用户重新拉一遍 */
async function settle(sid: string, content: string) {
  activeId.value = sid
  if (isGuest.value) {
    guestMsgs.set(sid, [...list.value])
    if (!sessions.value.some((s) => s.id === sid)) {
      sessions.value = [
        {
          id: sid,
          title: content.slice(0, 24),
          created_at: Date.now() / 1000,
          updated_at: Date.now() / 1000,
        },
        ...sessions.value,
      ]
    }
  } else {
    await loadSessions()
  }
}

async function send(text?: string) {
  const content = (text ?? input.value).trim()
  if (!content || loading.value) return
  input.value = ''
  autoGrow()
  // 未登录不建会话，第一条消息发出去时后端会顺手建一个内存会话并把 id 带回来
  if (!activeId.value && !isGuest.value) await createSession()
  list.value.push({ id: `t${Date.now()}`, role: 'user', content, created_at: Date.now() / 1000 })
  scroll()
  loading.value = true
  const aiId = `a${Date.now()}`
  let sid = activeId.value
  try {
    if (stream.value) {
      list.value.push({ id: aiId, role: 'assistant', content: '', created_at: Date.now() / 1000 })
      await chatStream({ session_id: activeId.value, message: content, use_rag: useRag.value }, {
        onMeta: (id) => {
          sid = id
        },
        onDelta: (t) => {
          const m = list.value.find((x) => x.id === aiId)
          if (m) m.content += t
          scroll()
        },
        onDone: async (r) => {
          const m = list.value.find((x) => x.id === aiId)
          if (m) m.content = r.answer
          sources.value = r.contexts
          if (r.quota && me.value) me.value.guest_quota = r.quota
          await settle(sid, content)
        },
      })
    } else {
      const r = await api.chat({ session_id: activeId.value, message: content, use_rag: useRag.value })
      list.value.push({ id: aiId, role: 'assistant', content: r.answer, created_at: Date.now() / 1000 })
      sources.value = r.contexts
      if (r.quota && me.value) me.value.guest_quota = r.quota
      await settle(r.session_id, content)
    }
  } catch {
    // 错误提示由 api 层统一弹，这里只把输入的内容退回去方便重发
    input.value = content
    list.value = list.value.filter((m) => m.id !== aiId && (m.role !== 'user' || m.content !== content))
  } finally {
    loading.value = false
    scroll()
  }
}

/** 语音输入：WebView2 里能用 Web Speech，不能用就直说 */
function mic() {
  const Ctor = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!Ctor) {
    ElMessage.warning('当前内核没有语音识别，打字吧')
    return
  }
  const r = new Ctor()
  r.lang = 'zh-CN'
  r.interimResults = true
  r.continuous = false
  r.onresult = (e: any) => {
    let text = ''
    for (let i = e.resultIndex; i < e.results.length; i++) {
      text += e.results[i][0].transcript
    }
    input.value = (input.value + text).trim()
    autoGrow()
  }
  r.onend = () => (listening.value = false)
  r.onerror = () => {
    listening.value = false
    ElMessage.warning('没听清，或者系统没开麦克风权限')
  }
  listening.value = true
  r.start()
}

/** 把最后一条回答念出来，再点一次停 */
function speak() {
  const last = [...list.value].reverse().find((m) => m.role === 'assistant' && m.content)
  if (!last) return
  if (!('speechSynthesis' in window)) {
    ElMessage.warning('系统不支持语音合成')
    return
  }
  if (talking.value) {
    window.speechSynthesis.cancel()
    talking.value = false
    return
  }
  const u = new SpeechSynthesisUtterance(last.content.slice(0, 2000))
  u.lang = 'zh-CN'
  u.rate = 1.05
  u.onend = () => (talking.value = false)
  talking.value = true
  window.speechSynthesis.speak(u)
}

/** 选张图交给后端认字，认出来直接塞输入框，还能再改 */
function pickImage(e: Event) {
  const el = e.target as HTMLInputElement
  const file = el.files?.[0]
  el.value = ''
  if (!file) return
  const reader = new FileReader()
  reader.onload = async () => {
    ocrBusy.value = true
    try {
      const r = await api.ocr(String(reader.result))
      input.value = (input.value ? input.value + '\n' : '') + r.text
      autoGrow()
      ElMessage.success('图里的字放进输入框了')
    } finally {
      ocrBusy.value = false
    }
  }
  reader.readAsDataURL(file)
}

/** 拿最后一条回答生成导图，结果在资料页 */
async function makeMindMap() {
  const last = [...list.value].reverse().find((m) => m.role === 'assistant' && m.content)
  if (!last) {
    ElMessage.info('先让它答一段再生成')
    return
  }
  try {
    const r = await api.mindmap({ text: last.content, title: title.value })
    ElMessage.success(`导图生成了 ${r.nodes} 个节点，去「资料」页看`)
  } catch {
    // 权限不够或者模型抽风，api 层已经弹过提示了
  }
}

function onUseSkill(e: Event) {
  const body = (e as CustomEvent).detail as string
  input.value = body
  autoGrow()
  focusInput()
}

async function searchSessions() {
  const q = sq.value.trim()
  if (!q) {
    found.value = null
    return
  }
  try {
    found.value = await api.sessionSearch(q)
  } catch {
    found.value = []
  }
}
async function newChat() {
  menu.value = false
  if (isGuest.value) {
    // 未登录只在内存里开一段新对话，刷新后自然就没了
    if (activeId.value && list.value.length) guestMsgs.set(activeId.value, [...list.value])
    activeId.value = ''
    list.value = []
    sources.value = []
  } else {
    await createSession()
  }
  focusInput()
}
async function switchTo(id: string) {
  if (isGuest.value) list.value = guestMsgs.get(id) ?? []
  activeId.value = id
  menu.value = false
  focusInput()
}
async function remove(id: string) {
  if (isGuest.value) {
    guestMsgs.delete(id)
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

function doExport(fmt: string) {
  if (!activeId.value) return
  exportChat(activeId.value, fmt === 'txt' || fmt === 'docx' ? fmt : 'md')
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
  window.addEventListener('sc:use-skill', onUseSkill)
  if (!activeId.value) setTimeout(focusInput, 300)
})
onUnmounted(() => {
  window.removeEventListener('sc:focus', onFocusEvent)
  window.removeEventListener('sc:use-skill', onUseSkill)
  if (talking.value) window.speechSynthesis.cancel()
})
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
          <!-- 搜的是消息正文，不只是标题；未登录没有历史会话，就别摆这个框 -->
          <label v-if="!isGuest" class="sess-find">
            <AppIcon name="search" :size="12" />
            <input v-model="sq" type="text" placeholder="搜聊天记录" @input="searchSessions" />
            <button v-if="sq" class="sess-clear" title="清空" @click="sq = ''; found = null">
              <AppIcon name="close" :size="10" />
            </button>
          </label>
          <div class="sess-items sc-scroll">
            <div
              v-for="s in found ?? sessions"
              :key="s.id"
              class="sess-item"
              :class="{ active: s.id === activeId }"
              @click="switchTo(s.id); sq = ''; found = null"
            >
              <span class="sess-name">{{ s.title }}</span>
              <span class="sess-time">{{ fmtTime(s.updated_at) }}</span>
              <button v-if="!found" class="sess-x" title="删除" @click.stop="remove(s.id)">
                <AppIcon name="close" :size="11" />
              </button>
            </div>
            <p v-if="found && !found.length" class="sess-none">没搜到相关对话</p>
            <p v-else-if="!found && !sessions.length" class="sess-none">还没有对话记录</p>
          </div>
        </div>
      </el-popover>

      <div class="head-ops">
        <button v-if="!isGuest" class="pill" :class="{ on: useRag }" title="回答时检索本地资料" @click="useRag = !useRag">
          本地资料
        </button>
        <button class="pill" :class="{ on: stream }" title="边生成边显示" @click="stream = !stream">流式</button>
        <button v-if="!isGuest" class="icon-btn" title="把最后一条回答转成思维导图" @click="makeMindMap">
          <AppIcon name="mindmap" :size="14" />
        </button>
        <el-dropdown v-if="!isGuest && activeId" trigger="click" placement="bottom-end" @command="doExport">
          <button class="icon-btn" title="导出这段对话">
            <AppIcon name="download" :size="14" />
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="md">Markdown</el-dropdown-item>
              <el-dropdown-item command="txt">纯文本</el-dropdown-item>
              <el-dropdown-item command="docx">Word 文档</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
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
                ? `未登录用 Kilo 免费模型，每小时 ${gq?.limit ?? 0} 次；登录后能换自己的模型，额度也是现在的两倍。`
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
          <div class="composer-tools">
            <button class="tool-btn" :class="{ on: listening }" title="语音输入" @click="mic">
              <AppIcon name="mic" :size="13" />
            </button>
            <button class="tool-btn" :class="{ on: talking }" title="朗读最后一条回答" @click="speak">
              <AppIcon name="sound" :size="13" />
            </button>
            <button class="tool-btn" :class="{ on: ocrBusy }" title="传图识字" @click="imgEl?.click()">
              <AppIcon name="image" :size="13" />
            </button>
            <input ref="imgEl" type="file" accept="image/*" hidden @change="pickImage" />
            <span class="composer-hint">
              {{
                isGuest
                  ? `未登录 · 免费模型剩 ${gq?.left ?? 0}/${gq?.limit ?? 0} 次/时 · 对话不保存`
                  : useRag
                    ? '回答会引用本地资料'
                    : '仅用模型自身知识'
              }}
            </span>
          </div>
          <button class="send" :disabled="!input.trim() || loading" title="发送" @click="send()">
            <AppIcon name="send" :size="15" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped src="../styles/chat.css"></style>
