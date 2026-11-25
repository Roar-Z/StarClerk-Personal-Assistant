<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import AppIcon from '../components/AppIcon.vue'
import { api, download, type DocMeta, type MindMap, type WorkSpace } from '../api'
import { isPro, me } from '../store'

const stats = ref({ chunks: 0, memories: 0, dim: 0 })
const docs = ref<DocMeta[]>([])
const text = ref('')
const source = ref('')
const busy = ref(false)
const fileInput = ref<HTMLInputElement>()

// 工作区是 Pro 才有的入口，免费版一直用 default
const workspaces = ref<WorkSpace[]>([])
const ws = ref('')

const mmOpen = ref(false)
const mmBusy = ref(false)
const mmDoc = ref('')
const mmResult = ref<MindMap | null>(null)

async function refresh() {
  try {
    const [s, d] = await Promise.all([api.stats(), api.documents(ws.value)])
    stats.value = s
    docs.value = d
    if (isPro.value) workspaces.value = (await api.workspaces()).items
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
      ElMessage.success(`${r.source} 已切 ${r.chunks} 段`)
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
        v-if="isPro && workspaces.length > 1"
        v-model="ws"
        size="small"
        style="width: 104px"
        @change="refresh"
      >
        <el-option v-for="w in workspaces" :key="w.name" :label="`${w.name} ${w.docs}`" :value="w.name" />
      </el-select>
      <input ref="fileInput" type="file" multiple accept=".txt,.md,.csv,.log,.json" hidden @change="uploadFiles" />
      <button v-if="isPro" class="btn-ghost" :disabled="!docs.length" @click="openMindmap()">导图</button>
      <button class="btn-dark" :disabled="busy" @click="fileInput?.click()">
        <AppIcon name="upload" :size="14" />
        导入
      </button>
    </header>

    <div class="page-body sc-scroll">
      <div class="page-inner stack">
        <div class="stats">
          <div class="stat"><b>{{ stats.chunks }}</b><span>分块</span></div>
          <div class="stat"><b>{{ docs.length }}</b><span>文档</span></div>
          <div class="stat"><b>{{ stats.dim }}</b><span>向量维度</span></div>
        </div>

        <button class="card drop" :disabled="busy" @click="fileInput?.click()">
          <AppIcon name="upload" :size="18" />
          <span>{{ busy ? '正在切块建索引…' : '点这里选文件，可以多选' }}</span>
          <em>txt / md / csv / log / json，切段后写入本地向量库</em>
        </button>

        <div class="card">
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

        <div class="card">
          <div class="card-head">
            <span class="card-title">已入库</span>
            <span class="card-hint">{{ docs.length }} 份</span>
          </div>
          <div class="card-body doc-list">
            <div v-for="d in docs" :key="d.doc_id" class="doc-row">
              <div class="doc-main">
                <span class="doc-name" :title="d.source">{{ d.source }}</span>
                <span class="doc-meta">{{ d.chunks }} 段 · {{ d.workspace }}</span>
              </div>
              <button v-if="isPro" class="mem-del" title="生成导图" @click="openMindmap(d.doc_id)">
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
  </div>
</template>

<style scoped src="../styles/views.css"></style>
