<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { isGuest, loadLicense, loadSessions, me } from '../store'
import { isDesktop, win } from '../desktop'

const cfg = reactive<any>({
  llm_provider: 'deepseek',
  llm_base_url: '',
  llm_api_key: '',
  llm_model: '',
  llm_gateway: 'own',
  embed_base_url: '',
  embed_model: '',
  embed_dim: 1024,
  fallback_enabled: true,
  hotkey: '<ctrl>+<alt>+<space>',
})
const providers = ref<Record<string, any>>({})
// 未登录实际调的是哪个免费模型，后端在 /config 里一起给
const guestModel = ref<{ label: string; model: string; hourly: number } | null>(null)
const saving = ref(false)
const testing = ref(false)
const rebuilding = ref(false)
const status = ref<{ ok: boolean; text: string } | null>(null)
const loginBusy = ref(false)
const perfBusy = ref(false)
type ThemeMode = 'light' | 'dark' | 'system'
const themeMode = ref<ThemeMode>((localStorage.getItem('sc-theme') as ThemeMode) || 'light')
const floatOn = ref(false)

function setTheme(mode: ThemeMode) {
  themeMode.value = mode
  localStorage.setItem('sc-theme', mode)
  window.dispatchEvent(new CustomEvent('sc:theme', { detail: mode }))
}
async function toggleFloat(on: boolean) {
  floatOn.value = on
  window.dispatchEvent(new CustomEvent('sc:float', { detail: on }))
  if (isDesktop()) await win.setFloat(on)
  else ElMessage.info('浏览器里只切界面，窗口交给浏览器管')
}

async function doLogin() {
  loginBusy.value = true
  try {
    await api.login()
    await loadLicense()
    await loadSessions()
    ElMessage.success('已登录，所有功能都能用了')
  } catch {
    /* 提示在 api 层 */
  } finally {
    loginBusy.value = false
  }
}

async function doLogout() {
  try {
    await api.logout()
    await loadLicense()
    await loadSessions()
    ElMessage.success('已退出登录')
  } catch {
    /* 提示在 api 层 */
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
    guestModel.value = s.guest_model || null
    Object.assign(cfg, {
      llm_provider: s.llm_provider,
      llm_base_url: s.llm_base_url,
      llm_model: s.llm_model,
      llm_gateway: s.llm_gateway || 'own',
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
  if (isGuest.value) return ElMessage.warning('未登录不能改模型，登录后就能自己填')
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
  if (isGuest.value) return ElMessage.warning('登录后才能测试自己的模型')
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
      <el-button v-if="!isGuest" size="small" type="primary" :loading="saving" @click="save">保存</el-button>
      <span v-else class="page-sub">未登录只读</span>
    </header>

    <div class="page-body sc-scroll">
      <div class="page-inner bento">
        <section class="card col-5">
          <div class="card-head">
            <span class="card-title">本机登录</span>
            <span class="card-hint">不联网</span>
          </div>
          <div class="card-body">
            <div class="lic-head">
              <div>
                <p class="lic-name">{{ me?.label || '未登录' }}</p>
                <span class="lic-sub">
                  任务 {{ me?.limits.tasks ?? 0 }} · 文档 {{ me?.limits.docs ?? 0 }} · 笔记
                  {{ me?.limits.notes ?? 0 }} · 记忆 {{ me?.limits.memories ?? 0 }}
                </span>
              </div>
              <el-button v-if="me && !me.is_guest" link size="small" @click="doLogout">退出登录</el-button>
            </div>
            <div v-if="me?.is_guest" class="lic-input">
              <el-button size="small" type="primary" :loading="loginBusy" @click="doLogin">登录</el-button>
              <span class="lic-sub">只记在本机，不用账号密码，也不联网</span>
            </div>
            <p v-else-if="me" class="muted-line mt8">已登录，所有功能都开着；退出后回到未登录的限制。</p>
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

        <section class="card col-7">
          <div class="card-head">
            <span class="card-title">外观与窗口</span>
            <span class="card-hint">未登录也能设</span>
          </div>
          <div class="card-body">
            <div class="form-row">
              <label>主题</label>
              <div class="seg">
                <button class="seg-btn" :class="{ on: themeMode === 'light' }" @click="setTheme('light')">浅色</button>
                <button class="seg-btn" :class="{ on: themeMode === 'dark' }" @click="setTheme('dark')">深色</button>
                <button class="seg-btn" :class="{ on: themeMode === 'system' }" @click="setTheme('system')">
                  跟随系统
                </button>
              </div>
            </div>
            <div class="lic-row">
              <div>
                <p>悬浮窗模式</p>
                <span>缩成一小条贴在桌面，按 Ctrl + Alt + Space 随时唤起</span>
              </div>
              <el-switch v-model="floatOn" size="small" @change="toggleFloat" />
            </div>
          </div>
        </section>

        <section class="card col-7">
          <div class="card-head">
            <span class="card-title">对话模型</span>
            <span class="card-hint">{{ isGuest ? '未登录固定' : 'OpenAI 兼容' }}</span>
          </div>

          <div v-if="isGuest" class="card-body">
            <div class="lic-head">
              <div>
                <p class="lic-name">{{ guestModel?.label || 'Kilo 免费' }}</p>
                <span class="lic-sub">{{ guestModel?.model || 'kilo-auto/free' }}</span>
              </div>
              <span class="tag tier-guest">每小时 {{ guestModel?.hourly ?? 0 }} 次</span>
            </div>
            <p class="muted-line mt8">
              未登录只能用这个免费模型，额度是已登录后的一半。登录后可以换成自己的服务商、地址和 Key。
            </p>
          </div>

          <div v-else class="card-body">
            <div class="form-row">
              <label>走哪条</label>
              <div class="seg">
                <button class="seg-btn" :class="{ on: cfg.llm_gateway !== 'kilo' }" @click="cfg.llm_gateway = 'own'">
                  自己的 Key
                </button>
                <button class="seg-btn" :class="{ on: cfg.llm_gateway === 'kilo' }" @click="cfg.llm_gateway = 'kilo'">
                  Kilo 免费网关
                </button>
              </div>
            </div>
            <p v-if="cfg.llm_gateway === 'kilo'" class="muted-line">
              走 {{ guestModel?.model || 'kilo-auto/free' }}，不花自己的额度，按小时限流，赶时间就切回来。
            </p>
            <div class="form-row">
              <label>服务商</label>
              <el-select v-model="cfg.llm_provider" size="small" :disabled="cfg.llm_gateway === 'kilo'" @change="applyPreset">
                <el-option v-for="(_, k) in providers" :key="k" :label="k" :value="k" />
              </el-select>
            </div>
            <div class="form-row">
              <label>接口地址</label>
              <el-input
                v-model="cfg.llm_base_url"
                size="small"
                :disabled="cfg.llm_gateway === 'kilo'"
                placeholder="https://api.xxx.com/v1"
              />
            </div>
            <div class="form-row">
              <label>API Key</label>
              <el-input
                v-model="cfg.llm_api_key"
                size="small"
                type="password"
                show-password
                :disabled="cfg.llm_gateway === 'kilo'"
                placeholder="留空表示不改"
              />
            </div>
            <div class="form-row">
              <label>模型名</label>
              <el-input v-model="cfg.llm_model" size="small" :disabled="cfg.llm_gateway === 'kilo'" />
            </div>
            <div class="form-foot">
              <el-button link size="small" :loading="testing" @click="test">测试连接</el-button>
              <span v-if="status" class="status" :class="{ bad: !status.ok }"><i />{{ status.text }}</span>
            </div>
          </div>
        </section>

        <section class="card col-5">
          <div class="card-head">
            <span class="card-title">本地向量</span>
            <span class="card-hint">Ollama + bge-m3</span>
          </div>
          <div class="card-body">
            <p v-if="isGuest" class="muted-line">未登录模式只读，这些参数登录后才能改。</p>
            <div class="form-row">
              <label>服务地址</label>
              <el-input
                v-model="cfg.embed_base_url"
                size="small"
                :disabled="isGuest"
                placeholder="http://127.0.0.1:11434/v1"
              />
            </div>
            <div class="form-row">
              <label>模型</label>
              <el-input v-model="cfg.embed_model" size="small" :disabled="isGuest" placeholder="bge-m3" />
            </div>
            <div class="form-row">
              <label>维度</label>
              <el-input-number
                v-model="cfg.embed_dim"
                :min="64"
                :max="4096"
                :disabled="isGuest"
                size="small"
                controls-position="right"
              />
            </div>
            <div class="form-row">
              <label>断网降级</label>
              <div class="switch-line">
                <el-switch v-model="cfg.fallback_enabled" size="small" :disabled="isGuest" />
                <span>云端挂了自动切本地模型</span>
              </div>
            </div>
            <div class="form-foot">
              <el-popconfirm title="清空向量库后资料要重新导入，确定？" width="220" @confirm="rebuild">
                <template #reference>
                  <el-button link size="small" :loading="rebuilding" :disabled="isGuest">重建索引</el-button>
                </template>
              </el-popconfirm>
            </div>
          </div>
        </section>

        <section class="card col-12">
          <div class="card-head"><span class="card-title">交互</span></div>
          <div class="card-body">
            <div class="form-row">
              <label>唤起热键</label>
              <el-input v-model="cfg.hotkey" size="small" :disabled="isGuest" />
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
