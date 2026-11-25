<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, type Todo } from '../api'
import { isGuest } from '../store'

const image = ref('')
const fileName = ref('')
const text = ref('')
const kind = ref<'express' | 'receipt'>('express')
const parsed = ref<Record<string, any> | null>(null)
const busy = ref(false)
const fileEl = ref<HTMLInputElement>()
const memoLines = ref('')
const merged = ref<{ groups: { place: string; items: { name: string; qty: number }[] }[]; text: string } | null>(null)

async function pick(e: Event) {
  const el = e.target as HTMLInputElement
  const file = el.files?.[0]
  el.value = ''
  if (!file) return
  fileName.value = file.name
  const reader = new FileReader()
  reader.onload = async () => {
    image.value = String(reader.result)
    text.value = ''
    parsed.value = null
    await runOcr()
  }
  reader.readAsDataURL(file)
}

async function runOcr() {
  if (!image.value && !text.value.trim()) return ElMessage.warning('先选张图，或者把单子上的字贴进来')
  busy.value = true
  try {
    if (image.value) {
      const r = await api.ocrLocal(image.value)
      text.value = r.text
      if (!r.count) ElMessage.info('图上没认出字，换个清楚点的')
    }
    await parseText()
  } finally {
    busy.value = false
  }
}

async function parseText() {
  if (!text.value.trim()) return
  busy.value = true
  try {
    parsed.value = await api.ocrParse({ text: text.value, kind: kind.value })
  } finally {
    busy.value = false
  }
}

async function copy(s: string, what: string) {
  if (!s) return ElMessage.warning(`还没认出${what}`)
  try {
    await navigator.clipboard.writeText(s)
  } catch {
    const ta = document.createElement('textarea')
    ta.value = s
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    ta.remove()
  }
  ElMessage.success(`${what}复制好了`)
}

async function makeMemo() {
  const p = parsed.value
  if (!p?.memo) return ElMessage.warning('先认一张单子')
  await api.addTodo({ title: p.memo, note: `来自${kind.value === 'express' ? '快递单' : '小票'}识别` })
  ElMessage.success('备忘已经放进待办清单')
}

async function importTodos() {
  const rows: Todo[] = await api.todos('0')
  memoLines.value = rows.map((t) => t.title).join('\n')
  if (!rows.length) ElMessage.info('待办清单里还没有条目')
}

async function doMerge() {
  const lines = memoLines.value.split('\n').map((x, i) => ({ text: x.trim(), id: String(i + 1) })).filter((x) => x.text)
  if (!lines.length) return ElMessage.warning('先写几条备忘，或者从待办导入')
  busy.value = true
  try {
    merged.value = await api.shoppingMerge(lines)
    ElMessage.success(`并成了 ${merged.value.groups.length} 处`)
  } finally {
    busy.value = false
  }
}

onMounted(() => window.addEventListener('sc:scan', runOcr))
onUnmounted(() => window.removeEventListener('sc:scan', runOcr))
</script>

<template>
  <div class="page scan">
    <header class="page-head">
      <div>
        <h1>扫描与清单</h1>
        <p>本地识字，不上传图片；快递、小票按字段拆好</p>
      </div>
      <div class="head-actions">
        <button class="btn ghost" @click="fileEl?.click()">选图片</button>
        <input ref="fileEl" type="file" accept="image/*" hidden @change="pick" />
      </div>
    </header>

    <div class="page-body sc-scroll">
      <div class="scan-grid">
        <section class="card">
          <div class="card-head">
            <span class="card-title">识别</span>
            <span class="card-hint">{{ fileName || '本地 OCR' }}</span>
          </div>
          <div class="card-body">
            <div class="seg">
              <button class="seg-btn" :class="{ on: kind === 'express' }" @click="kind = 'express'; parsed && parseText()">
                快递单
              </button>
              <button class="seg-btn" :class="{ on: kind === 'receipt' }" @click="kind = 'receipt'; parsed && parseText()">
                小票
              </button>
            </div>
            <textarea v-model="text" rows="7" placeholder="识别结果会放在这，也可以直接把单子上的字贴进来" />
            <div class="actions">
              <button class="btn primary" :disabled="busy" @click="runOcr">{{ busy ? '认字中…' : '开始识别' }}</button>
            </div>

            <div v-if="parsed" class="fields">
              <template v-if="kind === 'express'">
                <div class="field-row"><span>取件码</span><b>{{ parsed.pickup_code || '—' }}</b>
                  <button class="btn ghost sm" @click="copy(parsed.pickup_code, '取件码')">复制</button>
                </div>
                <div class="field-row"><span>单号</span><b>{{ parsed.tracking_no || '—' }}</b>
                  <button class="btn ghost sm" @click="copy(parsed.tracking_no, '单号')">复制</button>
                </div>
                <div class="field-row"><span>取件点</span><b>{{ parsed.station || '—' }}</b></div>
              </template>
              <template v-else>
                <div class="field-row"><span>商家</span><b>{{ parsed.seller || '—' }}</b></div>
                <div class="field-row"><span>日期</span><b>{{ parsed.date || '—' }}</b></div>
                <div class="field-row"><span>合计</span><b>¥{{ parsed.total || '—' }}</b></div>
                <div v-for="(it, i) in parsed.items || []" :key="i" class="field-row">
                  <span>明细</span><b>{{ it.name }} · {{ it.price }}</b>
                </div>
              </template>
              <button class="btn" @click="makeMemo">生成备忘</button>
            </div>
          </div>
        </section>

        <section v-if="!isGuest" class="card">
          <div class="card-head">
            <span class="card-title">采购清单合并</span>
            <span class="card-hint">按地点归类</span>
          </div>
          <div class="card-body">
            <p class="tip">一行一条，比如「两斤苹果 水果店」「在超市买牛奶 x2」。</p>
            <textarea v-model="memoLines" rows="9" placeholder="两斤苹果 水果店&#10;牛奶 x2 超市&#10;在药房买创可贴" />
            <div class="actions">
              <button class="btn ghost" @click="importTodos">从待办导入</button>
              <button class="btn primary" :disabled="busy" @click="doMerge">合并</button>
            </div>
            <div v-if="merged" class="result">
              <div v-for="g in merged.groups" :key="g.place" class="group">
                <b>【{{ g.place }}】</b>
                <span v-for="(it, i) in g.items" :key="i">{{ it.name }} ×{{ it.qty }}</span>
              </div>
              <button class="btn ghost sm" @click="copy(merged.text, '清单')">复制整张清单</button>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.scan { display: flex; flex-direction: column; height: 100%; }
.scan-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding: 14px 16px 20px; height: 100%; }
.scan-grid .card { min-height: 0; display: flex; flex-direction: column; }
textarea { width: 100%; margin-top: 10px; padding: 9px; resize: vertical; font-size: 12px; line-height: 1.7; color: var(--sc-text); background: var(--sc-surface); border: 1px solid var(--sc-line); border-radius: 6px; outline: none; }
textarea:focus { border-color: var(--sc-accent); }
.seg { display: inline-flex; gap: 2px; padding: 2px; background: rgba(21, 27, 38, 0.045); border-radius: 7px; }
.seg-btn { padding: 5px 12px; font-size: 11.5px; border: 0; border-radius: 5px; background: transparent; color: var(--sc-muted); cursor: pointer; }
.seg-btn.on { color: var(--sc-text); background: var(--sc-surface); box-shadow: 0 1px 3px rgba(21, 27, 38, 0.08); }
.actions { display: flex; gap: 6px; margin-top: 9px; }
.btn.sm { padding: 3px 8px; font-size: 11px; }
.fields { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--sc-line); }
.field-row { display: flex; align-items: center; gap: 8px; padding: 5px 0; font-size: 12px; }
.field-row span { width: 52px; color: var(--sc-muted); }
.field-row b { flex: 1; font-weight: 600; word-break: break-all; }
.tip { margin: 0; font-size: 11.5px; line-height: 1.7; color: var(--sc-muted); }
.result { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--sc-line); }
.group { display: flex; flex-wrap: wrap; gap: 6px 10px; padding: 6px 0; font-size: 12px; }
.group b { min-width: 70px; }
.group span { color: var(--sc-text-2); }
</style>
