<script setup lang="ts">
import { onUnmounted, ref } from 'vue'
import AppIcon from './AppIcon.vue'
import { isDesktop, win } from '../desktop'

const desktop = isDesktop()
const dragging = ref(false)
let baseX = 0
let baseY = 0

function onDown(e: MouseEvent) {
  if (!desktop || e.button !== 0) return
  dragging.value = true
  baseX = e.screenX
  baseY = e.screenY
  win.begin()
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

function onMove(e: MouseEvent) {
  if (!dragging.value) return
  win.follow(e.screenX, e.screenY, baseX, baseY)
}

function onUp() {
  dragging.value = false
  window.removeEventListener('mousemove', onMove)
  window.removeEventListener('mouseup', onUp)
}

onUnmounted(onUp)
</script>

<template>
  <header class="titlebar" :class="{ dragging }" @mousedown="onDown">
    <span class="dot" />
    <span class="name">StarClerk</span>
    <span class="tag">本地版</span>

    <div v-if="desktop" class="win-ops" @mousedown.stop>
      <button class="win-btn" title="最小化" @click="win.minimize()"><AppIcon name="minimize" :size="14" /></button>
      <button class="win-btn" title="收进托盘" @click="win.hide()"><AppIcon name="close" :size="13" /></button>
    </div>
  </header>
</template>
