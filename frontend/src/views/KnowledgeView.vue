<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import AppIcon from '../components/AppIcon.vue'
import { api } from '../api'

const stats = ref({ chunks: 0, memories: 0, dim: 0 })
const memories = ref<{ id: string; content: string }[]>([])
const text = ref('')
const source = ref('粘贴文本')
const busy = ref(false)
const fileInput = ref<HTMLInputElement>()

async function refresh() {
  const [s, m] = await Promise.all([api.stats(), api.memories()])
  stats.value = s
  memories.value = m
}
async function uploadFiles(e: Event) {
  const files = (e.target as HTMLInputElement).files
  if (!files?.length) return
  busy.value = true
  try {
    for (const f of Array.from(files)) {
      const r = await api.upload(f)
      ElMessage.success(`${r.source} · ${r.chunks} 段`)
    }
    await refresh()
  } catch (err: any) {
    ElMessage.error(err.message)
  } finally {
    busy.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}
async function addText() {
  if (text.value.trim().length < 10) return ElMessage.warning('内容太短，至少 10 个字')
  busy.value = true
  try {
    const r: any = await api.addText(text.value, source.value)
    ElMessage.success(`已索引 ${r.chunks} 段`)
    text.value = ''
    await refresh()
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    busy.value = false
  }
}
async function delMemory(id: string) {
  await api.delMemory(id)
  await refresh()
}
onMounted(refresh)
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div class="page-head-left">
        <span class="page-title">知识库与记忆</span>
        <span class="page-sub">本地私有 · 不上传云端</span>
      </div>
      <input ref="fileInput" type="file" multiple accept=".txt,.md,.csv,.log,.json" hidden @change="uploadFiles" />
      <button class="btn-dark" :disabled="busy" @click="fileInput?.click()">
        <AppIcon name="upload" :size="14" />导入文件
      </button>
    </header>

    <div class="page-body sc-scroll">
      <div class="page-inner">
        <div class="stats">
          <div class="stat"><b>{{ stats.chunks }}</b><span>已索引片段</span></div>
          <div class="stat"><b>{{ stats.memories }}</b><span>长期记忆</span></div>
          <div class="stat"><b>{{ stats.dim }}</b><span>向量维度</span></div>
        </div>

        <div class="grid-2">
          <section class="card fill">
            <div class="card-head">
              <span class="card-title">导入资料</span>
              <span class="card-hint">txt · md · csv · log · json</span>
            </div>
            <div class="card-body">
              <button class="drop" :disabled="busy" @click="fileInput?.click()">
                <AppIcon name="upload" :size="18" />
                <span>{{ busy ? '正在建立索引…' : '点击选择文件，支持多选' }}</span>
                <em>按段落切块后写入本地向量库</em>
              </button>
            </div>
          </section>

          <section class="card">
            <div class="card-head"><span class="card-title">粘贴文本</span></div>
            <div class="card-body">
              <el-input v-model="source" size="small" placeholder="来源名称，如：项目周报" class="mb10" />
              <el-input v-model="text" type="textarea" :rows="4" resize="none" placeholder="粘贴需要长期检索的内容" />
              <div class="card-actions">
                <el-button size="small" type="primary" :loading="busy" @click="addText">入库</el-button>
              </div>
            </div>
          </section>
        </div>

        <section class="card mt16">
          <div class="card-head">
            <span class="card-title">长期记忆</span>
            <span class="card-hint">对话中自动沉淀，可手动删除</span>
          </div>
          <div class="card-body mem-body">
            <div v-if="!memories.length" class="muted-line">还没有记忆。聊几句，我会自己记住重要的事。</div>
            <div v-for="m in memories" :key="m.id" class="mem">
              <span class="mem-text">{{ m.content }}</span>
              <button class="mem-del" title="删除" @click="delMemory(m.id)">
                <AppIcon name="trash" :size="13" />
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped src="../styles/views.css"></style>
