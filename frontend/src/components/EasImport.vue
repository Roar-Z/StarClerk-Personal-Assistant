<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'

type Course = { name: string; teacher: string; room: string; day: number; s1: number; s2: number; w1: number; w2: number; parity: string }

const DAYS = ['一', '二', '三', '四', '五', '六', '日']
const portal = ref('https://portal.gdust.edu.cn')
const saved = ref(0)
const preview = ref<Course[]>([])
const busy = ref(false)
const pywebview = ref(false)

async function load() {
  try {
    const r = await api.easInfo()
    portal.value = r.portal
    saved.value = r.saved.count
  } catch {
    /* 提示在 api 层 */
  }
  pywebview.value = !!(window as any).pywebview?.api
}

async function openPortal() {
  const bridge = (window as any).pywebview?.api
  if (!bridge?.open_eas) {
    ElMessage.warning('请用桌面版打开，浏览器里不能开内嵌教务窗口')
    return
  }
  await bridge.open_eas()
  ElMessage.info('已打开教务窗口，请自己登录并进入课表页，然后回来点「抓取当前页」')
}

async function grab() {
  const bridge = (window as any).pywebview?.api
  if (!bridge?.grab_eas_html) {
    ElMessage.warning('请用桌面版打开')
    return
  }
  busy.value = true
  try {
    const html = String(await bridge.grab_eas_html() || '')
    if (!html) {
      ElMessage.warning('没读到页面，先在教务窗口里登录并打开课表页')
      return
    }
    const r = await api.easPreview(html)
    preview.value = r.items
    if (!r.count) ElMessage.warning('没认出课程，可能还没到课表页，或课表结构需要适配')
    else ElMessage.success(`认出 ${r.count} 条课表记录，核对后点保存`)
  } catch {
    /* 提示在 api 层 */
  } finally {
    busy.value = false
  }
}

async function save() {
  if (!preview.value.length) return
  try {
    const r = await api.easSave(preview.value)
    saved.value = r.count
    ElMessage.success('课表已存到本机')
  } catch {
    /* 提示在 api 层 */
  }
}

async function clear() {
  try {
    await ElMessageBox.confirm('清掉本机保存的课表？', '', { type: 'warning' })
  } catch {
    return
  }
  await api.easClear()
  saved.value = 0
  preview.value = []
  ElMessage.success('已清空')
}

async function exportIcs() {
  try {
    await api.easExport()
    ElMessage.success('日历已下载')
  } catch {
    /* 提示在 api 层 */
  }
}

onMounted(load)
</script>

<template>
  <section class="card">
    <div class="card-head">
      <span class="card-title">教务课表导入</span>
      <span class="card-hint">广东科技学院 · 只存本机</span>
    </div>
    <div class="card-body">
      <p class="note">打开内嵌浏览器，自己登录智慧校园门户进入课表页，再回来点抓取。程序不碰登录、不上传任何数据，只把当前页的课程读出来存到本机。</p>

      <div class="acts">
        <button class="btn" :disabled="busy" @click="openPortal">打开教务窗口</button>
        <button class="btn ghost" :disabled="busy" @click="grab">抓取当前页</button>
        <button v-if="saved" class="btn ghost" @click="exportIcs">导出日历</button>
        <button v-if="saved" class="btn ghost small" @click="clear">清空</button>
      </div>
      <p v-if="!pywebview" class="warn">当前是浏览器预览模式，内嵌窗口不可用。打包成桌面版后即可使用。</p>
      <p class="status">已存课表：{{ saved }} 条</p>

      <div v-if="preview.length" class="list">
        <div v-for="(c, i) in preview" :key="i" class="row">
          <span class="day">周{{ DAYS[c.day - 1] }}</span>
          <span class="name">{{ c.name }}</span>
          <span class="meta">{{ c.s1 }}{{ c.s2 > c.s1 ? '-' + c.s2 : '' }} 节 · {{ c.w1 }}-{{ c.w2 }}周{{ c.parity ? '(' + c.parity + ')' : '' }}</span>
          <span v-if="c.room" class="room">{{ c.room }}</span>
        </div>
        <button class="btn" @click="save">确认保存</button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.note { margin: 0 0 14px; font-size: 11.5px; color: var(--sc-muted); line-height: 1.7; }
.acts { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.warn { font-size: 11px; color: #b07a2c; margin: 10px 0 0; }
.status { font-size: 12px; color: var(--sc-text-2); margin: 10px 0 0; }
.btn.small { padding: 4px 9px; font-size: 11px; }
.list { margin-top: 14px; border-top: 1px solid var(--sc-line); }
.row { display: flex; align-items: center; gap: 10px; padding: 8px 2px; border-bottom: 1px solid var(--sc-line); font-size: 12px; }
.day { width: 30px; flex: none; color: var(--sc-text-2); }
.name { flex: 1; min-width: 0; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.meta { color: var(--sc-muted); font-size: 11px; white-space: nowrap; }
.room { color: var(--sc-muted); font-size: 11px; white-space: nowrap; }
.list > .btn { margin-top: 12px; }
</style>
