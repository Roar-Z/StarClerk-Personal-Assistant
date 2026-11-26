<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'

type Exam = { name: string; start: number; end: number }
type LogItem = { at: number; status: string; reason: string; new: number; detail: string }

const enabled = ref(false)
const loggedIn = ref(false)
const cookieAt = ref(0)
const exams = ref<Exam[]>([])
const logs = ref<LogItem[]>([])
const lastSync = ref<{ at: number; status: string; new: number; reason: string } | null>(null)
const busy = ref(false)

const qrOpen = ref(false)
const qrImage = ref('')
const qrKey = ref('')
const qrText = ref('请用手机学习通扫码登录')
const pollTimer = ref<number | null>(null)

const examOpen = ref(false)
const examDraft = ref<Exam[]>([])

const CONFIRM = `您即将开启【每日12:40 + 19:00 + 22:00定时查询】
规则：登录成功立刻查询一次学习通作业；每天12:40、19:00、22:00各自动查询一次，其余时间不会自动请求。
⚠️重要提醒：
1. 12:40后~19点前新发作业，等到当天19点检测；19点后~22点前新发作业，等到当天22点检测；22点之后新发作业顺延至次日12:40；本版本无手动刷新同步功能；
2. 仅读取作业截止信息，不会自动刷课、答题、提交任务；
3. 网页会话和手机学习通相互独立，一般不会挤下线；
4. 登录凭证由超星平台管控，大多可以连续多日免扫码；一旦会话失效，会弹窗提醒你重新扫码；
5. 考试保护为强制规则，考试时段会自动跳过本次查询，不可关闭；
6. 你可在当前页面随时关闭访问学习通，停止全部自动查询；
7. 该功能调用平台未公开接口，存在会话失效、账号风控风险；
8. 使用本功能带来的账号相关风险，由使用者自行承担。
是否确认开启？`

const RISK = '账号风险较低；12:40后至19点前新增作业，等到当日19点抓取；19点后至22点前新增作业，等到当日22点抓取；22点之后新增作业，等到次日12:40抓取；登录凭证由平台管理，一般可维持多日免扫码，会话失效时弹窗提示重新扫码；网页会话与手机APP相互独立，通常不会挤下线；仅读取作业信息，不自动完成任务；考试保护强制生效，考试时段自动跳过查询；你可在本页面随时关闭访问学习通；该功能调用平台未公开接口，存在账号风控风险，使用风险由使用者自行承担。'

async function load() {
  try {
    const s = await api.studyStatus()
    enabled.value = s.enabled
    loggedIn.value = s.cookie.logged_in
    cookieAt.value = s.cookie.at
    exams.value = s.exams
    logs.value = s.logs
    lastSync.value = s.last_sync?.at ? s.last_sync : null
  } catch {
    /* 提示在 api 层 */
  }
}

async function turnOn() {
  try {
    await ElMessageBox.confirm(CONFIRM, '', {
      confirmButtonText: '确认开启',
      cancelButtonText: '取消',
      type: 'warning',
      customClass: 'study-confirm',
    })
  } catch {
    return
  }
  await api.studyEnable()
  ElMessage.success('已开启，登录成功后会立刻查一次作业')
  await load()
}

async function turnOff() {
  await api.studyDisable()
  ElMessage.success('已停止访问学习通，所有自动请求都关了')
  await load()
}

function stopPoll() {
  if (pollTimer.value) window.clearInterval(pollTimer.value)
  pollTimer.value = null
}

async function openQr() {
  busy.value = true
  try {
    const r = await api.studyQrStart()
    qrKey.value = r.key
    qrImage.value = r.image
    qrText.value = '请用手机学习通扫码登录'
    qrOpen.value = true
    stopPoll()
    pollTimer.value = window.setInterval(async () => {
      try {
        const hit = await api.studyQrCheck(qrKey.value)
        if (hit.status === 'ok') {
          stopPoll()
          qrOpen.value = false
          ElMessage.success('登录成功')
          await load()
        } else if (hit.status === 'expired') {
          stopPoll()
          qrText.value = '二维码过期了，关掉后重新打开'
        } else if (hit.status === 'scanned') {
          qrText.value = '扫到了，手机上确认一下'
        }
      } catch {
        /* 轮询失败不打断，下一轮再来 */
      }
    }, 2000)
  } catch {
    /* 提示在 api 层 */
  } finally {
    busy.value = false
  }
}

function closeQr() {
  stopPoll()
  qrOpen.value = false
}

async function logout() {
  try {
    await ElMessageBox.confirm('清掉本机保存的学习通会话？下次要重新扫码。', '', { type: 'warning' })
  } catch {
    return
  }
  await api.studyLogout()
  ElMessage.success('已清除')
  await load()
}

function openExams() {
  examDraft.value = exams.value.map((x) => ({ ...x }))
  if (!examDraft.value.length) examDraft.value.push({ name: '考试', start: 0, end: 0 })
  examOpen.value = true
}

function addExam() {
  examDraft.value.push({ name: '考试', start: 0, end: 0 })
}

function delExam(i: number) {
  examDraft.value.splice(i, 1)
}

async function saveExams() {
  await api.studySaveExams(examDraft.value.filter((x) => x.start && x.end))
  examOpen.value = false
  ElMessage.success('考试时段已保存，强制保护生效')
  await load()
}

function fmt(ts: number) {
  if (!ts) return '—'
  return new Date(ts * 1000).toLocaleString('zh-CN', { hour12: false })
}

function toLocal(ts: number) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const z = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}T${z(d.getHours())}:${z(d.getMinutes())}`
}

function fromLocal(v: string) {
  if (!v) return 0
  return Math.floor(new Date(v).getTime() / 1000)
}

const statusText = { ok: '成功', failed: '失败', expired: '登录失效', skipped: '考试保护跳过', blocked: '总开关拦截', on: '开启', off: '关闭', login: '扫码登录', logout: '清除会话', exam: '考试时段' } as Record<string, string>

function onSessionExpired(e: Event) {
  const reason = (e as CustomEvent).detail || ''
  ElMessageBox.alert(`学习通会话失效，请重新扫码登录。${reason ? `原因：${reason}` : ''}`, '会话失效', {
    type: 'warning',
    confirmButtonText: '去扫码',
  })
    .then(() => openQr())
    .catch(() => {})
}

onMounted(() => {
  load()
  window.addEventListener('sc:study-expired', onSessionExpired)
})
onUnmounted(() => {
  stopPoll()
  window.removeEventListener('sc:study-expired', onSessionExpired)
})
</script>

<template>
  <div class="page study">
    <header class="page-head">
      <div>
        <h1>学习空间</h1>
        <p>学习通作业提醒 · 每天三个固定时段读取作业</p>
      </div>
      <div class="head-actions">
        <button v-if="!enabled" class="btn" :disabled="busy" @click="turnOn">开启定时模式</button>
        <button v-else class="btn ghost danger" @click="turnOff">停止访问学习通</button>
      </div>
    </header>

    <div class="page-body sc-scroll">
      <div class="study-grid">
        <section class="card">
          <div class="card-head">
            <span class="card-title">学习通作业提醒</span>
            <span class="card-hint">{{ enabled ? '运行中' : '已关闭' }}</span>
          </div>
          <div class="card-body">
            <p class="status-line">当前：每日12:40、19:00、22:00定时查询模式</p>
            <p class="hint">轮询规则：登录成功立即查询一次作业；每日12:40、19:00、22:00各自动查询一次作业；其余时间不发起自动请求。</p>

            <div class="login-row">
              <span class="badge" :class="loggedIn ? 'ok' : 'off'">{{ loggedIn ? '已登录' : '未登录' }}</span>
              <span v-if="loggedIn" class="sub">{{ fmt(cookieAt) }}</span>
              <button v-if="!loggedIn" class="btn" :disabled="busy" @click="openQr">扫码登录</button>
              <button v-else class="btn ghost" @click="logout">清除会话</button>
            </div>

            <div class="last" v-if="lastSync">
              最近同步：{{ fmt(lastSync.at) }} · {{ statusText[lastSync.status] || lastSync.status }} · 新作业 {{ lastSync.new }} 条
            </div>

            <div class="exam-box">
              <div class="exam-head">
                <b>考试时段（强制保护，不可关闭）</b>
                <button class="btn ghost small" @click="openExams">配置</button>
              </div>
              <p v-if="!exams.length" class="hint">还没录入考试时段。录入后，考试时间内会直接跳过查询。</p>
              <div v-for="(x, i) in exams" :key="i" class="exam-item">
                {{ x.name }} · {{ fmt(x.start) }} ～ {{ fmt(x.end) }}
              </div>
            </div>

            <p class="risk">{{ RISK }}</p>
          </div>
        </section>

        <section class="card">
          <div class="card-head">
            <span class="card-title">运行日志</span>
            <span class="card-hint">最近 {{ logs.length }} 条</span>
          </div>
          <div class="card-body list">
            <div v-for="(l, i) in logs" :key="i" class="log-row">
              <span class="dot" :class="l.status" />
              <div>
                <b>{{ statusText[l.status] || l.status }} · {{ l.reason }}</b>
                <small>{{ fmt(l.at) }} · 新作业 {{ l.new }} 条{{ l.detail ? ` · ${l.detail}` : '' }}</small>
              </div>
            </div>
            <p v-if="!logs.length" class="empty">还没有记录</p>
          </div>
        </section>
      </div>
    </div>

    <el-dialog v-model="qrOpen" title="学习通扫码登录" width="360px" @closed="stopPoll">
      <div class="qr-wrap">
        <div v-if="qrImage" class="qr-box">
          <img :src="qrImage" alt="扫码登录二维码" />
        </div>
        <div v-else class="qr-loading">二维码加载中…</div>
        <p>{{ qrText }}</p>
        <p class="hint">网页会话独立于学习通 APP，不会挤下线</p>
      </div>
      <template #footer>
        <button class="btn ghost" @click="closeQr">关闭</button>
      </template>
    </el-dialog>

    <el-dialog v-model="examOpen" title="考试时段" width="560px">
      <div class="exam-edit">
        <p class="hint">考试时段内强制跳过查询，不能关闭。支持多段。</p>
        <div v-for="(x, i) in examDraft" :key="i" class="exam-row">
          <input v-model="x.name" class="mini" placeholder="名称" />
          <input v-model="x.start" type="hidden" />
          <input :value="toLocal(x.start)" type="datetime-local" @input="x.start = fromLocal(($event.target as HTMLInputElement).value)" />
          <span>～</span>
          <input :value="toLocal(x.end)" type="datetime-local" @input="x.end = fromLocal(($event.target as HTMLInputElement).value)" />
          <button class="btn ghost small" @click="delExam(i)">删</button>
        </div>
        <button class="btn ghost small" @click="addExam">加一段</button>
      </div>
      <template #footer>
        <button class="btn ghost" @click="examOpen = false">取消</button>
        <button class="btn" @click="saveExams">保存</button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.study-grid { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; }
.study-grid .card { min-width: 0; }
.status-line { font-size: 14px; font-weight: 600; margin: 0 0 8px; }
.hint { font-size: 12px; color: var(--sc-muted); line-height: 1.7; margin: 6px 0; }
.login-row { display: flex; align-items: center; gap: 10px; margin: 14px 0; }
.login-row .btn { margin-left: auto; }
.badge { padding: 3px 9px; border-radius: 10px; font-size: 11px; }
.badge.ok { background: rgba(46,160,120,.14); color: #2ea078; }
.badge.off { background: var(--sc-surface-2); color: var(--sc-muted); }
.sub { font-size: 11px; color: var(--sc-muted); }
.last { font-size: 12px; color: var(--sc-text-2); padding: 8px 10px; background: var(--sc-surface-2); border-radius: 8px; }
.exam-box { margin: 16px 0; padding: 12px; border: 1px solid var(--sc-line); border-radius: 10px; }
.exam-head { display: flex; align-items: center; justify-content: space-between; font-size: 13px; }
.exam-item { font-size: 12px; color: var(--sc-text-2); padding: 6px 0; border-top: 1px solid var(--sc-line); }
.risk { font-size: 11.5px; color: var(--sc-muted); line-height: 1.8; margin-top: 16px; padding-top: 12px; border-top: 1px dashed var(--sc-line); }
.list { display: flex; flex-direction: column; gap: 6px; }
.log-row { display: flex; gap: 9px; padding: 8px 10px; border: 1px solid var(--sc-line); border-radius: 8px; }
.log-row b { font-size: 12px; font-weight: 600; }
.log-row small { display: block; font-size: 11px; color: var(--sc-muted); margin-top: 3px; }
.dot { width: 7px; height: 7px; border-radius: 50%; margin-top: 5px; flex: none; background: var(--sc-accent); }
.dot.failed, .dot.expired { background: var(--sc-danger); }
.dot.skipped, .dot.blocked { background: #c98242; }
.dot.on, .dot.login, .dot.ok { background: #2ea078; }
.empty { font-size: 12px; color: var(--sc-muted); text-align: center; padding: 24px 0; }
.btn.small { padding: 4px 9px; font-size: 11px; }
.btn.ghost.danger { color: var(--sc-danger); border-color: var(--sc-danger); }
.qr-wrap { text-align: center; }
.qr-box { width: 200px; height: 200px; margin: 0 auto 12px; }
.qr-box img { width: 100%; height: 100%; }
.qr-loading { height: 200px; display: grid; place-items: center; color: var(--sc-muted); }
.exam-edit .hint { margin-bottom: 10px; }
.exam-row { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; }
.exam-row input { flex: 1; min-width: 0; }
.exam-row input.mini { flex: 0 0 80px; }
</style>
