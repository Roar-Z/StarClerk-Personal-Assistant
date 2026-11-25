<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, type DocMeta, type Note } from '../api'
import { fmtTime } from '../store'

const items = ref<Note[]>([])
const cats = ref<{ category: string; n: number }[]>([])
const total = ref(0)
const q = ref('')
const cat = ref('')
const cur = ref<Note | null>(null)
const draft = ref({ title: '', body: '', category: '', tags: '' })
const busy = ref(false)
const dirty = computed(() => {
  const n = cur.value
  if (!n) return false
  return (
    n.title !== draft.value.title ||
    n.body !== draft.value.body ||
    n.category !== draft.value.category ||
    n.tags !== draft.value.tags
  )
})

// 统一检索的结果，点开就盖在列表上面
const searching = ref(false)
const hits = ref<{ notes: Note[]; docs: DocMeta[] } | null>(null)

async function load() {
  const r = await api.notes(q.value, cat.value)
  items.value = r.items
  cats.value = r.categories
  total.value = r.total
  if (!cur.value && r.items.length) open(r.items[0])
}

function open(n: Note) {
  cur.value = n
  draft.value = { title: n.title, body: n.body, category: n.category, tags: n.tags }
}

async function create() {
  const n = await api.addNote({ title: '未命名笔记', body: '', category: cat.value || '' })
  items.value = [n, ...items.value]
  total.value += 1
  open(n)
}

async function save() {
  if (!cur.value) return
  busy.value = true
  try {
    const n = await api.saveNote(cur.value.id, { ...draft.value })
    const i = items.value.findIndex((x) => x.id === n.id)
    if (i >= 0) items.value[i] = n
    open(n)
    ElMessage.success('存好了')
  } finally {
    busy.value = false
  }
}

async function remove() {
  if (!cur.value) return
  await ElMessageBox.confirm('删了就找不回来，确定？', '删除笔记', { type: 'warning' })
  await api.delNote(cur.value.id)
  items.value = items.value.filter((x) => x.id !== cur.value!.id)
  cur.value = null
  total.value -= 1
  if (items.value.length) open(items.value[0])
}

let timer: number | undefined
function search() {
  window.clearTimeout(timer)
  timer = window.setTimeout(async () => {
    if (!q.value.trim()) {
      hits.value = null
      searching.value = false
      await load()
      return
    }
    searching.value = true
    hits.value = await api.noteSearch(q.value.trim())
  }, 260)
}

function pick(n: Note) {
  searching.value = false
  const i = items.value.findIndex((x) => x.id === n.id)
  if (i < 0) items.value = [n, ...items.value]
  open(n)
}

function excerpt(s: string) {
  return (s || '').replace(/\s+/g, ' ').slice(0, 46) || '空的'
}

onMounted(load)
</script>

<template>
  <div class="page notes">
    <header class="page-head">
      <div>
        <h1>笔记</h1>
        <p>随手记的东西放这，搜的时候连资料库一起搜。</p>
      </div>
      <div class="head-actions">
        <el-input v-model="q" placeholder="搜标题、正文、标签" clearable size="small" class="search" @input="search" />
        <button class="btn" @click="create">新建</button>
      </div>
    </header>

    <div class="body">
      <aside class="list">
        <div class="cats">
          <button :class="{ on: cat === '' }" @click="((cat = ''), load())">全部 {{ total }}</button>
          <button
            v-for="c in cats"
            :key="c.category"
            :class="{ on: cat === c.category }"
            @click="((cat = c.category), load())"
          >
            {{ c.category || '未分类' }} {{ c.n }}
          </button>
        </div>

        <div v-if="searching" class="hit-layer">
          <p class="hit-cap">笔记 {{ hits?.notes.length || 0 }}</p>
          <button v-for="n in hits?.notes" :key="n.id" class="item" @click="pick(n)">
            <b>{{ n.title }}</b>
            <span>{{ excerpt(n.body) }}</span>
          </button>
          <p class="hit-cap">资料 {{ hits?.docs.length || 0 }}</p>
          <div v-for="d in hits?.docs" :key="d.doc_id" class="item doc">
            <b>{{ d.source }}</b>
            <span>{{ d.chunks }} 个片段</span>
          </div>
          <p v-if="!hits?.notes.length && !hits?.docs.length" class="empty">没有匹配的东西</p>
        </div>

        <template v-else>
          <button
            v-for="n in items"
            :key="n.id"
            class="item"
            :class="{ on: cur?.id === n.id }"
            @click="open(n)"
          >
            <b>{{ n.title }}</b>
            <span>{{ excerpt(n.body) }}</span>
            <em>{{ fmtTime(n.updated_at) }}</em>
          </button>
          <p v-if="!items.length" class="empty">还没有笔记，点右上角新建</p>
        </template>
      </aside>

      <section class="editor">
        <template v-if="cur">
          <input v-model="draft.title" class="title" placeholder="标题" />
          <div class="meta">
            <input v-model="draft.category" class="mini" placeholder="分类" />
            <input v-model="draft.tags" class="mini tags" placeholder="标签，逗号隔开" />
            <span class="stamp">{{ fmtTime(cur.updated_at) }}</span>
          </div>
          <textarea v-model="draft.body" class="paper" placeholder="正文，支持 Markdown"></textarea>
          <footer class="bar">
            <button class="link danger" @click="remove">删除</button>
            <div>
              <span v-if="dirty" class="hint">有未保存的改动</span>
              <button class="btn primary" :disabled="!dirty || busy" @click="save">保存</button>
            </div>
          </footer>
        </template>
        <p v-else class="empty big">左边选一条，或者新建一条</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.notes {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 18px 20px 0;
}
.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.search {
  width: 210px;
}
.body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 250px 1fr;
  gap: 12px;
  margin-top: 12px;
  padding-bottom: 16px;
}
.list {
  position: relative;
  overflow-y: auto;
  background: var(--sc-surface);
  border: 1px solid var(--sc-line);
  border-radius: 8px;
}
.cats {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 8px;
  border-bottom: 1px solid var(--sc-line);
}
.cats button {
  padding: 2px 7px;
  font-size: 11.5px;
  color: var(--sc-text-2);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  cursor: pointer;
}
.cats button.on {
  color: var(--sc-accent);
  background: rgba(58, 86, 212, 0.07);
  border-color: rgba(58, 86, 212, 0.28);
}
.item {
  display: block;
  width: 100%;
  padding: 9px 10px;
  text-align: left;
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--sc-line);
  cursor: pointer;
}
.item:hover {
  background: rgba(21, 27, 38, 0.045);
}
.item.on {
  background: rgba(58, 86, 212, 0.07);
}
.item b {
  display: block;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--sc-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.item span {
  display: block;
  margin-top: 2px;
  font-size: 11.5px;
  color: var(--sc-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.item em {
  display: block;
  margin-top: 3px;
  font-size: 10.5px;
  font-style: normal;
  color: var(--sc-muted);
}
.item.doc {
  cursor: default;
}
.hit-layer {
  max-height: 100%;
  overflow-y: auto;
}
.hit-cap {
  padding: 7px 10px 2px;
  font-size: 10.5px;
  letter-spacing: 0.08em;
  color: var(--sc-muted);
}
.editor {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 14px 16px 12px;
  background: var(--sc-surface);
  border: 1px solid var(--sc-line);
  border-radius: 8px;
}
.title {
  width: 100%;
  padding: 0 0 8px;
  font-family: inherit;
  font-size: 17px;
  font-weight: 600;
  color: var(--sc-text);
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--sc-line);
  outline: none;
}
.meta {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 0;
}
.mini {
  width: 110px;
  height: 24px;
  padding: 0 7px;
  font-family: inherit;
  font-size: 11.5px;
  color: var(--sc-text-2);
  background: rgba(21, 27, 38, 0.045);
  border: 1px solid transparent;
  border-radius: 4px;
  outline: none;
}
.mini:focus {
  background: #fff;
  border-color: var(--sc-line);
}
.mini.tags {
  width: 190px;
}
.stamp {
  margin-left: auto;
  font-size: 11px;
  color: var(--sc-muted);
}
.paper {
  flex: 1;
  min-height: 0;
  padding: 10px 2px;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.85;
  color: var(--sc-text);
  background: transparent;
  border: 0;
  outline: none;
  resize: none;
}
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 8px;
  border-top: 1px solid var(--sc-line);
}
bar .hint {
  margin-right: 10px;
}
.hint {
  margin-right: 10px;
  font-size: 11.5px;
  color: var(--sc-muted);
}
.empty {
  padding: 14px 12px;
  font-size: 12px;
  color: var(--sc-muted);
}
.empty.big {
  margin: auto;
  font-size: 13px;
}
</style>
