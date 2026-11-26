<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, type FocusSession, type FocusStats } from '../api'

const session = ref<FocusSession | null>(null)
const stats = ref<FocusStats | null>(null)
const days = ref(7)
const now = ref(Date.now() / 1000)
let ticker: number | null = null

const MODES = [
  { key: 'focus', label: '专注', min: 25 },
  { key: 'short', label: '短休息', min: 5 },
  { key: 'long', label: '长休息', min: 15 },
]
const mode = ref('focus')
const minutes = ref(25)

const active = computed(() => !!session.value?.active)
const paused = computed(() => !!session.value?.paused_at)
const remain = computed(() => {
  const s = session.value
  if (!s?.active) return minutes.value * 60
  const end = s.paused_at || s.end_at
  return Math.max(0, Math.floor(end - now.value))
})
const clock = computed(() => {
  const n = remain.value
  const m = Math.floor(n / 60)
  const s = n % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
})
const progress = computed(() => {
  const s = session.value
  if (!s?.active) return 0
  const total = s.minutes * 60
  return total ? Math.max(0, Math.min(1, remain.value / total)) : 0
})
const modeLabel = computed(() => MODES.find((x) => x.key === (session.value?.mode || mode.value))?.label || '专注')
const maxDay = computed(() => Math.max(1, ...(stats.value?.daily || []).map((d) => d.minutes)))

async function load() {
  try {
    const r = await api.focusStatus(days.value)
    session.value = r.session?.active ? r.session : null
    stats.value = r.stats
    if (!r.session?.active) {
      const d = r.stats.defaults
      MODES[0].min = d.focus
      MODES[1].min = d.short
      MODES[2].min = d.long
      minutes.value = d.focus
    }
    window.dispatchEvent(new CustomEvent('sc:focus-change', { detail: !!session.value?.active }))
  } catch {
    /* 提示在 api 层 */
  }
}

function pickMode(k: string, min: number) {
  if (active.value) return
  mode.value = k
  minutes.value = min
}

async function start() {
  try {
    const r = await api.focusStart(minutes.value, mode.value)
    session.value = r.session
    window.dispatchEvent(new CustomEvent('sc:focus-change', { detail: true }))
    ElMessage.success(mode.value === 'focus' ? '专注开始，悬浮窗消息已屏蔽' : '休息开始')
  } catch {
    /* 提示在 api 层 */
  }
}

async function pause() {
  const r = await api.focusPause()
  session.value = r.session
}

async function resume() {
  const r = await api.focusResume()
  session.value = r.session
}

async function stop() {
  try {
    const r = await api.focusStop()
    session.value = null
    window.dispatchEvent(new CustomEvent('sc:focus-change', { detail: false }))
    if (r.session?.last_complete) ElMessage.success('番茄完成，记入统计')
    else ElMessage.info('已结束')
    await load()
  } catch {
    /* 提示在 api 层 */
  }
}

function fmtHour(min: number) {
  if (!min) return '0'
  return (min / 60).toFixed(1)
}

onMounted(() => {
  load()
  ticker = window.setInterval(() => {
    now.value = Date.now() / 1000
    if (active.value && !paused.value && remain.value <= 0) stop()
  }, 1000)
})
onUnmounted(() => {
  // 只清定时器，别在这发解除——切走页面不算结束专注
  if (ticker) window.clearInterval(ticker)
})
</script>

<template>
  <section class="card focus-card">
    <div class="card-head">
      <span class="card-title">专注番茄钟</span>
      <span class="card-hint">{{ active ? (paused ? '已暂停' : '专注中 · 消息已屏蔽') : '25 分钟专注 + 5 分钟休息' }}</span>
    </div>
    <div class="card-body focus-body">
      <div class="clock-wrap">
        <svg viewBox="0 0 120 120" class="ring">
          <circle cx="60" cy="60" r="54" class="ring-bg" />
          <circle cx="60" cy="60" r="54" class="ring-fg" :style="{ strokeDashoffset: 339 - 339 * progress }" />
        </svg>
        <div class="clock">
          <b>{{ clock }}</b>
          <span>{{ modeLabel }}</span>
        </div>
      </div>

      <div class="control">
        <div v-if="!active" class="modes">
          <button
            v-for="m in MODES"
            :key="m.key"
            class="mode"
            :class="{ on: mode === m.key }"
            @click="pickMode(m.key, m.min)"
          >{{ m.label }}</button>
        </div>
        <div v-if="!active" class="minutes">
          <button class="step" @click="minutes = Math.max(1, minutes - 5)">−</button>
          <span>{{ minutes }} 分钟</span>
          <button class="step" @click="minutes = Math.min(180, minutes + 5)">+</button>
        </div>
        <button v-if="!active" class="btn" @click="start">开始</button>
        <template v-else>
          <button v-if="paused" class="btn" @click="resume">继续</button>
          <button v-else class="btn ghost" @click="pause">暂停</button>
          <button class="btn ghost danger" @click="stop">结束</button>
        </template>
        <p class="hint">专注开始时自动屏蔽待办提醒和悬浮窗消息，结束后恢复</p>
      </div>
    </div>

    <div class="stat-row">
      <div class="stat"><b>{{ fmtHour(stats?.today_minutes) }}h</b><span>今日专注</span></div>
      <div class="stat"><b>{{ stats?.today_count || 0 }}</b><span>今日番茄</span></div>
      <div class="stat"><b>{{ stats?.total_count || 0 }}</b><span>累计番茄</span></div>
      <div class="stat"><b>{{ stats?.streak || 0 }}</b><span>连续天数</span></div>
    </div>

    <div class="chart">
      <div class="chart-head">
        <span>近 {{ days }} 天专注时长</span>
        <span class="seg">
          <button class="seg-btn" :class="{ on: days === 7 }" @click="days = 7; load()">7 天</button>
          <button class="seg-btn" :class="{ on: days === 30 }" @click="days = 30; load()">30 天</button>
        </span>
      </div>
      <div class="bars">
        <div v-for="d in stats?.daily || []" :key="d.date" class="bar-col" :title="`${d.date} · ${d.minutes} 分钟`">
          <div class="bar" :style="{ height: `${Math.max(3, (d.minutes / maxDay) * 100)}%` }" />
          <small>{{ d.date.slice(5) }}</small>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.focus-card { min-width: 0; }
.focus-body { display: flex; align-items: center; gap: 28px; }
.clock-wrap { position: relative; width: 150px; height: 150px; flex: none; }
.ring { width: 100%; height: 100%; transform: rotate(-90deg); }
.ring-bg, .ring-fg { fill: none; stroke-width: 7; }
.ring-bg { stroke: var(--sc-line); }
.ring-fg { stroke: var(--sc-accent); stroke-linecap: round; stroke-dasharray: 339; transition: stroke-dashoffset .5s linear; }
.clock { position: absolute; inset: 0; display: grid; place-content: center; text-align: center; }
.clock b { font-size: 30px; font-variant-numeric: tabular-nums; }
.clock span { font-size: 11px; color: var(--sc-muted); margin-top: 2px; }
.control { flex: 1; min-width: 0; }
.modes { display: flex; gap: 6px; margin-bottom: 10px; }
.mode { padding: 5px 12px; font-size: 12px; border: 1px solid var(--sc-line); border-radius: 6px; background: var(--sc-surface); color: var(--sc-text-2); cursor: pointer; }
.mode.on { border-color: var(--sc-accent); color: var(--sc-accent); }
.minutes { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.minutes span { font-size: 13px; min-width: 60px; text-align: center; }
.step { width: 26px; height: 26px; border: 1px solid var(--sc-line); border-radius: 6px; background: var(--sc-surface); cursor: pointer; }
.control .btn { margin-right: 8px; }
.hint { font-size: 11.5px; color: var(--sc-muted); margin-top: 10px; line-height: 1.6; }
.stat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 18px; }
.stat { padding: 10px; border: 1px solid var(--sc-line); border-radius: 8px; text-align: center; }
.stat b { display: block; font-size: 18px; }
.stat span { font-size: 11px; color: var(--sc-muted); }
.chart { margin-top: 18px; }
.chart-head { display: flex; justify-content: space-between; align-items: center; font-size: 12px; margin-bottom: 8px; }
.seg { display: inline-flex; gap: 2px; }
.seg-btn { font-size: 11px; padding: 3px 8px; border: 1px solid var(--sc-line); background: var(--sc-surface); color: var(--sc-muted); border-radius: 5px; cursor: pointer; }
.seg-btn.on { color: var(--sc-accent); border-color: var(--sc-accent); }
.bars { display: flex; align-items: flex-end; gap: 4px; height: 90px; padding-top: 6px; border-bottom: 1px solid var(--sc-line); }
.bar-col { flex: 1; height: 100%; display: flex; flex-direction: column; justify-content: flex-end; align-items: center; min-width: 0; }
.bar { width: 100%; background: var(--sc-accent); border-radius: 3px 3px 0 0; opacity: .8; }
.bar-col small { font-size: 9px; color: var(--sc-muted); margin-top: 3px; white-space: nowrap; }
@media (max-width: 900px) { .focus-body { flex-direction: column; } .stat-row { grid-template-columns: repeat(2, 1fr); } }
</style>
