<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, type Todo } from '../api'

const items = ref<Todo[]>([])
const doneFilter = ref('0')
const q = ref('')
const phrase = ref('')
const editing = ref('')
const conflicts = ref<Todo[]>([])
const busy = ref(false)
const form = ref({
  title: '',
  note: '',
  due_at: '',
  minutes: 30,
  priority: 'normal',
  tags: '',
  repeat: 'once',
  lead_minutes: 0,
})

const REPEAT: Record<string, string> = { once: '不重复', daily: '每天', weekly: '每周', monthly: '每月' }

function pad(n: number) {
  return String(n).padStart(2, '0')
}
function toInput(ts?: number | null) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
function fromInput(v: string) {
  return v ? Math.floor(new Date(v).getTime() / 1000) : null
}
function fmt(ts?: number | null) {
  if (!ts) return '没定时间'
  const d = new Date(ts * 1000)
  const today = new Date()
  const day = `${d.getMonth() + 1}月${d.getDate()}日`
  const time = `${pad(d.getHours())}:${pad(d.getMinutes())}`
  return d.toDateString() === today.toDateString() ? `今天 ${time}` : `${day} ${time}`
}
const sorted = computed(() =>
  [...items.value].sort((a, b) => (a.due_at || 9e15) - (b.due_at || 9e15)),
)

async function load() {
  items.value = await api.todos(doneFilter.value, '', q.value)
}
async function parse() {
  const text = phrase.value.trim()
  if (!text) return
  busy.value = true
  try {
    const d = await api.parseTodo(text)
    form.value = {
      title: d.title || text,
      note: d.note || '',
      due_at: toInput(d.due_at),
      minutes: d.duration_minutes || 30,
      priority: d.priority || 'normal',
      tags: (d.tags || []).join(', '),
      repeat: d.repeat || 'once',
      lead_minutes: d.lead_minutes || 0,
    }
    ElMessage.success('拆好了，确认一下再存')
  } finally {
    busy.value = false
  }
}
function open(t?: Todo) {
  editing.value = t?.id || ''
  form.value = {
    title: t?.title || '',
    note: t?.note || '',
    due_at: toInput(t?.due_at),
    minutes: t?.due_at && t?.end_at ? Math.round((t.end_at - t.due_at) / 60) : 30,
    priority: t?.priority || 'normal',
    tags: t?.tags || '',
    repeat: t?.repeat || 'once',
    lead_minutes: t?.lead_minutes || 0,
  }
  conflicts.value = []
}
async function save() {
  if (!form.value.title.trim()) return ElMessage.warning('写个标题')
  const due = fromInput(form.value.due_at)
  const body = {
    title: form.value.title.trim(),
    note: form.value.note.trim(),
    due_at: due,
    end_at: due ? due + Number(form.value.minutes || 30) * 60 : null,
    priority: form.value.priority,
    tags: form.value.tags.trim(),
    repeat: form.value.repeat,
    lead_minutes: Number(form.value.lead_minutes || 0),
  }
  busy.value = true
  try {
    if (editing.value) {
      await api.saveTodo(editing.value, body)
      if (due && body.end_at) conflicts.value = (await api.todoConflicts(due, body.end_at, editing.value)).items
      ElMessage.success('改好了')
    } else {
      const r = await api.addTodo(body)
      conflicts.value = r.conflicts || []
      ElMessage.success(r.conflicts?.length ? '存好了，不过跟别的事撞时间了' : '加好了')
      open(r.item)
    }
    await load()
  } finally {
    busy.value = false
  }
}
async function finish(t: Todo) {
  const r = await api.finishTodo(t.id)
  ElMessage.success(r.next ? '完成，下一次也排上了' : '完成')
  if (editing.value === t.id) open()
  await load()
}
async function remove(t: Todo) {
  await ElMessageBox.confirm(`删掉「${t.title}」？`, '删待办', { type: 'warning' })
  await api.delTodo(t.id)
  if (editing.value === t.id) open()
  await load()
}
function newOne() {
  open()
  phrase.value = ''
}
function onNewShortcut() {
  newOne()
  window.setTimeout(() => document.getElementById('todo-phrase')?.focus(), 50)
}

onMounted(() => {
  load()
  window.addEventListener('sc:todo-new', onNewShortcut)
})
onUnmounted(() => window.removeEventListener('sc:todo-new', onNewShortcut))
</script>

<template>
  <div class="page todos">
    <header class="page-head">
      <div>
        <h1>待办与日程</h1>
        <p>说一句就能记下来，重复的自动排下一次</p>
      </div>
      <div class="head-actions">
        <button class="btn ghost" @click="api.exportTodos('csv')">导出 CSV</button>
        <button class="btn ghost" @click="api.exportTodos('ics')">导出日历</button>
        <button class="btn" @click="newOne">新建</button>
      </div>
    </header>

    <div class="page-body sc-scroll">
      <div class="todo-grid">
        <section class="card">
          <div class="card-head">
            <span class="card-title">清单</span>
            <span class="card-hint">
              <select v-model="doneFilter" class="mini-select" @change="load">
                <option value="0">待完成</option>
                <option value="1">已完成</option>
                <option value="all">全部</option>
              </select>
            </span>
          </div>
          <div class="card-body list">
            <input v-model="q" class="filter" placeholder="搜标题" @input="load" />
            <button
              v-for="t in sorted"
              :key="t.id"
              class="row"
              :class="{ on: editing === t.id, finished: t.done }"
              @click="open(t)"
            >
              <span class="dot" :class="t.priority" />
              <span class="row-main">
                <b>{{ t.title }}</b>
                <small>{{ fmt(t.due_at) }} · {{ REPEAT[t.repeat] || t.repeat }}</small>
              </span>
              <button class="tick" title="完成" @click.stop="finish(t)">✓</button>
              <button class="del" title="删除" @click.stop="remove(t)">×</button>
            </button>
            <p v-if="!sorted.length" class="empty">这里还是空的</p>
          </div>
        </section>

        <section class="card">
          <div class="card-head">
            <span class="card-title">{{ editing ? '改这条' : '记一条' }}</span>
            <span class="card-hint">一句话或手动填都行</span>
          </div>
          <div class="card-body edit">
            <div class="phrase">
              <input
                id="todo-phrase"
                v-model="phrase"
                placeholder="比如：明天下午三点开会，重要，提前20分钟出门"
                @keydown.enter="parse"
              />
              <button class="btn" :disabled="busy || !phrase.trim()" @click="parse">拆一句</button>
            </div>
            <div class="field">
              <label>标题</label>
              <input v-model="form.title" placeholder="要做什么" />
            </div>
            <div class="field">
              <label>时间</label>
              <input v-model="form.due_at" type="datetime-local" />
            </div>
            <div class="grid">
              <div class="field">
                <label>时长（分钟）</label>
                <input v-model.number="form.minutes" type="number" min="5" step="5" />
              </div>
              <div class="field">
                <label>优先级</label>
                <select v-model="form.priority">
                  <option value="high">高</option>
                  <option value="normal">普通</option>
                  <option value="low">低</option>
                </select>
              </div>
              <div class="field">
                <label>重复</label>
                <select v-model="form.repeat">
                  <option v-for="(label, key) in REPEAT" :key="key" :value="key">{{ label }}</option>
                </select>
              </div>
              <div class="field">
                <label>提前出门（分钟）</label>
                <input v-model.number="form.lead_minutes" type="number" min="0" step="5" />
              </div>
            </div>
            <div class="field">
              <label>标签</label>
              <input v-model="form.tags" placeholder="用逗号分开，比如 工作, 取件" />
            </div>
            <div class="field">
              <label>备注</label>
              <textarea v-model="form.note" rows="2" placeholder="可不填" />
            </div>

            <div v-if="conflicts.length" class="conflict">
              和这几件撞时间了：
              <span v-for="c in conflicts" :key="c.id">{{ c.title }}（{{ fmt(c.due_at) }}）</span>
            </div>

            <div class="actions">
              <button class="btn primary" :disabled="busy" @click="save">{{ editing ? '保存' : '加进清单' }}</button>
              <button class="btn ghost" @click="newOne">清空</button>
            </div>
            <p class="tip">提醒走托盘气泡；填了「提前出门」就按那个时间提前喊你。</p>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.todos { display: flex; flex-direction: column; height: 100%; padding: 0; }
.todo-grid { display: grid; grid-template-columns: minmax(300px, 0.9fr) minmax(360px, 1.1fr); gap: 12px; padding: 14px 16px 20px; height: 100%; }
.todo-grid .card { min-height: 0; display: flex; flex-direction: column; }
.list, .edit { overflow-y: auto; }
.filter, .field input, .field textarea, .field select, .mini-select {
  width: 100%; padding: 7px 9px; font-size: 12px; color: var(--sc-text);
  background: var(--sc-surface); border: 1px solid var(--sc-line); border-radius: 6px; outline: none;
}
.field input:focus, .field textarea:focus, .filter:focus, .phrase input:focus { border-color: var(--sc-accent); }
.mini-select { width: 90px; padding: 3px 6px; }
.filter { margin-bottom: 8px; }
.row { display: flex; align-items: center; gap: 8px; width: 100%; padding: 9px 8px; text-align: left; border: 0; border-bottom: 1px solid var(--sc-line); background: transparent; cursor: pointer; }
.row:hover, .row.on { background: rgba(28, 31, 35, 0.06); }
.row.finished { opacity: 0.55; }
.row.finished .row-main b { text-decoration: line-through; }
.dot { width: 7px; height: 7px; border-radius: 50%; background: var(--sc-line-strong); flex-shrink: 0; }
.dot.high { background: #c8483f; }
.dot.low { background: #7b8496; }
.row-main { flex: 1; min-width: 0; }
.row-main b { display: block; font-size: 12.5px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row-main small { color: var(--sc-muted); font-size: 10.5px; }
.tick, .del { width: 20px; height: 20px; padding: 0; border: 0; border-radius: 5px; background: transparent; color: var(--sc-muted); cursor: pointer; }
.tick:hover { color: var(--sc-accent); background: rgba(28, 31, 35, 0.06); }
.del:hover { color: #c8483f; background: rgba(200, 72, 63, 0.08); }
.phrase { display: flex; gap: 6px; margin-bottom: 10px; }
.phrase input { flex: 1; min-width: 0; padding: 7px 9px; font-size: 12px; border: 1px solid var(--sc-line); border-radius: 6px; outline: none; }
.field { margin-bottom: 9px; }
.field label { display: block; margin-bottom: 4px; font-size: 11px; color: var(--sc-muted); }
.field textarea { resize: vertical; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 8px; }
.conflict { padding: 8px 10px; margin-bottom: 10px; font-size: 11.5px; line-height: 1.7; color: #9a4a2f; background: rgba(196, 110, 60, 0.08); border: 1px solid rgba(196, 110, 60, 0.2); border-radius: 6px; }
.conflict span { display: block; }
.actions { display: flex; gap: 6px; margin-top: 4px; }
.tip { margin: 10px 0 0; font-size: 11px; color: var(--sc-muted); }
</style>
