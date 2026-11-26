<script setup lang="ts">
const props = withDefaults(defineProps<{ name: string; size?: number; stroke?: number }>(), {
  size: 16,
  stroke: 1.6,
})

const ICONS: Record<string, string> = {
  chat: 'M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v7a2.5 2.5 0 0 1-2.5 2.5H9.5L5 19.5V16H6.5A2.5 2.5 0 0 1 4 13.5v-7Z',
  knowledge: 'M4 6a2 2 0 0 1 2-2h3.6l1.9 2.4H18a2 2 0 0 1 2 2v9.6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6Z',
  tasks: 'M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17ZM12 7.5V12l3.2 2',
  clock: 'M12 3.8a8.2 8.2 0 1 0 0 16.4 8.2 8.2 0 0 0 0-16.4ZM12 7.8V12l3 1.6',
  settings: 'M4 7.5h7M15 7.5h5M4 16.5h5M13 16.5h7M13 5.5v4M11 14.5v4',
  send: 'M12 19.5V4.5M6.5 10 12 4.5 17.5 10',
  plus: 'M12 5v14M5 12h14',
  trash: 'M4.5 7h15M9.5 7V4.5h5V7M6.5 7l.8 12.5h9.4L17.5 7M10.5 10.5v6M13.5 10.5v6',
  upload: 'M12 16.5V4.5M7.5 9 12 4.5 16.5 9M4.5 20h15',
  spark: 'M12 3.5l1.7 4.8 4.8 1.7-4.8 1.7L12 16.5l-1.7-4.8L5.5 10l4.8-1.7L12 3.5Z',
  check: 'M5 12.5 9.5 17 19 7',
  dot: 'M12 12h.01',
  memory: 'M6 4.5h11.5v15l-5.75-3.6-5.75 3.6v-15Z',
  usage: 'M5.5 19.5v-6M12 19.5v-11M18.5 19.5v-4',
  chevron: 'M8 10.5 12 14.5 16 10.5',
  minimize: 'M6 12h12',
  close: 'M6.5 6.5l11 11M17.5 6.5l-11 11',
  refresh: 'M19 12a7 7 0 1 1-2.2-5.1M19.5 4.5V8H16',
  mindmap: 'M12 4.5v3M12 7.5 5.5 11v2M12 7.5l6.5 3.5v2M5.5 13v4M18.5 13v4M12 7.5v9M3.5 17h4v3h-4zM16.5 17h4v3h-4zM10 16.5h4v3h-4z',
  shield: 'M12 3.5 5.5 6v6.1c0 4 2.8 6.9 6.5 8.4 3.7-1.5 6.5-4.4 6.5-8.4V6L12 3.5Z',
  mic: 'M12 4.5a2.5 2.5 0 0 1 2.5 2.5v4.5a2.5 2.5 0 0 1-5 0V7A2.5 2.5 0 0 1 12 4.5ZM6.5 11a5.5 5.5 0 0 0 11 0M12 16.5V20',
  sound: 'M5 9.5h3l4-3.5v12l-4-3.5H5zM15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11',
  image: 'M4.5 6.5a2 2 0 0 1 2-2h11a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2h-11a2 2 0 0 1-2-2v-11ZM4.5 15.5 9 11l4 4 2.5-2.5 4 4M15 9.5h.01',
  note: 'M6 4.5h8.5L19 9v10.5H6V4.5ZM14 4.5V9h5M9 13h7M9 16.5h5',
  todo: 'M4.5 6.5h15v13h-15zM8 12.2l2.4 2.4L16 9',
  help: 'M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17ZM9.6 9.4a2.5 2.5 0 1 1 3.4 2.3c-.6.3-1 .8-1 1.5v.5M12 16.6h.01',
  download: 'M12 4.5V16M7.5 11.5 12 16l4.5-4.5M4.5 19.5h15',
  search: 'M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13ZM15.5 15.5 20 20',
  book: 'M4.5 5.5A2 2 0 0 1 6.5 3.5H19v14H6.5a2 2 0 0 0-2 2v-14ZM4.5 17.5v3h12',
  key: 'M15.5 4.5a4 4 0 1 0 1.4 7.7L20 15v2h-2v2h-2l-3.4-3.4a4 4 0 0 1-.7-4.3',
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
