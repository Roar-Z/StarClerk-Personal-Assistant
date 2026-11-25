<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import AppIcon from '../components/AppIcon.vue'
import { api, type Quota, type Task } from '../api'

const tasks = ref<Task[]>([])
const quota = ref<Quota>()
const running = ref<string>()
const dialog = ref(false)
const result = ref<{ title: string; body: string } | null>(null)
const form = reactive({ name: '', prompt: '', cron_minutes: 60 })

const INTERVALS = [
  { value: 30, label: '每 30 分钟' },
  { value: 60, label: '每小时' },
  { value: 180, label: '每 3 小时' },
  { value: 1440, label: '每天' },
]

async function refresh() {
  try {
    const [t, q] = await Promise.all([api.tasks(), api.quota()])
    tasks.value = t
    quota.value = q
  } catch {
    /* 提示在 api 层 */
  }
}

function fmt(ts?: number) {
  if (!ts) return '还没跑过'
  const d = new Date(ts * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
function intervalText(m: number) {
  const hit = INTERVALS.find((i) => i.value === m)
  if (hit) return hit.label
  if (m % 60 === 0) return `每 ${m / 60} 小时`
  return `每 ${m} 分钟`
}

async function add() {
  if (!form.name.trim() || !form.prompt.trim()) return ElMessage.warning('名称和巡检要求都要填')
  try {
    await api.addTask({ ...form })
    dialog.value = false
    form.name = form.prompt = ''
    form.cron_minutes = 60
    await refresh()
  } catch {
    /* 额度不足等提示已弹出 */
  }
}

async function run(t: Task) {
  running.value = t.id
  try {
    const r = await api.runTask(t.id)
    result.value = { title: t.name, body: r.result }
    await refresh()
  } catch {
    /* 同上 */
  } finally {
    running.value = undefined
  }
}

async function toggle(t: Task, v: boolean) {
  try {
    await api.toggleTask(t.id, v)
    await refresh()
  } catch {
    /* 同上 */
  }
}

async function del(t: Task) {
  try {
    await api.delTask(t.id)
    await refresh()
  } catch {
    /* 同上 */
  }
}

onMounted(refresh)
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div class="page-head-left">
        <span class="page-title">巡检任务</span>
        <span class="page-sub">{{ quota ? `${quota.used} / ${quota.limit}` : '' }}</span>
      </div>
      <div class="head-ops">
        <button class="btn-dark" @click="dialog = true">
          <AppIcon name="plus" :size="14" />
          新建
        </button>
      </div>
    </header>

    <div class="page-body sc-scroll">
      <div class="page-inner stack">
        <div v-if="!tasks.length" class="card empty-card">
          <p class="empty-title">还没有巡检任务</p>
          <p class="muted-line">建一条试试：每隔 3 小时检查本地资料里有没有风险，没有就回“无异常”。</p>
        </div>

        <div v-for="t in tasks" :key="t.id" class="card task-card" :class="{ off: !t.enabled }">
          <div class="task-top">
            <el-switch :model-value="!!t.enabled" size="small" @change="(v) => toggle(t, !!v)" />
            <span class="task-name">{{ t.name }}</span>
            <span class="chip">{{ intervalText(t.cron_minutes) }}</span>
          </div>
          <p class="task-prompt">{{ t.prompt }}</p>
          <div class="task-foot">
            <span class="task-time">上次 {{ fmt(t.last_run_at) }}</span>
            <div class="task-ops">
              <el-button link size="small" :loading="running === t.id" @click="run(t)">执行</el-button>
              <el-button link size="small" @click="del(t)">删除</el-button>
            </div>
          </div>
        </div>

        <p class="muted-line">
          调度器每 20 秒扫一次，到点自己在后台跑；有异常才会弹提醒，结果也写进任务卡片。
          <template v-if="!quota?.is_pro">免费版最多 5 个，可以到「用量」页切 Pro。</template>
        </p>
      </div>
    </div>

    <el-dialog v-model="dialog" title="新建巡检任务" width="440px" align-center>
      <label class="field-label">任务名称</label>
      <el-input v-model="form.name" size="small" placeholder="如：资料风险巡检" class="mb12" />
      <label class="field-label">巡检要求</label>
      <el-input
        v-model="form.prompt"
        type="textarea"
        :rows="4"
        resize="none"
        placeholder="如：检查今天新增的资料里有没有风险点，没有就只回复“无异常”"
        class="mb12"
      />
      <label class="field-label">执行间隔</label>
      <el-select v-model="form.cron_minutes" size="small" style="width: 100%">
        <el-option v-for="i in INTERVALS" :key="i.value" :value="i.value" :label="i.label" />
      </el-select>
      <template #footer>
        <el-button size="small" @click="dialog = false">取消</el-button>
        <el-button size="small" type="primary" @click="add">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog
      :model-value="!!result"
      :title="`执行结果 · ${result?.title ?? ''}`"
      width="460px"
      align-center
      @close="result = null"
    >
      <div class="result-text">{{ result?.body }}</div>
    </el-dialog>
  </div>
</template>

<style scoped src="../styles/views.css"></style>
