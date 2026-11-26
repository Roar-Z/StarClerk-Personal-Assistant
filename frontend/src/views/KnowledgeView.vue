<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import AppIcon from '../components/AppIcon.vue'
import { api, download, type DocMeta, type MindMap, type WorkSpace } from '../api'
import { isLoggedIn, me } from '../store'

const stats = ref({ chunks: 0, memories: 0, dim: 0 })
const docs = ref<DocMeta[]>([])
const text = ref('')
const source = ref('')
const busy = ref(false)
const fileInput = ref<HTMLInputElement>()

// 没建工作区时一直用 default
const workspaces = ref<WorkSpace[]>([])
const ws = ref('')

const mmOpen = ref(false)
const mmBusy = ref(false)
const mmDoc = ref('')
const mmResult = ref<MindMap | null>(null)

// 批量处理：勾几份出来做摘要/翻译/抽表格，最多 10 份
const picked = ref<string[]>([])
const batchOpen = ref(false)
const batchAction = ref<'summary' | 'translate' | 'table'>('summary')
const batchLang = ref('中文')
const batchBusy = ref(false)
const batchRes = ref<{ source: string; ok: boolean; text: string }[]>([])
const batchCsv = ref('')

function togglePick(id: string) {
  const i = picked.value.indexOf(id)
  if (i >= 0) picked.value.splice(i, 1)
  else if (picked.value.length < 10) picked.value.push(id)
  else ElMessage.warning('一次最多选 10 份')
}

function openBatch() {
  batchRes.value = []
  batchCsv.value = ''
  batchOpen.value = true
}

async function runBatch() {
  if (!picked.value.length) return ElMessage.warning('先选中要处理的资料')
  batchBusy.value = true
  try {
    const r = await api.batchAi({ doc_ids: picked.value, action: batchAction.value, lang: batchLang.value })
    batchRes.value = r.items
    batchCsv.value = r.csv
    ElMessage.success(`${r.ok_count}/${r.items.length} 份处理好了`)
  } catch {
    /* 提示在 api 层 */
  } finally {
    batchBusy.value = false
  }
}

/** 表格结果直接存 csv，Excel 打开就行 */
function saveCsv() {
  const blob = new Blob([`\ufeff${batchCsv.value}`], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `tables-${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}

async function copyAll() {
  const body = batchRes.value.map((x) => `【${x.source}】\n${x.text}`).join('\n\n')
  try {
    await navigator.clipboard.writeText(body)
    ElMessage.success('已经复制到剪贴板')
  } catch {
    ElMessage.warning('剪贴板不给用，手动选中复制吧')
  }
}

async function refresh() {
  try {
    const [s, d] = await Promise.all([api.stats(), api.documents(ws.value)])
    stats.value = s
    docs.value = d
    picked.value = picked.value.filter((id) => d.some((x) => x.doc_id === id))
    if (isLoggedIn.value) workspaces.value = (await api.workspaces()).items
  } catch {
    /* 提示在 api 层 */
  }
}

async function uploadFiles(e: Event) {
  const files = (e.target as HTMLInputElement).files
  if (!files?.length) return
  busy.value = true
  try {
    for (const f of Array.from(files)) {
      const r = await api.upload(f, ws.value)
      if (r.pages) ElMessage.success(`${r.source} 共 ${r.pages} 页，已切 ${r.chunks} 段${r.ocr_pages ? `（${r.ocr_pages} 页走了 OCR）` : ''}`)
      else ElMessage.success(`${r.source} 已切 ${r.chunks} 段`)
    }
    await refresh()
  } catch {
    /* 同上，常见是向量服务没起 */
  } finally {
    busy.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

async function addText() {
  if (text.value.trim().length < 10) return ElMessage.warning('内容太短，至少 10 个字')
  busy.value = true
  try {
    const r = await api.addText(text.value, source.value.trim() || '粘贴文本', ws.value)
    ElMessage.success(`已索引 ${r.chunks} 段`)
    text.value = ''
    await refresh()
  } catch {
    /* 同上 */
  } finally {
    busy.value = false
  }
}

async function remove(d: DocMeta) {
  try {
    await api.delDoc(d.doc_id)
    docs.value = docs.value.filter((x) => x.doc_id !== d.doc_id)
    stats.value = await api.stats()
  } catch {
    /* 同上 */
  }
}

function openMindmap(docId = '') {
  mmDoc.value = docId || docs.value[0]?.doc_id || ''
  mmResult.value = null
  mmOpen.value = true
}

async function genMindmap() {
  if (!mmDoc.value) return ElMessage.warning('先选一份资料')
  mmBusy.value = true
  try {
    mmResult.value = await api.mindmap({ doc_id: mmDoc.value })
    ElMessage.success('大纲生成好了')
  } catch {
    /* 模型不可用时 api 层会提示 */
  } finally {
    mmBusy.value = false
  }
}

function exportMindmap() {
  if (mmResult.value) download(`/mindmap/${mmResult.value.id}/export`)
}

onMounted(refresh)
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div class="page-head-left">
        <span class="page-title">资料库</span>
        <span class="page-sub">本机 · {{ docs.length }}/{{ me?.limits.docs ?? 0 }} 份</span>
      </div>
      <el-select
        v-if="isLoggedIn && workspaces.length > 1"
        v-model="ws"
        size="small"
        style="width: 104px"
        @change="refresh"
      >
        <el-option v-for="w in workspaces" :key="w.name" :label="`${w.name} ${w.docs}`" :value="w.name" />
      </el-select>
      <input ref="fileInput" type="file" multiple accept=".pdf,.txt,.md,.csv,.log,.json" hidden @change="uploadFiles" />
      <button v-if="isLoggedIn" class="btn-ghost" :disabled="!picked.length" @click="openBatch">
        批量{{ picked.length ? `(${picked.length})` : '' }}
      </button>
      <button v-if="isLoggedIn" class="btn-ghost" :disabled="!docs.length" @click="openMindmap()">导图</button>
      <button class="btn-dark" :disabled="busy" @click="fileInput?.click()">
        <AppIcon name="upload" :size="14" />
        导入
      </button>
    </header>

    <div class="page-body sc-scroll">
      <div class="page-inner bento">
        <div class="stats col-12">
          <div class="stat"><b>{{ stats.chunks }}</b><span>分块</span></div>
          <div class="stat"><b>{{ docs.length }}</b><span>文档</span></div>
          <div class="stat"><b>{{ stats.dim }}</b><span>向量维度</span></div>
        </div>

        <button class="card drop col-12" :disabled="busy" @click="fileInput?.click()">
          <AppIcon name="upload" :size="18" />
          <span>{{ busy ? '正在切块建索引…' : '点这里选文件，可以多选' }}</span>
          <em>txt / md / csv / log / json，切段后写入本地向量库</em>
        </button>

        <div class="card col-5">
          <div class="card-head">
            <span class="card-title">粘贴一段文字</span>
            <span class="card-hint">适合周报、会议记录</span>
          </div>
          <div class="card-body">
            <el-input v-model="source" size="small" placeholder="来源名称，如：项目周报" class="mb10" />
            <el-input v-model="text" type="textarea" :rows="4" resize="none" placeholder="粘贴需要以后被检索到的内容" />
            <div class="card-actions">
              <el-button size="small" type="primary" :loading="busy" @click="addText">保存</el-button>
            </div>
          </div>
        </div>

        <div class="card col-7">
          <div class="card-head">
            <span class="card-title">已入库</span>
            <span class="card-hint">{{ docs.length }} 份</span>
          </div>
          <div class="card-body doc-list">
            <div v-for="d in docs" :key="d.doc_id" class="doc-row">
              <el-checkbox
                v-if="isLoggedIn"
                :model-value="picked.includes(d.doc_id)"
                class="doc-pick"
                @change="togglePick(d.doc_id)"
              />
              <div class="doc-main">
                <span class="doc-name" :title="d.source">{{ d.source }}</span>
                <span class="doc-meta">{{ d.chunks }} 段 · {{ d.workspace }}</span>
              </div>
              <button v-if="isLoggedIn" class="mem-del" title="生成导图" @click="openMindmap(d.doc_id)">
                <AppIcon name="mindmap" :size="13" />
              </button>
              <button class="mem-del" title="删除" @click="remove(d)">
                <AppIcon name="trash" :size="13" />
              </button>
            </div>
            <p v-if="!docs.length" class="empty">还没有资料，先导入一份</p>
          </div>
        </div>
      </div>
    </div>

    <el-dialog v-model="mmOpen" title="思维导图" width="360px" append-to-body>
      <el-select v-model="mmDoc" size="small" placeholder="选一份资料" style="width: 100%">
        <el-option v-for="d in docs" :key="d.doc_id" :label="d.source" :value="d.doc_id" />
      </el-select>
      <pre v-if="mmResult" class="mm-preview">{{ mmResult.markdown }}</pre>
      <p v-else class="muted-line" style="margin: 12px 0 0">
        选好资料点生成，模型会把内容提炼成 markdown 大纲，节点太多会自动截断。
      </p>
      <div class="mm-foot">
        <el-button size="small" :loading="mmBusy" @click="genMindmap">
          {{ mmResult ? '换一版' : '生成' }}
        </el-button>
        <el-button v-if="mmResult" size="small" type="primary" @click="exportMindmap">
          导出 Markdown
        </el-button>
      </div>
    </el-dialog>

    <el-dialog v-model="batchOpen" title="批量处理" width="620px" append-to-body>
      <div class="batch-top">
        <el-radio-group v-model="batchAction" size="small">
          <el-radio-button value="summary">摘要</el-radio-button>
          <el-radio-button value="translate">翻译</el-radio-button>
          <el-radio-button value="table">抽表格</el-radio-button>
        </el-radio-group>
        <el-input v-if="batchAction === 'translate'" v-model="batchLang" size="small" style="width: 110px" />
        <span class="card-hint">已选 {{ picked.length }} 份</span>
      </div>

      <div v-if="batchRes.length" class="batch-res sc-scroll">
        <article v-for="(r, i) in batchRes" :key="i" class="batch-item">
          <header>
            <b>{{ r.source }}</b>
            <em :class="{ bad: !r.ok }">{{ r.ok ? '完成' : '失败' }}</em>
          </header>
          <pre>{{ r.text }}</pre>
        </article>
      </div>
      <p v-else class="muted-line" style="margin: 12px 0 0">
        一次最多 10 份，串行跑，慢是慢点但不容易被上游限流。
      </p>

      <template #footer>
        <el-button v-if="batchAction === 'table' && batchCsv" size="small" @click="saveCsv">存成 CSV</el-button>
        <el-button v-if="batchRes.length" size="small" @click="copyAll">复制全部</el-button>
        <el-button size="small" type="primary" :loading="batchBusy" @click="runBatch">开始</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped src="../styles/views.css"></style>
<style scoped>
.doc-pick {
  margin-right: 8px;
  height: auto;
}
.batch-top {
  display: flex;
  align-items: center;
  gap: 10px;
}
.batch-res {
  max-height: 340px;
  margin-top: 12px;
}
.batch-item {
  padding: 9px 0;
  border-bottom: 1px solid var(--sc-line);
}
.batch-item:last-child {
  border-bottom: 0;
}
.batch-item header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 4px;
}
.batch-item b {
  font-size: 12px;
  font-weight: 600;
}
.batch-item em {
  font-style: normal;
  font-size: 10.5px;
  color: #2e7d5b;
}
.batch-item em.bad {
  color: var(--sc-danger);
}
.batch-item pre {
  margin: 0;
  font-family: inherit;
  font-size: 12px;
  line-height: 1.8;
  color: var(--sc-text-2);
  white-space: pre-wrap;
  word-break: break-word;
  user-select: text;
}
</style>
