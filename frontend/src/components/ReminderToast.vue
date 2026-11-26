<script setup lang="ts">
import { onUnmounted, watch } from 'vue'
import AppIcon from './AppIcon.vue'

export interface ReminderItem {
  event_id: string
  todo_id: string
  stage: number
  title: string
  body: string
  level: string
  due_at: number
}

const props = defineProps<{ items: ReminderItem[] }>()
const emit = defineEmits<{ (e: 'ack', item: ReminderItem): void; (e: 'close', item: ReminderItem): void }>()

// 没人点就十分钟自动收掉，关掉的动作照旧发给后端，不影响下一档提醒
const timers = new Map<string, number>()
watch(
  () => props.items,
  (list) => {
    const ids = new Set(list.map((x) => x.event_id))
    for (const [id, timer] of timers) {
      if (!ids.has(id)) {
        clearTimeout(timer)
        timers.delete(id)
      }
    }
    for (const item of list) {
      if (timers.has(item.event_id)) continue
      const timer = window.setTimeout(() => emit('close', item), 10 * 60 * 1000)
      timers.set(item.event_id, timer)
    }
  },
  { immediate: true, deep: true },
)
onUnmounted(() => {
  for (const timer of timers.values()) clearTimeout(timer)
  timers.clear()
})
</script>

<template>
  <div class="reminder-stack" role="status" aria-live="polite">
    <div v-for="item in items" :key="item.event_id" class="reminder-card" :class="item.level">
      <span class="bar" />
      <div class="head">
        <span class="icon"><AppIcon name="clock" :size="13" /></span>
        <b>{{ item.title }}</b>
        <span class="stage">{{ item.stage }}/3</span>
      </div>
      <p class="body">{{ item.body }}</p>
      <div class="acts">
        <button class="ack" @click="emit('ack', item)">
          <AppIcon name="check" :size="12" />
          已确认
        </button>
        <button class="close" @click="emit('close', item)">
          <AppIcon name="close" :size="11" />
          关闭
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.reminder-stack {
  position: fixed;
  right: 16px;
  bottom: 16px;
  z-index: 35;
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 330px;
  pointer-events: none;
}
.reminder-card {
  position: relative;
  padding: 11px 12px 10px 14px;
  overflow: hidden;
  pointer-events: auto;
  background: var(--sc-surface);
  border: 1px solid var(--sc-line-strong);
  border-radius: 10px;
  box-shadow: var(--sc-shadow-sm);
}
.bar {
  position: absolute;
  top: 0;
  left: 0;
  width: 3px;
  height: 100%;
  background: var(--sc-accent);
}
.reminder-card.warn .bar {
  background: #c98242;
}
.reminder-card.urgent .bar {
  background: var(--sc-danger);
}
.head {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12.5px;
}
.head b {
  font-weight: 600;
}
.icon {
  display: grid;
  place-items: center;
  color: var(--sc-accent);
}
.warn .icon {
  color: #c98242;
}
.urgent .icon {
  color: var(--sc-danger);
}
.stage {
  margin-left: auto;
  font-size: 10.5px;
  color: var(--sc-muted);
}
.body {
  margin: 7px 0 10px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--sc-text-2);
  word-break: break-all;
}
.acts {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
}
.acts button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 9px;
  font-size: 11px;
  border: 1px solid var(--sc-line);
  border-radius: 6px;
  background: var(--sc-surface);
  color: var(--sc-text-2);
  cursor: pointer;
}
.acts button:hover {
  border-color: var(--sc-line-strong);
  color: var(--sc-text);
}
.acts .ack {
  color: #fff;
  background: var(--sc-text);
  border-color: var(--sc-text);
}
.acts .ack:hover {
  opacity: 0.88;
  color: #fff;
}
</style>
