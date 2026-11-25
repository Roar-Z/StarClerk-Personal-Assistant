<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'

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
const status = ref<{ ok: boolean; text: string } | null>(null)

function applyPreset(name: string) {
  const p = providers.value[name]
  if (!p) return
  cfg.llm_base_url = p.base_url
  cfg.llm_model = p.model
}
async function load() {
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
}
async function save() {
  saving.value = true
  try {
    const body = { ...cfg }
    if (!body.llm_api_key) delete body.llm_api_key
    const r = await api.saveSettings(body)
    ElMessage.success(r.need_rebuild_vector ? '已保存，向量配置变更需重建索引' : '已保存')
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}
async function test() {
  testing.value = true
  status.value = null
  try {
    const r = await api.testLLM()
    status.value = r.ok ? { ok: true, text: `连接正常 · ${r.reply}` } : { ok: false, text: r.error || '连接失败' }
  } catch (e: any) {
    status.value = { ok: false, text: e.message }
  } finally {
    testing.value = false
  }
}
onMounted(load)
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div class="page-head-left">
        <span class="page-title">设置</span>
        <span class="page-sub">配置保存在本机 .env</span>
      </div>
      <el-button size="small" type="primary" :loading="saving" @click="save">保存</el-button>
    </header>

    <div class="page-body sc-scroll">
      <div class="page-inner">
        <div class="grid-2">
          <section class="card">
            <div class="card-head"><span class="card-title">对话模型</span><span class="card-hint">OpenAI 兼容协议</span></div>
            <div class="card-body">
              <div class="form-row">
                <label>服务商</label>
                <el-select v-model="cfg.llm_provider" size="small" @change="applyPreset">
                  <el-option v-for="(_, k) in providers" :key="k" :label="k" :value="k" />
                </el-select>
              </div>
              <div class="form-row">
                <label>接口地址</label>
                <el-input v-model="cfg.llm_base_url" size="small" />
              </div>
              <div class="form-row">
                <label>API Key</label>
                <el-input v-model="cfg.llm_api_key" size="small" type="password" show-password placeholder="留空则不修改" />
              </div>
              <div class="form-row">
                <label>模型</label>
                <el-input v-model="cfg.llm_model" size="small" />
              </div>
              <div class="form-actions">
                <el-button link size="small" :loading="testing" @click="test">测试连接</el-button>
                <span v-if="status" class="status" :class="{ bad: !status.ok }"><i />{{ status.text }}</span>
              </div>
            </div>
          </section>

          <section class="card">
            <div class="card-head"><span class="card-title">本地索引</span><span class="card-hint">建议 Ollama + bge-m3</span></div>
            <div class="card-body">
              <div class="form-row">
                <label>向量服务</label>
                <el-input v-model="cfg.embed_base_url" size="small" />
              </div>
              <div class="form-row">
                <label>向量模型</label>
                <el-input v-model="cfg.embed_model" size="small" />
              </div>
              <div class="form-row">
                <label>向量维度</label>
                <el-input-number v-model="cfg.embed_dim" :min="64" :max="4096" size="small" controls-position="right" />
              </div>
              <div class="form-row">
                <label>断网降级</label>
                <div class="switch-line">
                  <el-switch v-model="cfg.fallback_enabled" size="small" />
                  <span>云端失败自动切本地</span>
                </div>
              </div>
            </div>
          </section>
        </div>

        <div class="grid-2 mt16">
          <section class="card">
            <div class="card-head"><span class="card-title">交互</span></div>
            <div class="card-body">
              <div class="form-row">
                <label>唤起快捷键</label>
                <el-input v-model="cfg.hotkey" size="small" />
              </div>
              <p class="muted-line mt8">格式示例：&lt;ctrl&gt;+&lt;alt&gt;+&lt;space&gt;，修改后需重启生效。</p>
            </div>
          </section>

          <section class="card">
            <div class="card-head"><span class="card-title">关于</span></div>
            <div class="card-body">
              <p class="muted-line">接口地址与模型改动需重启应用生效；向量维度变更需重建索引。会话、知识库与记忆全部保存在本机 data 目录，可直接整目录备份。</p>
            </div>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped src="../styles/views.css"></style>
