<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, download, type Skill } from '../api'

const items = ref<Skill[]>([])
const cats = ref<string[]>([])
const cat = ref('')
const editing = ref(false)
const form = ref({ id: '', name: '', category: '', body: '' })
const saving = ref(false)

const shown = computed(() => (cat.value ? items.value.filter((s) => s.category === cat.value) : items.value))

async function load() {
  const r = await api.skills()
  items.value = r.items
  cats.value = r.categories
}

function openNew() {
  form.value = { id: '', name: '', category: cat.value || '通用', body: '' }
  editing.value = true
}

function openEdit(s: Skill) {
  form.value = { id: s.id, name: s.name, category: s.category, body: s.body }
  editing.value = true
}

async function save() {
  if (!form.value.name.trim() || form.value.body.trim().length < 5) {
    ElMessage.warning('名字和内容都得填，内容至少写几个字')
    return
  }
  saving.value = true
  try {
    const body = { name: form.value.name.trim(), category: form.value.category.trim() || '通用', body: form.value.body }
    if (form.value.id) await api.saveSkill(form.value.id, body)
    else await api.addSkill(body)
    editing.value = false
    await load()
    ElMessage.success('存好了')
  } finally {
    saving.value = false
  }
}

async function remove(s: Skill) {
  await ElMessageBox.confirm(`删除「${s.name}」？`, '删除模板', { type: 'warning' })
  await api.delSkill(s.id)
  await load()
}

/** 用模板：把内容丢给对话页，让它自己粘进去 */
async function use(s: Skill) {
  await api.useSkill(s.id)
  window.dispatchEvent(new CustomEvent('sc:use-skill', { detail: s.body }))
}

function exportAll() {
  download('/skills/export')
}

async function importFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    const data = JSON.parse(await file.text())
    const list = Array.isArray(data) ? data : data.items
    if (!Array.isArray(list) || !list.length) throw new Error('格式不对')
    const r = await api.importSkills(list)
    ElMessage.success(`导进 ${r.added} 条`)
    await load()
  } catch (err) {
    ElMessage.error('读不了这个文件：' + (err as Error).message)
  } finally {
    input.value = ''
  }
}

function brief(s: string) {
  return s.replace(/\{[^}]*\}/g, '…').replace(/\s+/g, ' ').slice(0, 72)
}

onMounted(load)
</script>

<template>
  <div class="page skills">
    <header class="page-head">
      <div>
        <h1>模板</h1>
        <p>一段写好开头的话，点一下就填进对话，省得每次重打。</p>
      </div>
      <div class="head-actions">
        <label class="btn ghost">
          导入
          <input type="file" accept="application/json,.json" hidden @change="importFile" />
        </label>
        <button class="btn ghost" @click="exportAll">导出</button>
        <button class="btn" @click="openNew">新建模板</button>
      </div>
    </header>

    <div class="chips">
      <button :class="{ on: cat === '' }" @click="cat = ''">全部 {{ items.length }}</button>
      <button v-for="c in cats" :key="c" :class="{ on: cat === c }" @click="cat = c">{{ c }}</button>
    </div>

    <div class="grid">
      <article v-for="s in shown" :key="s.id" class="tile" @dblclick="use(s)">
        <header>
          <b>{{ s.name }}</b>
          <span class="brief-cat">{{ s.category }}</span>
        </header>
        <p class="brief">{{ brief(s.body) }}</p>
        <footer>
          <span class="used">用过 {{ s.use_count }} 次</span>
          <div class="ops">
            <button @click="use(s)">用</button>
            <button @click="openEdit(s)">改</button>
            <button class="danger" @click="remove(s)">删</button>
          </div>
        </footer>
      </article>
      <p v-if="!shown.length" class="empty">这个分类下还没有模板</p>
    </div>

    <el-dialog v-model="editing" :title="form.id ? '改模板' : '新建模板'" width="620px" append-to-body>
      <div class="form">
        <label>
          <span>名字</span>
          <el-input v-model="form.name" maxlength="40" placeholder="比如：周报整理" size="small" />
        </label>
        <label>
          <span>分类</span>
          <el-input v-model="form.category" maxlength="20" placeholder="学习 / 写作 / 编程" size="small" />
        </label>
        <label class="full">
          <span>内容（用 {input} 表示你要填进去的部分）</span>
          <el-input
            v-model="form.body"
            type="textarea"
            :rows="10"
            placeholder="你是一名……把下面的内容……&#10;&#10;原文：{input}"
          />
        </label>
      </div>
      <template #footer>
        <button class="btn ghost" @click="editing = false">取消</button>
        <button class="btn primary" :disabled="saving" @click="save">保存</button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.skills {
  padding: 18px 20px 24px;
  overflow-y: auto;
}
.head-actions {
  display: flex;
  gap: 8px;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin: 12px 0;
}
.chips button {
  padding: 3px 9px;
  font-size: 11.5px;
  color: var(--sc-text-2);
  background: var(--sc-surface);
  border: 1px solid var(--sc-line);
  border-radius: 4px;
  cursor: pointer;
}
.chips button.on {
  color: var(--sc-accent);
  background: rgba(58, 86, 212, 0.07);
  border-color: rgba(58, 86, 212, 0.28);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(238px, 1fr));
  gap: 10px;
}
.tile {
  display: flex;
  flex-direction: column;
  padding: 12px 13px 10px;
  background: var(--sc-surface);
  border: 1px solid var(--sc-line);
  border-radius: 8px;
  transition: border-color 0.15s;
}
.tile:hover {
  border-color: rgba(58, 86, 212, 0.28);
}
.tile header {
  display: flex;
  align-items: baseline;
  gap: 7px;
}
.tile b {
  font-size: 13px;
  font-weight: 600;
}
.brief-cat {
  font-size: 10.5px;
  color: var(--sc-muted);
}
.brief {
  flex: 1;
  margin: 6px 0 10px;
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--sc-muted);
}
.tile footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.used {
  font-size: 10.5px;
  color: var(--sc-muted);
}
.ops {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.15s;
}
.tile:hover .ops {
  opacity: 1;
}
.ops button {
  padding: 1px 6px;
  font-size: 11px;
  color: var(--sc-text-2);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 3px;
  cursor: pointer;
}
.ops button:hover {
  background: rgba(21, 27, 38, 0.045);
  border-color: var(--sc-line);
}
.ops button:disabled {
  color: var(--sc-muted);
  cursor: default;
}
.ops .danger {
  color: var(--sc-danger);
}
.form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.form label {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.form .full {
  grid-column: 1 / -1;
}
.form span {
  font-size: 11.5px;
  color: var(--sc-muted);
}
.empty {
  grid-column: 1 / -1;
  padding: 30px;
  text-align: center;
  font-size: 12px;
  color: var(--sc-muted);
}
</style>
