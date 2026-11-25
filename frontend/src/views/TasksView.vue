<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import AppIcon from '../components/AppIcon.vue'
import { api, type Task } from '../api'

const tasks = ref<Task[]>([])
const running = ref<string>()
const dialog = ref(false)
const result = ref<{ title: string; body: string } | null>(null)
const form = reactive({ name: '', prompt: '', cron_minutes: 60 })

async function refresh() {
  tasks.value = await api.tasks()
}
function fmt(ts?: number) {
  if (!ts) return '未运行'
  const d = new Date(ts * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
function fmtInterval(m: number) {
  if (m % 1440 === 0) return m === 1440 ? '每天' : `每 ${m / 1440} 天`
  if (m % 60 === 0) return m === 60 ? '每小时' : `每 ${m / 60} 小时`
  return `每 ${m} 分钟`
}
async function add() {
  if (!form.name.trim() || !form.prompt.trim()) return ElMessage.warning('请填写名称与巡检要求')
  await api.addTask({ ...form })
  dialog.value = false
  form.name = form.prompt = ''
  form.cron_minutes = 60
  await refresh()
}
async function run(t: Task) {
  running.value = t.id
  try {
    const r = await api.runTask(t.id)
    result.value = { title: t.name, body: r.result }
    await refresh()
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    running.value = undefined
  }
}
async function toggle(t: Task, v: boolean) {
  await api.toggleTask(t.id, v)
  await refresh()
}
async function del(t: Task) {
  await api.delTask(t.id)
  await refresh()
}
onMounted(refresh)
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div class="page-head-left">
        <span class="page-title">后台巡检</span>
        <span class="page-sub">到点自动执行，结果通过托盘提醒</span>
      </div>
      <button class="btn-dark" @click="dialog = true"><AppIcon name="plus" :size="14" />新建任务</button>
    </header>

    <div class="page-body sc-scroll">
      <div class="page-inner">
        <section class="card">
          <div class="task-head">
            <span>任务</span><span>间隔</span><span>上次执行</span><span>状态</span><span>操作</span>
          </div>

          <div v-if="!tasks.length" class="task-empty">
            <p>还没有巡检任务</p>
            <span>例如：每天早上 9 点检查知识库新增资料中的风险项，无异常只回复“无异常”。</span>
          </div>

          <div v-for="t in tasks" :key="t.id" class="task-row" :class="{ off: !t.enabled }">
            <div class="task-main">
              <div class="task-name">{{ t.name }}</div>
              <div class="task-prompt">{{ t.prompt }}</div>
            </div>
            <div class="task-cell">{{ fmtInterval(t.cron_minutes) }}</div>
            <div class="task-cell num">{{ fmt(t.last_run_at) }}</div>
            <div class="task-cell">
              <el-switch :model-value="!!t.enabled" size="small" @change="(v) => toggle(t, !!v)" />
            </div>
            <div class="task-ops">
              <el-button link size="small" :loading="running === t.id" @click="run(t)">执行</el-button>
              <el-button link size="small" @click="del(t)">删除</el-button>
            </div>
          </div>
        </section>

        <p class="muted-line mt12">巡检任务由进程内调度器每 30 秒扫描一次，触发结果会同时写入会话历史与托盘通知。</p>
      </div>
    </div>

    <el-dialog v-model="dialog" title="新建巡检任务" width="480px" align-center>
      <label class="field-label">任务名称</label>
      <el-input v-model="form.name" size="small" placeholder="如：每日资料风险巡检" class="mb12" />
      <label class="field-label">巡检要求</label>
      <el-input v-model="form.prompt" type="textarea" :rows="4" resize="none" placeholder="如：检查今日新增资料中的风险点，无异常只回复“无异常”" class="mb12" />
      <label class="field-label">执行间隔（分钟）</label>
      <el-input-number v-model="form.cron_minutes" :min="1" :max="1440" size="small" controls-position="right" />
      <template #footer>
        <el-button size="small" @click="dialog = false">取消</el-button>
        <el-button size="small" type="primary" @click="add">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog :model-value="!!result" :title="`执行结果 · ${result?.title ?? ''}`" width="520px" align-center @close="result = null">
      <div class="result-text">{{ result?.body }}</div>
    </el-dialog>
  </div>
</template>

<style scoped src="../styles/views.css"></style>
