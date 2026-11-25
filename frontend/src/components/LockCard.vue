<script setup lang="ts">
/**
 * 锁住的页面：未登录点任务/资料/记忆/用量就显示这个。
 * 不做双份界面，说明一下怎么登录就够了。
 */
defineProps<{
  title: string
  desc: string
  need: 'free'
  points?: string[]
}>()

const emit = defineEmits<{ (e: 'go'): void }>()
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div class="page-head-left">
        <span class="page-title">{{ title }}</span>
        <span class="page-sub">当前未登录</span>
      </div>
    </header>

    <div class="page-body sc-scroll">
      <div class="page-inner">
        <div class="lock-card">
          <div class="lock-mark">
            <span class="lock-body" />
            <span class="lock-hook" />
          </div>
          <p class="lock-title">登录后可用</p>
          <p class="lock-desc">{{ desc }}</p>
          <ul v-if="points?.length" class="lock-list">
            <li v-for="p in points" :key="p">{{ p }}</li>
          </ul>
          <button class="btn-dark" @click="emit('go')">去登录</button>
          <p class="lock-note">本机登录，不用账号密码，也不联网</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped src="../styles/views.css"></style>
