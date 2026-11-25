<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'

const md = ref('')
const title = ref('使用说明')
const version = ref('')
const checking = ref(false)
const update = ref<{ current: string; latest: string; has_new: boolean; file: string; folder: string; checked_at: string } | null>(null)

// 不引 markdown 库，按行粗处理一下就够看：标题、列表、行内代码、加粗
type Block = { kind: 'h' | 'p' | 'li' | 'ol'; text: string }

const blocks = computed<Block[]>(() => {
  const out: Block[] = []
  for (const raw of md.value.split('\n')) {
    const line = raw.trimEnd()
    if (!line.trim()) continue
    if (line.startsWith('## ')) out.push({ kind: 'h', text: line.slice(3) })
    else if (/^\d+\.\s/.test(line)) out.push({ kind: 'ol', text: line.replace(/^\d+\.\s/, '') })
    else if (line.startsWith('- ')) out.push({ kind: 'li', text: line.slice(2) })
    else out.push({ kind: 'p', text: line })
  }
  return out
})

const toc = computed(() => blocks.value.filter((b) => b.kind === 'h').map((b) => b.text))

function inline(s: string) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
}

async function load() {
  const r = await api.help()
  md.value = r.markdown
  title.value = r.title
  version.value = r.version
}

async function check() {
  checking.value = true
  try {
    update.value = await api.checkUpdate()
    if (update.value.has_new) ElMessage.success(`发现 ${update.value.latest}`)
    else ElMessage.info('已经是最新的了')
  } finally {
    checking.value = false
  }
}

/** 主界面那个引导卡片画在 App 里，这里只负责喊一声 */
function replay() {
  window.dispatchEvent(new Event('sc:guide'))
}

function jump(t: string) {
  const el = [...document.querySelectorAll('.doc h2')].find((n) => n.textContent?.includes(t))
  el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

onMounted(load)
</script>

<template>
  <div class="page help">
    <header class="page-head">
      <div>
        <h1>{{ title }}</h1>
        <p>当前版本 {{ version }}，常见问题都写在这，不用去翻群里。</p>
      </div>
      <div class="head-actions">
        <button class="btn ghost" @click="replay">再看一遍引导</button>
        <button class="btn ghost" :disabled="checking" @click="check">
          {{ checking ? '检查中…' : '检查更新' }}
        </button>
      </div>
    </header>

    <div v-if="update" class="update-bar" :class="{ fresh: update.has_new }">
      <span>
        当前 {{ update.current }}，本地最高 {{ update.latest }}（{{ update.checked_at }} 查的）
      </span>
      <span v-if="update.has_new" class="up-file">{{ update.file }}</span>
      <span v-else class="up-idle">没找到更新的安装包，想升级就把新包放到 {{ update.folder }}</span>
    </div>

    <div class="wrap">
      <aside class="toc">
        <p class="toc-cap">目录</p>
        <button v-for="t in toc" :key="t" @click="jump(t)">{{ t }}</button>
      </aside>
      <article class="doc">
        <template v-for="(b, i) in blocks" :key="i">
          <h2 v-if="b.kind === 'h'">{{ b.text }}</h2>
          <ol v-else-if="b.kind === 'ol'" class="num">
            <li v-html="inline(b.text)" />
          </ol>
          <p v-else-if="b.kind === 'li'" class="li" v-html="'· ' + inline(b.text)" />
          <p v-else v-html="inline(b.text)" />
        </template>
      </article>
    </div>
  </div>
</template>

<style scoped>
.help {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 18px 20px 0;
}
.update-bar {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 7px 10px;
  margin: 12px 0 0;
  font-size: 11.5px;
  color: var(--sc-muted);
  background: rgba(21, 27, 38, 0.045);
  border: 1px solid var(--sc-line);
  border-radius: 6px;
}
.update-bar.fresh {
  color: var(--sc-accent);
  background: rgba(58, 86, 212, 0.07);
  border-color: rgba(58, 86, 212, 0.28);
}
.up-file {
  margin-left: auto;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 11px;
}
.up-idle {
  margin-left: auto;
  color: var(--sc-muted);
}
.wrap {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 170px 1fr;
  gap: 14px;
  padding: 12px 0 16px;
}
.toc {
  padding: 8px 0;
  border-right: 1px solid var(--sc-line);
}
.toc-cap {
  padding: 0 10px 6px;
  font-size: 10.5px;
  letter-spacing: 0.08em;
  color: var(--sc-muted);
}
.toc button {
  display: block;
  width: 100%;
  padding: 5px 10px;
  text-align: left;
  font-size: 12px;
  color: var(--sc-text-2);
  background: transparent;
  border: 0;
  border-left: 2px solid transparent;
  cursor: pointer;
}
.toc button:hover {
  color: var(--sc-accent);
  background: rgba(21, 27, 38, 0.045);
  border-left-color: var(--sc-accent);
}
.doc {
  overflow-y: auto;
  padding-right: 8px;
}
.doc h2 {
  margin: 16px 0 8px;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--sc-text);
  scroll-margin-top: 8px;
}
.doc h2:first-child {
  margin-top: 0;
}
.doc p {
  margin: 0 0 6px;
  font-size: 12.5px;
  line-height: 1.9;
  color: var(--sc-text-2);
}
.doc .li {
  padding-left: 12px;
  color: var(--sc-muted);
}
.doc .num {
  margin: 0 0 8px;
  padding-left: 18px;
  font-size: 12.5px;
  line-height: 1.9;
  color: var(--sc-text-2);
}
.doc :deep(code) {
  padding: 1px 4px;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 11.5px;
  color: var(--sc-text);
  background: rgba(21, 27, 38, 0.045);
  border-radius: 3px;
}
</style>
