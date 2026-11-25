<script setup lang="ts">
import { onMounted, ref } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import { api, type Memory } from '../api'

const list = ref<Memory[]>([])
const text = ref('')
const busy = ref(false)

async function load() {
  try {
    list.value = await api.memories()
  } catch {
    list.value = []
  }
}

async function add() {
  const content = text.value.trim()
  if (!content || busy.value) return
  busy.value = true
  try {
    await api.addMemory(content)
    text.value = ''
    await load()
  } catch {
    /* 提示已由 api 层弹出，输入保留方便再试 */
  } finally {
    busy.value = false
  }
}

async function remove(id: string) {
  try {
    await api.delMemory(id)
    list.value = list.value.filter((m) => m.id !== id)
  } catch {
    /* 同上 */
  }
}

function when(ts?: number) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return `${d.getMonth() + 1}月${d.getDate()}日`
}

onMounted(load)
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div class="page-head-left">
        <span class="page-title">记忆</span>
        <span class="page-sub">{{ list.length }} 条</span>
      </div>
    </header>

    <div class="page-body sc-scroll">
      <div class="page-inner stack">
        <div class="card">
          <div class="card-head">
            <span class="card-title">让它记住一件事</span>
          </div>
          <div class="card-body" style="padding-top: 4px">
            <el-input
              v-model="text"
              type="textarea"
              :rows="2"
              maxlength="500"
              show-word-limit
              placeholder="比如：我习惯周五下午做本周复盘"
            />
            <div class="mem-actions">
              <span class="muted-line">对话里说“记住…”也会自动写入</span>
              <button class="btn-dark" :disabled="!text.trim() || busy" @click="add">加入记忆</button>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <span class="card-title">已记住的内容</span>
            <span class="card-hint">检索时按相关度取前几条</span>
          </div>
          <div class="card-body mem-list">
            <div v-for="m in list" :key="m.id" class="mem-row">
              <div class="mem-main">
                <p class="mem-text">{{ m.content }}</p>
                <span class="mem-meta">{{ m.created_at ? when(m.created_at) : '较早' }}</span>
              </div>
              <button class="mem-del" title="删除" @click="remove(m.id)">
                <AppIcon name="trash" :size="13" />
              </button>
            </div>
            <p v-if="!list.length" class="empty">还没有记忆，先加一条试试</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped src="../styles/views.css"></style>
