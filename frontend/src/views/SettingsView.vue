<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { loadLicense, loadSessions, me } from '../store'

const cfg = reactive<any>({
  llm_provider: 'deepseek',
  llm_base_url: '',
  llm_api_key: '',
  llm_model: '',
  embed_base_url: '',
  embed_model: '',
  embed_dim: 1024,
  fallback_enabled: true,
  hotkey: '<ctrl>+<alt>+<space>',
})
const providers = ref<Record<string, any>>({})
const saving = ref(false)
const testing = ref(false)
const rebuilding = ref(false)
const status = ref<{ ok: boolean; text: string } | null>(null)
const code = ref('')
const activating = ref(false)
const perfBusy = ref(false)

async function doActivate() {
  const text = code.value.trim()
  if (!text) return ElMessage.warning('先粘贴激活码')
  activating.value = true
  try {
    await api.activate(text)
    await loadLicense()
    await loadSessions()
    code.value = ''
    ElMessage.success(`已激活 ${me.value?.label || ''}`)
  } catch {
    /* 码不对的提示在 api 层 */
  } finally {
    activating.value = false
  }
}

async function togglePerf(on: boolean) {
  perfBusy.value = true
  try {
    me.value = await api.setPerf(on)
    ElMessage.success(on ? '低配模式已开，巡检间隔会拉长' : '已恢复常规模式')
  } catch {
    if (me.value) me.value.perf_mode = !on
  } finally {
    perfBusy.value = false
  }
}

async function backToGuest() {
  try {
    await api.resetLicense()
    await loadLicense()
    await loadSessions()
    ElMessage.success('已退回游客模式')
  } catch {
    /* 同上 */
  }
}

function applyPreset(name: string) {
  const p = providers.value[name]
  if (!p) return
  cfg.llm_base_url = p.base_url
  cfg.llm_model = p.model
}

async function load() {
  try {
    const s = await api.settings()
    providers.value = s.providers
    Object.assign(cfg, {
      llm_provider: s.llm_provider,
      llm_base_url: s.llm_base_url,
      llm_model: s.llm_model,
      embed_base_url: s.embed_base_url,
      embed_model: s.embed_model,
      embed_dim: s.embed_dim,
      fallback_enabled: s.fallback_enabled,
      hotkey: s.hotkey,
    })
  } catch {
    /* 提示在 api 层 */
  }
}

async function save() {
  saving.value = true
  try {
    const body = { ...cfg }
    // 留空表示沿用原来的 key，不覆盖
    if (!body.llm_api_key) delete body.llm_api_key
    const r = await api.saveSettings(body)
    ElMessage.success(r.need_rebuild_vector ? '已保存，向量配置改了要重建索引' : '已保存')
  } catch {
    /* 同上 */
  } finally {
    saving.value = false
  }
}

async function test() {
  testing.value = true
  status.value = null
  try {
    const r = await api.testLLM()
    status.value = r.ok ? { ok: true, text: `连接正常 · ${r.reply}` } : { ok: false, text: r.error || '连不上' }
  } catch (e: any) {
    status.value = { ok: false, text: e.message }
  } finally {
    testing.value = false
  }
}

async function rebuild() {
  rebuilding.value = true
  try {
    await api.rebuildVector()
    ElMessage.success('向量库已清空，资料需要重新导入')
  } catch {
    /* 同上 */
  } finally {
    rebuilding.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div class="page-head-left">
        <span class="page-title">模型</span>
        <span class="page-sub">写在本机 .env</span>
      </div>
      <el-button size="small" type="primary" :loading="saving" @click="save">保存</el-button>
    </header>

    <div class="page-body sc-scroll">
      <div class="page-inner stack">
        <section class="card">
          <div class="card-head">
            <span class="card-title">本地授权</span>
            <span class="card-hint">离线校验</span>
          </div>
          <div class="card-body">
            <div class="lic-head">
              <div>
                <p class="lic-name">{{ me?.label || '游客' }}</p>
                <span class="lic-sub">
                  任务 {{ me?.limits.tasks ?? 0 }} · 文档 {{ me?.limits.docs ?? 0 }} · 记忆
                  {{ me?.limits.memories ?? 0 }}
                </span>
              </div>
              <el-button v-if="me && !me.is_guest" link size="small" @click="backToGuest">退回游客</el-button>
            </div>
            <div v-if="!me?.is_pro" class="lic-input">
              <el-input
                v-model="code"
                size="small"
                placeholder="粘贴激活码，如 FREE-2024AB-1A2B"
                @keyup.enter="doActivate"
              />
              <el-button size="small" type="primary" :loading="activating" @click="doActivate">激活</el-button>
            </div>
            <div class="lic-row">
              <div>
                <p>低配性能模式</p>
                <span>巡检间隔拉长，模型并发固定 {{ me?.max_concurrency ?? 2 }} 路</span>
              </div>
              <el-switch
                :model-value="!!me?.perf_mode"
                :loading="perfBusy"
                size="small"
                @change="(v) => togglePerf(Boolean(v))"
              />
            </div>
          </div>
        </section>

        <section class="card">
          <div class="card-head">
            <span class="card-title">对话模型</span>
            <span class="card-hint">OpenAI 兼容</span>
          </div>
          <div class="card-body">
            <div class="form-row">
              <label>服务商</label>
              <el-select v-model="cfg.llm_provider" size="small" @change="applyPreset">
                <el-option v-for="(_, k) in providers" :key="k" :label="k" :value="k" />
              </el-select>
            </div>
            <div class="form-row">
              <label>接口地址</label>
              <el-input v-model="cfg.llm_base_url" size="small" placeholder="https://api.xxx.com/v1" />
            </div>
            <div class="form-row">
              <label>API Key</label>
              <el-input v-model="cfg.llm_api_key" size="small" type="password" show-password placeholder="留空表示不改" />
            </div>
            <div class="form-row">
              <label>模型名</label>
              <el-input v-model="cfg.llm_model" size="small" />
            </div>
            <div class="form-foot">
              <el-button link size="small" :loading="testing" @click="test">测试连接</el-button>
              <span v-if="status" class="status" :class="{ bad: !status.ok }"><i />{{ status.text }}</span>
            </div>
          </div>
        </section>

        <section class="card">
          <div class="card-head">
            <span class="card-title">本地向量</span>
            <span class="card-hint">Ollama + bge-m3</span>
          </div>
          <div class="card-body">
            <div class="form-row">
              <label>服务地址</label>
              <el-input v-model="cfg.embed_base_url" size="small" placeholder="http://127.0.0.1:11434/v1" />
            </div>
            <div class="form-row">
              <label>模型</label>
              <el-input v-model="cfg.embed_model" size="small" placeholder="bge-m3" />
            </div>
            <div class="form-row">
              <label>维度</label>
              <el-input-number v-model="cfg.embed_dim" :min="64" :max="4096" size="small" controls-position="right" />
            </div>
            <div class="form-row">
              <label>断网降级</label>
              <div class="switch-line">
                <el-switch v-model="cfg.fallback_enabled" size="small" />
                <span>云端挂了自动切本地模型</span>
              </div>
            </div>
            <div class="form-foot">
              <el-popconfirm title="清空向量库后资料要重新导入，确定？" width="220" @confirm="rebuild">
                <template #reference>
                  <el-button link size="small" :loading="rebuilding">重建索引</el-button>
                </template>
              </el-popconfirm>
            </div>
          </div>
        </section>

        <section class="card">
          <div class="card-head"><span class="card-title">交互</span></div>
          <div class="card-body">
            <div class="form-row">
              <label>唤起热键</label>
              <el-input v-model="cfg.hotkey" size="small" />
            </div>
            <p class="muted-line mt8">
              例：&lt;ctrl&gt;+&lt;alt&gt;+&lt;space&gt;，改完要重启才生效。模型和向量配置同理，数据都在 data 目录，复制走就能带走。
            </p>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped src="../styles/views.css"></style>
