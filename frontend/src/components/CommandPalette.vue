<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'run', key: string, text?: string): void }>()

const q = ref('')
const inputEl = ref<HTMLInputElement>()

const COMMANDS = [
  { key: 'mic', label: '语音输入', hint: '开始听我说话', icon: 'mic' },
  { key: 'ocr', label: '拍照识字', hint: '本地 OCR，不联网', icon: 'image' },
  { key: 'todo', label: '新建待办', hint: '一句话记一件事', icon: 'todo' },
  { key: 'todos', label: '打开待办清单', hint: '看看今天要做什么', icon: 'check' },
  { key: 'scan', label: '快递单 / 小票', hint: '拆取件码、消费记录', icon: 'knowledge' },
  { key: 'mindmap', label: '生成思维导图', hint: '把上一段回答整理成导图', icon: 'mindmap' },
]
const shown = computed(() => {
  const s = q.value.trim().toLowerCase()
  return s ? COMMANDS.filter((c) => c.label.toLowerCase().includes(s) || c.hint.includes(s)) : COMMANDS
})

watch(
  () => props.open,
  (v) => {
    if (v) {
      q.value = ''
      nextTick(() => inputEl.value?.focus())
    }
  },
)

function run(key: string) {
  emit('run', key)
  emit('close')
}
function send() {
  const text = q.value.trim()
  if (!text) return
  emit('run', 'send', text)
  emit('close')
}
</script>

<template>
  <div v-if="open" class="mask" @mousedown.self="emit('close')">
    <div class="palette">
      <div class="search">
        <AppIcon name="spark" :size="15" />
        <input
          ref="inputEl"
          v-model="q"
          placeholder="输一句话直接问，或者选个动作"
          @keydown.enter="send"
          @keydown.esc="emit('close')"
        />
        <kbd>Esc</kbd>
      </div>
      <p class="cap">快捷指令</p>
      <div class="list">
        <button v-for="c in shown" :key="c.key" @click="run(c.key)">
          <span class="ico"><AppIcon :name="c.icon" :size="15" /></span>
          <span class="txt"><b>{{ c.label }}</b><small>{{ c.hint }}</small></span>
          <AppIcon name="chevron" :size="12" />
        </button>
        <p v-if="!shown.length" class="none">没找到这个动作，直接回车当问题问吧</p>
      </div>
      <p class="foot">Ctrl + Alt + Space 随时唤起</p>
    </div>
  </div>
</template>

<style scoped>
.mask { position: fixed; inset: 0; z-index: 40; display: flex; justify-content: center; align-items: flex-start; background: rgba(17, 22, 31, 0.26); }
.palette { width: 520px; margin-top: 13vh; background: var(--sc-surface); border: 1px solid var(--sc-line-strong); border-radius: 12px; box-shadow: 0 20px 60px rgba(17, 22, 31, 0.16); overflow: hidden; }
.search { display: flex; align-items: center; gap: 9px; padding: 12px 14px; border-bottom: 1px solid var(--sc-line); color: var(--sc-muted); }
.search input { flex: 1; min-width: 0; border: 0; outline: none; font-size: 13px; color: var(--sc-text); background: transparent; }
.search input::placeholder { color: var(--sc-muted); }
kbd { padding: 2px 5px; font-size: 10px; font-family: inherit; color: var(--sc-muted); border: 1px solid var(--sc-line); border-radius: 4px; }
.cap { margin: 10px 14px 4px; font-size: 10.5px; letter-spacing: 0.06em; color: var(--sc-muted); }
.list { max-height: 320px; overflow-y: auto; padding: 0 8px 8px; }
.list button { display: flex; align-items: center; gap: 10px; width: 100%; padding: 8px; text-align: left; border: 0; border-radius: 7px; background: transparent; cursor: pointer; color: var(--sc-muted); }
.list button:hover { background: rgba(58, 86, 212, 0.06); color: var(--sc-accent); }
.ico { display: grid; place-items: center; width: 28px; height: 28px; border: 1px solid var(--sc-line); border-radius: 7px; color: var(--sc-text-2); }
.txt { flex: 1; }
.txt b { display: block; font-size: 12.5px; font-weight: 600; color: var(--sc-text); }
.txt small { font-size: 11px; color: var(--sc-muted); }
.none { padding: 12px; font-size: 12px; color: var(--sc-muted); }
.foot { margin: 0; padding: 8px 14px; font-size: 10.5px; color: var(--sc-muted); border-top: 1px solid var(--sc-line); }
</style>
