<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppIcon from '../components/AppIcon.vue'
import { api, download, type Memory } from '../api'
import { isPro } from '../store'

const list = ref<Memory[]>([])
const text = ref('')
const busy = ref(false)
const group = ref('')
const groups = ref<{ name: string; n: number }[]>([])
const profile = ref<{ kinds: { kind: string; n: number }[]; recent: { content: string; kind: string }[] } | null>(null)
const summary = ref('')
const working = ref('')

const shown = computed(() => (group.value ? list.value.filter((m) => (m.group_name || '') === group.value) : list.value))

// kind 是后端入库时打的粗标签，界面上翻成人话
const KIND: Record<string, string> = { fact: '事实', preference: '偏好', todo: '待办', summary: '总结' }
function kindText(k?: string) {
  return KIND[k || 'fact'] || '其他'
}

async function load() {
  try {
    list.value = await api.memories()
    if (isPro.value) {
      const g = await api.memoryGroups()
      groups.value = g.items.filter((x) => x.name && x.name !== '未分组')
    }
  } catch {
    list.value = []
  }
}

async function loadProfile() {
  if (!isPro.value) return
  try {
    profile.value = await api.memoryProfile()
  } catch {
    profile.value = null
  }
}

async function add() {
  const content = text.value.trim()
  if (!content || busy.value) return
  busy.value = true
  try {
    await api.addMemory(content, group.value)
    text.value = ''
    await load()
    await loadProfile()
  } catch {
    /* 提示已由 api 层弹出，输入保留方便再试 */
  } finally {
    busy.value = false
  }
}

async function remove(id: string) {
  try {
    await api.delMemory(id)
    list.value = list.value.filter((m) => m.id !== id)
    await loadProfile()
  } catch {
    /* 同上 */
  }
}

/** 自动归类：后端按 kind 分堆再让模型起名，慢几秒，按钮转着就行 */
async function organize() {
  working.value = 'organize'
  try {
    const r = await api.organizeMemory()
    ElMessage.success(r.moved ? `归了 ${r.moved} 条，分成 ${r.groups.length} 组` : '没有需要归组的记忆')
    await load()
    await loadProfile()
  } finally {
    working.value = ''
  }
}

async function summarize() {
  working.value = 'summary'
  try {
    const r = await api.summarizeMemory()
    summary.value = r.text
    await load()
  } finally {
    working.value = ''
  }
}

async function backup() {
  download('/memory/backup')
}

async function restore(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    const data = JSON.parse(await file.text())
    const items = Array.isArray(data) ? data : data.items
    if (!Array.isArray(items) || !items.length) throw new Error('文件里没有记忆')
    await ElMessageBox.confirm(`要导入 ${items.length} 条，内容重复的会自动跳过？`, '导入记忆', {
      type: 'warning',
    })
    const r = await api.importMemories(items)
    ElMessage.success(`导入 ${r.added} 条，跳过 ${r.skipped} 条`)
    await load()
  } catch (err) {
    ElMessage.error('导入失败：' + (err as Error).message)
  }
}

function when(ts?: number) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return `${d.getMonth() + 1}月${d.getDate()}日`
}

onMounted(async () => {
  await load()
  await loadProfile()
})
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div class="page-head-left">
        <span class="page-title">记忆</span>
        <span class="page-sub">{{ list.length }} 条 · 检索时按相关度取前几条</span>
      </div>
      <div class="head-ops">
        <template v-if="isPro">
          <button class="btn ghost" :disabled="!!working" @click="organize">
            {{ working === 'organize' ? '归类中…' : '自动归类' }}
          </button>
          <button class="btn ghost" :disabled="!!working" @click="summarize">
            {{ working === 'summary' ? '总结中…' : '总结一下' }}
          </button>
          <button class="btn ghost" @click="backup">备份</button>
          <label class="btn ghost">
            导入
            <input type="file" accept="application/json,.json" hidden @change="restore" />
          </label>
        </template>
      </div>
    </header>

    <div class="page-body sc-scroll">
      <div class="page-inner stack">
        <div v-if="isPro && profile" class="card">
          <div class="card-head">
            <span class="card-title">画像</span>
            <span class="card-hint">按入库时的标签粗略统计</span>
          </div>
          <div class="card-body prof">
            <div v-for="k in profile.kinds" :key="k.kind" class="prof-item">
              <b>{{ k.n }}</b>
              <span>{{ kindText(k.kind) }}</span>
            </div>
            <p v-if="!profile.kinds.length" class="empty">还没有记忆，先加几条</p>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <span class="card-title">让它记住一件事</span>
          </div>
          <div class="card-body" style="padding-top: 4px">
            <el-input
              v-model="text"
              type="textarea"
              :rows="2"
              maxlength="500"
              show-word-limit
              :placeholder="group ? `写进「${group}」分组，比如：我习惯周五下午复盘` : '比如：我习惯周五下午做本周复盘'"
            />
            <div class="mem-actions">
              <span class="muted-line">对话里说“记住…”也会自动写入</span>
              <button class="btn-dark" :disabled="!text.trim() || busy" @click="add">加入记忆</button>
            </div>
          </div>
        </div>

        <div v-if="summary" class="card">
          <div class="card-head">
            <span class="card-title">这段时间的总结</span>
            <button class="link-x" @click="summary = ''">收起</button>
          </div>
          <div class="card-body">
            <p class="sum-text">{{ summary }}</p>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <span class="card-title">已记住的内容</span>
            <span class="card-hint">{{ shown.length }} 条</span>
          </div>
          <div v-if="groups.length" class="chips">
            <button :class="{ on: group === '' }" @click="group = ''">全部</button>
            <button v-for="g in groups" :key="g.name" :class="{ on: group === g.name }" @click="group = g.name">
              {{ g.name }} {{ g.n }}
            </button>
          </div>
          <div class="card-body mem-list">
            <div v-for="m in shown" :key="m.id" class="mem-row">
              <div class="mem-main">
                <p class="mem-text">{{ m.content }}</p>
                <span class="mem-meta">
                  <em class="kind">{{ kindText(m.kind) }}</em>
                  <template v-if="m.group_name">· {{ m.group_name }}</template>
                  · {{ m.created_at ? when(m.created_at) : '较早' }}
                </span>
              </div>
              <button class="mem-del" title="删除" @click="remove(m.id)">
                <AppIcon name="trash" :size="13" />
              </button>
            </div>
            <p v-if="!shown.length" class="empty">这个分组下还没有记忆</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped src="../styles/views.css"></style>
<style scoped>
.prof {
  display: flex;
  gap: 22px;
}
.prof-item {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.prof-item b {
  font-size: 18px;
  font-weight: 600;
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}
.prof-item span {
  font-size: 11px;
  color: var(--sc-muted);
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  padding: 9px 14px 0;
}
.chips button {
  padding: 2px 8px;
  font-size: 11.5px;
  color: var(--sc-text-2);
  background: transparent;
  border: 1px solid var(--sc-line);
  border-radius: 999px;
  cursor: pointer;
}
.chips button.on {
  color: var(--sc-text);
  background: rgba(21, 27, 38, 0.05);
  border-color: var(--sc-line-strong);
}
.kind {
  font-style: normal;
  color: var(--sc-text-2);
}
.sum-text {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.9;
  color: var(--sc-text-2);
  user-select: text;
}
.link-x {
  border: 0;
  background: transparent;
  padding: 0;
  font-size: 11.5px;
  color: var(--sc-muted);
  cursor: pointer;
}
.link-x:hover {
  color: var(--sc-text);
}
</style>
