<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'

type Course = { name: string; teacher: string; room: string; day: number; s1: number; s2: number; w1: number; w2: number }

const DAYS = ['一', '二', '三', '四', '五', '六', '日']
const term = ref('')
const preview = ref<Course[]>([])
const busy = ref(false)
const canFetch = ref(true)

async function load() {
  try {
    term.value = (await api.studyTerm()).date
  } catch {
    /* 提示在 api 层 */
  }
}

async function saveTerm() {
  if (!term.value) return ElMessage.warning('先选学期第一周周一的日期')
  try {
    await api.studySaveTerm(term.value)
    ElMessage.success('已保存')
  } catch {
    /* 提示在 api 层 */
  }
}

async function doPreview() {
  busy.value = true
  try {
    const r = await api.studySchedulePreview()
    preview.value = r.items
    canFetch.value = r.can_fetch
    ElMessage.success(`读到 ${r.count} 门课`)
  } catch {
    /* 429 会提示还需等多久 */
  } finally {
    busy.value = false
  }
}

async function doExport() {
  if (!term.value) return ElMessage.warning('先填学期第一周周一的日期')
  busy.value = true
  try {
    await api.studyScheduleExport()
    ElMessage.success('日历已下载，导入手机或电脑日历即可')
    canFetch.value = false
  } catch {
    /* 提示在 api 层 */
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="card">
    <div class="card-head">
      <span class="card-title">课表日历导出</span>
      <span class="card-hint">只读 · 低频 · 不自动请求</span>
    </div>
    <div class="card-body">
      <p class="note">把课表导成日历文件，导入手机或电脑日历。只有你点预览或导出时才会读一次课表，两次之间至少隔 5 分钟，不做后台轮询。</p>

      <div class="term-row">
        <label>学期第一周周一</label>
        <input v-model="term" type="date" />
        <button class="btn ghost small" @click="saveTerm">保存</button>
      </div>

      <div class="acts">
        <button class="btn" :disabled="busy || !canFetch" @click="doPreview">预览课表</button>
        <button class="btn ghost" :disabled="busy || !canFetch" @click="doExport">导出日历</button>
        <span v-if="!canFetch" class="wait">刚读过，等 5 分钟再试</span>
      </div>

      <div v-if="preview.length" class="list">
        <div v-for="(c, i) in preview" :key="i" class="row">
          <span class="day">周{{ DAYS[c.day - 1] }}</span>
          <span class="name">{{ c.name }}</span>
          <span class="meta">{{ c.s1 }}-{{ c.s2 }} 节 · 第{{ c.w1 }}-{{ c.w2 }}周</span>
          <span v-if="c.room" class="room">{{ c.room }}</span>
        </div>
      </div>
      <p v-else-if="busy" class="empty">读取中…</p>
    </div>
  </section>
</template>

<style scoped>
.note { margin: 0 0 14px; font-size: 11.5px; color: var(--sc-muted); line-height: 1.7; }
.term-row { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.term-row label { font-size: 12px; color: var(--sc-text-2); white-space: nowrap; }
.term-row input { flex: 1; max-width: 180px; }
.acts { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.wait { font-size: 11px; color: var(--sc-muted); }
.btn.small { padding: 4px 9px; font-size: 11px; }
.list { display: flex; flex-direction: column; border-top: 1px solid var(--sc-line); }
.row { display: flex; align-items: center; gap: 10px; padding: 8px 2px; border-bottom: 1px solid var(--sc-line); font-size: 12px; }
.day { width: 30px; flex: none; color: var(--sc-text-2); }
.name { flex: 1; min-width: 0; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.meta { color: var(--sc-muted); font-size: 11px; white-space: nowrap; }
.room { color: var(--sc-muted); font-size: 11px; white-space: nowrap; }
.empty { font-size: 12px; color: var(--sc-muted); padding: 12px 0; margin: 0; }
</style>
