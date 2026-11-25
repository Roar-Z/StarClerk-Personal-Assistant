<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api, type UsageSummary } from '../api'

const days = ref(7)
const summary = ref<UsageSummary>()
const overview = ref<any>()

const totals = computed(() => summary.value?.totals)
const scopeName: Record<string, string> = { chat: '对话', patrol: '后台巡检', memory: '记忆抽取', probe: '连接测试' }

async function load() {
  try {
    const [s, o] = await Promise.all([api.usage(days.value), api.overview()])
    summary.value = s
    overview.value = o
  } catch {
    /* 统一提示已处理 */
  }
}

function goLicense() {
  location.hash = 'model'
}

function fmt(n = 0) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

function widthOf(n: number, all: number) {
  if (!all) return '0%'
  return `${Math.max(3, Math.round((n / all) * 100))}%`
}

const maxDaily = computed(() => Math.max(1, ...(summary.value?.daily || []).map((d) => d.total_tokens)))

watch(days, load)
onMounted(load)
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div class="page-head-left">
        <span class="page-title">用量</span>
        <span class="page-sub">token 消耗与套餐</span>
      </div>
      <div class="seg">
        <button class="seg-btn" :class="{ on: days === 7 }" @click="days = 7">7 天</button>
        <button class="seg-btn" :class="{ on: days === 30 }" @click="days = 30">30 天</button>
      </div>
    </header>

    <div class="page-body sc-scroll">
      <div class="page-inner stack">
        <div class="stats">
          <div class="stat">
            <b>{{ fmt(totals?.total_tokens) }}</b>
            <span>总 token</span>
          </div>
          <div class="stat">
            <b>{{ totals?.calls || 0 }}</b>
            <span>调用次数</span>
          </div>
          <div class="stat">
            <b>{{ overview?.knowledge?.chunks || 0 }}</b>
            <span>资料分块</span>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <span class="card-title">按场景</span>
            <span class="card-hint">输入 {{ fmt(totals?.prompt_tokens) }} / 输出 {{ fmt(totals?.completion_tokens) }}</span>
          </div>
          <div class="card-body usage-list">
            <div v-for="row in summary?.by_scope || []" :key="row.scope" class="usage-row">
              <span class="usage-name">{{ scopeName[row.scope] || row.scope }}</span>
              <span class="usage-bar"><i :style="{ width: widthOf(row.total_tokens, totals?.total_tokens || 0) }" /></span>
              <span class="usage-val">{{ fmt(row.total_tokens) }}</span>
            </div>
            <p v-if="!summary?.by_scope?.length" class="empty">这段时间还没有调用记录</p>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <span class="card-title">按模型</span>
          </div>
          <div class="card-body usage-list">
            <div v-for="row in summary?.by_model || []" :key="`${row.provider}-${row.model}`" class="usage-row">
              <span class="usage-name" :title="`${row.provider}/${row.model}`">{{ row.model }}</span>
              <span class="usage-bar"><i :style="{ width: widthOf(row.total_tokens, totals?.total_tokens || 0) }" /></span>
              <span class="usage-val">{{ fmt(row.total_tokens) }}</span>
            </div>
            <p v-if="!summary?.by_model?.length" class="empty">暂无数据</p>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <span class="card-title">每日趋势</span>
            <span class="card-hint">近 {{ days }} 天</span>
          </div>
          <div v-if="summary?.daily?.length" class="card-body daily">
            <div v-for="d in summary.daily" :key="d.day" class="daily-col" :title="`${d.day}：${fmt(d.total_tokens)}`">
              <span class="daily-bar" :style="{ height: `${Math.max(4, (d.total_tokens / maxDaily) * 100)}%` }" />
              <span class="daily-day">{{ d.day.slice(5) }}</span>
            </div>
          </div>
          <div v-else class="card-body">
            <p class="empty">暂无数据</p>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <span class="card-title">档位</span>
            <span class="card-hint">{{ overview?.license?.label || '游客' }}</span>
          </div>
          <div class="card-body">
            <div class="plan-row">
              <div>
                <p class="plan-name">{{ overview?.license?.label || '游客' }}</p>
                <p class="muted-line">
                  任务 {{ overview?.plan?.used || 0 }} / {{ overview?.plan?.limit || 0 }} · 模型并发
                  {{ overview?.llm_gate?.limit || 2 }} 路（占用 {{ overview?.llm_gate?.busy || 0 }}）
                </p>
              </div>
              <button v-if="!overview?.license?.is_pro" class="btn-dark" @click="goLicense">去激活</button>
            </div>
            <p class="muted-line" style="margin: 10px 0 0">
              档位只存在本机，不联网校验；异常 {{ overview?.errors_24h || 0 }} 条（24h）。
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped src="../styles/views.css"></style>
