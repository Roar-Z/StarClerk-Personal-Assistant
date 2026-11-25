<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, download, type MigrateInfo } from '../api'

const info = ref<MigrateInfo | null>(null)
const busy = ref(false)
const result = ref('')

async function load() {
  info.value = await api.migrateInfo()
}

function size(n: number) {
  if (n > 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + ' MB'
  return (n / 1024).toFixed(0) + ' KB'
}

function doExport() {
  download('/migrate/export')
  ElMessage.success('包已经在下载了，去下载目录看')
}

async function pickFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  await ElMessageBox.confirm(
    '导入会覆盖现在的会话、笔记、记忆和任务，旧的库会先备份一份。确定继续？',
    '导入迁移包',
    { type: 'warning', confirmButtonText: '导入' },
  )
  busy.value = true
  try {
    const r = await api.importPack(file)
    result.value = r.msg
    ElMessage.success('导入完成，重启程序后生效')
    await load()
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page migrate">
    <header class="page-head">
      <div>
        <h1>数据迁移</h1>
        <p>换电脑时把资料搬过去，导出的包里有数据库和授权文件。</p>
      </div>
    </header>

    <div class="cards">
      <section class="card">
        <div class="card-head">
          <span class="card-title">现在装了些什么</span>
          <span class="card-hint">{{ info?.tier }}</span>
        </div>
        <div class="card-body">
          <div class="nums">
            <div><b>{{ info?.counts.sessions || 0 }}</b><span>会话</span></div>
            <div><b>{{ info?.counts.notes || 0 }}</b><span>笔记</span></div>
            <div><b>{{ info?.counts.skills || 0 }}</b><span>模板</span></div>
            <div><b>{{ info?.counts.memories || 0 }}</b><span>记忆</span></div>
            <div><b>{{ info?.counts.tasks || 0 }}</b><span>任务</span></div>
          </div>
          <p class="path">数据库 {{ info?.db }}（{{ size(info?.size || 0) }}）</p>
        </div>
      </section>

      <section class="card">
        <div class="card-head">
          <span class="card-title">导出</span>
          <span class="card-hint">打包成一个 zip</span>
        </div>
        <div class="card-body">
          <p class="desc">
            会话、笔记、模板、记忆、任务配置都在库里，一起打进去。
            上传的原始文档和向量索引太大，没往里塞，换机时直接拷 data 目录更省事。
          </p>
          <button class="btn primary" @click="doExport">导出迁移包</button>
        </div>
      </section>

      <section class="card">
        <div class="card-head">
          <span class="card-title">导入</span>
          <span class="card-hint">会覆盖现有数据</span>
        </div>
        <div class="card-body">
          <p class="desc">
            选之前导出的 zip。导入前会把当前库复制到 data/backup，
            导错了还能从那儿捞回来。导入完成后要重启程序。
          </p>
          <label class="btn" :class="{ busy }">
            {{ busy ? '导入中…' : '选择迁移包' }}
            <input type="file" accept=".zip" hidden :disabled="busy" @change="pickFile" />
          </label>
          <p v-if="result" class="ok">{{ result }}</p>
        </div>
      </section>

      <section class="card">
        <div class="card-head">
          <span class="card-title">备份</span>
          <span class="card-hint">最近的 5 个</span>
        </div>
        <div class="card-body">
          <ul v-if="info?.backups.length" class="backs">
            <li v-for="b in info.backups" :key="b">{{ b }}</li>
          </ul>
          <p v-else class="desc">还没有备份。第一次导入或者导出后会出现在这里。</p>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.migrate {
  padding: 18px 20px 24px;
  overflow-y: auto;
}
.cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 12px;
}
.card {
  background: var(--sc-surface);
  border: 1px solid var(--sc-line);
  border-radius: 8px;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 13px;
  border-bottom: 1px solid var(--sc-line);
}
.card-title {
  font-size: 12.5px;
  font-weight: 600;
}
.card-hint {
  font-size: 11px;
  color: var(--sc-muted);
}
.card-body {
  padding: 12px 13px 13px;
}
.nums {
  display: flex;
  gap: 18px;
}
.nums div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.nums b {
  font-size: 18px;
  font-weight: 600;
  line-height: 1.1;
}
.nums span {
  font-size: 11px;
  color: var(--sc-muted);
}
.path {
  margin: 10px 0 0;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 10.5px;
  color: var(--sc-muted);
  word-break: break-all;
}
.desc {
  margin: 0 0 10px;
  font-size: 12px;
  line-height: 1.8;
  color: var(--sc-muted);
}
.backs {
  margin: 0;
  padding: 0;
  list-style: none;
}
.backs li {
  padding: 4px 0;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 11px;
  color: var(--sc-muted);
  border-bottom: 1px dashed var(--sc-line);
}
.busy {
  opacity: 0.6;
  pointer-events: none;
}
.ok {
  margin: 8px 0 0;
  font-size: 11.5px;
  color: #2e7d5b;
}
</style>
