<script setup lang="ts">
const props = withDefaults(defineProps<{ name: string; size?: number; stroke?: number }>(), {
  size: 16,
  stroke: 1.6,
})

const ICONS: Record<string, string> = {
  chat: 'M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v7a2.5 2.5 0 0 1-2.5 2.5H9.5L5 19.5V16H6.5A2.5 2.5 0 0 1 4 13.5v-7Z',
  knowledge: 'M4 6a2 2 0 0 1 2-2h3.6l1.9 2.4H18a2 2 0 0 1 2 2v9.6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6Z',
  tasks: 'M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17ZM12 7.5V12l3.2 2',
  settings: 'M4 7.5h7M15 7.5h5M4 16.5h5M13 16.5h7M13 5.5v4M11 14.5v4',
  send: 'M12 19.5V4.5M6.5 10 12 4.5 17.5 10',
  plus: 'M12 5v14M5 12h14',
  trash: 'M4.5 7h15M9.5 7V4.5h5V7M6.5 7l.8 12.5h9.4L17.5 7M10.5 10.5v6M13.5 10.5v6',
  upload: 'M12 16.5V4.5M7.5 9 12 4.5 16.5 9M4.5 20h15',
  spark: 'M12 3.5l1.7 4.8 4.8 1.7-4.8 1.7L12 16.5l-1.7-4.8L5.5 10l4.8-1.7L12 3.5Z',
  check: 'M5 12.5 9.5 17 19 7',
  dot: 'M12 12h.01',
}
</script>

<template>
  <svg
    :width="props.size"
    :height="props.size"
    viewBox="0 0 24 24"
    fill="none"
    :stroke-width="props.stroke"
    stroke="currentColor"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="ICONS[props.name] || ''" />
  </svg>
</template>
