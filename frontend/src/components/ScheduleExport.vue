<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'

type Course = { name: string; teacher: string; room: string; week: number; day: number; s1: number; s2: number }

const DAYS = ['一', '二', '三', '四', '五', '六', '日']
const term = ref('')
const weeks = ref(20)
const preview = ref<Course[]>([])
const busy = ref(false)
const canFetch = ref(true)
const cached = ref(false)

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

async function doPreview(force = false) {
  busy.value = true
  try {
    const r = await api.studySchedulePreview(weeks.value, force)
    preview.value = r.items
    canFetch.value = r.can_fetch
    cached.value = r.cached
    ElMessage.success(r.cached ? `读到 ${r.count} 条课表记录（本机缓存）` : `读到 ${r.count} 条课表记录`)
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
    await api.studyScheduleExport(weeks.value)
    ElMessage.success('日历已下载，导入手机或电脑日历即可')
  } catch {
    /* 提示在 api 层 */
  } finally {
    busy.value = false
  }
}

async function refresh() {
  await api.studyScheduleClearCache()
  cached.value = false
  await doPreview(true)
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
      <p class="note">按周读取课表，导成日历文件导入手机或电脑。只有你点预览或导出时才请求，逐周串行、有间隔，结果缓存在本机，不做后台轮询。</p>

      <div class="term-row">
        <label>学期第一周周一</label>
        <input v-model="term" type="date" />
        <label>读几周</label>
        <input v-model.number="weeks" type="number" min="1" max="30" class="weeks" />
        <button class="btn ghost small" @click="saveTerm">保存</button>
      </div>

      <div class="acts">
        <button class="btn" :disabled="busy" @click="doPreview(false)">预览课表</button>
        <button class="btn ghost" :disabled="busy" @click="doExport">导出日历</button>
        <button v-if="cached" class="btn ghost small" :disabled="busy || !canFetch" @click="refresh">重新拉取</button>
        <span v-if="!canFetch" class="wait">刚读过，等 5 分钟再试</span>
        <span v-else-if="cached" class="wait">用的是本机缓存</span>
      </div>

      <div v-if="preview.length" class="list">
        <div v-for="(c, i) in preview" :key="i" class="row">
          <span class="day">周{{ DAYS[c.day - 1] }}</span>
          <span class="name">{{ c.name }}</span>
          <span class="meta">{{ c.s1 }}-{{ c.s2 }} 节 · 第{{ c.week }}周</span>
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
.term-row input.weeks { flex: none; width: 64px; max-width: 64px; }
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
