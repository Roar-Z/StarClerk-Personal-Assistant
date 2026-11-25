<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, download, type AutoStart, type LogFile, type SystemInfo } from '../api'

const info = ref<SystemInfo>()
const auto = ref<AutoStart>()
const logs = ref<LogFile[]>([])
const logDir = ref('')
const logSize = ref(0)
const busy = ref('')

// 分钟级就够了，没必要精确到秒
const uptime = computed(() => {
  const m = Math.floor((info.value?.uptime || 0) / 60)
  if (m < 60) return `${m} 分钟`
  const h = Math.floor(m / 60)
  return h < 24 ? `${h} 小时 ${m % 60} 分` : `${Math.floor(h / 24)} 天 ${h % 24} 小时`
})

function size(n = 0) {
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  if (n >= 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${n} B`
}

async function load() {
  try {
    const [i, a, l] = await Promise.all([api.systemInfo(), api.autostart(), api.systemLogs()])
    info.value = i
    auto.value = a
    logs.value = l.items
    logDir.value = l.dir
    logSize.value = l.total
  } catch {
    /* 提示统一在 api 层弹 */
  }
}

async function toggleAuto(on: boolean) {
  busy.value = 'auto'
  try {
    auto.value = await api.setAutostart(on)
    ElMessage.success(on ? '已设置开机后台启动' : '已取消开机自启')
  } catch {
    if (auto.value) auto.value.enabled = !on
  } finally {
    busy.value = ''
  }
}

async function doClean(what: 'sessions' | 'vector' | 'config') {
  busy.value = what
  try {
    const r = await api.clean(what)
    ElMessage.success(
      r.need_restart ? `${r.done.join('、')}已清空，重启后生效` : `${r.done.join('、')}已清空`,
    )
    await load()
  } catch {
    /* 同上 */
  } finally {
    busy.value = ''
  }
}

async function exportLogs() {
  download('/system/logs/export')
}

async function openDir(target: 'logs' | 'data') {
  try {
    await api.reveal(target)
  } catch {
    /* 非 Windows 会提示，忽略 */
  }
}

async function tidyLogs() {
  busy.value = 'prune'
  try {
    const r = await api.pruneLogs()
    ElMessage.success(r.removed ? `清掉 ${r.removed} 个旧日志` : '还没有过期日志')
    await load()
  } catch {
    /* 同上 */
  } finally {
    busy.value = ''
  }
}

onMounted(load)

// 后端会自己退，这里只负责先把话说完
async function uninstallApp() {
  busy.value = 'uninstall'
  try {
    await api.uninstall()
    ElMessage.success('正在打开卸载程序，本窗口马上关闭')
  } catch {
    busy.value = ''
  }
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div class="page-head-left">
        <span class="page-title">系统</span>
        <span class="page-sub">本机运行与维护</span>
      </div>
      <button class="btn-ghost" @click="load">刷新</button>
    </header>

    <div class="page-body sc-scroll">
      <div class="page-inner stack">
        <section class="card">
          <div class="card-head">
            <span class="card-title">版本信息</span>
            <span class="pill" :class="`tier-${info?.tier || 'guest'}`">{{ info?.tier_label || '游客' }}</span>
          </div>
          <div class="card-body">
            <div class="sys-name">
              <p>{{ info?.name || 'StarClerk' }}</p>
              <span>v{{ info?.version || '-' }} · {{ info?.build || '源码' }}</span>
            </div>
            <div class="sys-kv">
              <span>运行平台</span><b>{{ info?.system || '-' }}</b>
            </div>
            <div class="sys-kv">
              <span>Python</span><b>{{ info?.python || '-' }}</b>
            </div>
            <div class="sys-kv">
              <span>本地端口</span><b>{{ info?.port || '-' }}</b>
            </div>
            <div class="sys-kv">
              <span>已运行</span><b>{{ uptime }}</b>
            </div>
            <div class="sys-kv">
              <span>数据目录</span><b class="mono" :title="info?.data_dir">{{ info?.data_dir || '-' }}</b>
            </div>
            <div class="sys-kv">
              <span>资料 / 会话</span>
              <b>{{ info?.counts.chunks ?? 0 }} 块 · {{ info?.counts.sessions ?? 0 }} 个</b>
            </div>
            <div class="sys-actions">
              <button class="btn-ghost" @click="openDir('data')">打开数据目录</button>
            </div>
          </div>
        </section>

        <section class="card">
          <div class="card-head">
            <span class="card-title">开机自启</span>
            <span class="card-hint">注册表 HKCU</span>
          </div>
          <div class="card-body">
            <div class="lic-row" style="border-top: 0; padding-top: 0; margin-top: 0">
              <div>
                <p>开机后台静默启动</p>
                <span>只挂托盘，不弹窗，按热键随时唤起</span>
              </div>
              <el-switch
                :model-value="!!auto?.enabled"
                :disabled="!auto?.supported || busy === 'auto'"
                size="small"
                @change="(v) => toggleAuto(Boolean(v))"
              />
            </div>
            <p v-if="auto && !auto.supported" class="muted-line mt8">当前系统不支持注册表自启，只在 Windows 下可用。</p>
            <p v-else class="muted-line mt8 mono ellipsis" :title="auto?.command">{{ auto?.command || '未写入注册表' }}</p>
          </div>
        </section>

        <section class="card">
          <div class="card-head">
            <span class="card-title">运行日志</span>
            <span class="card-hint">{{ logs.length }} 份 · {{ size(logSize) }}</span>
          </div>
          <div class="card-body">
            <div class="sys-files">
              <div v-for="f in logs.slice(0, 4)" :key="f.name" class="sys-file">
                <span class="mono ellipsis">{{ f.name }}</span>
                <b>{{ size(f.size) }}</b>
              </div>
              <p v-if="!logs.length" class="empty">还没有日志文件</p>
            </div>
            <p class="muted-line mt8 mono ellipsis" :title="logDir">{{ logDir }}</p>
            <div class="sys-actions">
              <button class="btn-ghost" @click="exportLogs">导出日志</button>
              <button class="btn-ghost" :disabled="busy === 'prune'" @click="tidyLogs">清理旧日志</button>
              <button class="btn-ghost" @click="openDir('logs')">打开目录</button>
            </div>
          </div>
        </section>

        <section class="card">
          <div class="card-head">
            <span class="card-title">清理工具</span>
            <span class="card-hint">删了就找不回</span>
          </div>
          <div class="card-body">
            <div class="clean-row">
              <div>
                <p>清空会话记录</p>
                <span>聊天内容和历史消息</span>
              </div>
              <el-popconfirm title="会话和消息会全部删掉，确定？" width="210" @confirm="doClean('sessions')">
                <template #reference>
                  <button class="btn-ghost" :disabled="busy === 'sessions'">清空</button>
                </template>
              </el-popconfirm>
            </div>
            <div class="clean-row">
              <div>
                <p>清空向量库</p>
                <span>资料分块和记忆向量，要重新导入</span>
              </div>
              <el-popconfirm title="向量库清空后资料要重新导入，确定？" width="210" @confirm="doClean('vector')">
                <template #reference>
                  <button class="btn-ghost" :disabled="busy === 'vector'">清空</button>
                </template>
              </el-popconfirm>
            </div>
            <div class="clean-row">
              <div>
                <p>重置模型配置</p>
                <span>删掉 .env，回到默认服务商</span>
              </div>
              <el-popconfirm title="模型地址和 Key 会被清掉，确定？" width="210" @confirm="doClean('config')">
                <template #reference>
                  <button class="btn-ghost" :disabled="busy === 'config'">重置</button>
                </template>
              </el-popconfirm>
            </div>
            <p class="muted-line mt8">
              所有数据都在本机 data 目录，不上传；授权档位不受清理影响，想换档去「模型」页激活。
            </p>
          </div>
        </section>

        <section class="card">
          <div class="card-head">
            <span class="card-title">卸载</span>
            <span class="card-hint">会打开卸载向导</span>
          </div>
          <div class="card-body">
            <div class="clean-row">
              <div>
                <p>卸载 StarClerk</p>
                <span>先关掉本程序，再打开卸载向导自己挑要删的东西</span>
              </div>
              <el-popconfirm
                title="现在退出并打开卸载向导，确定？"
                width="230"
                @confirm="uninstallApp"
              >
                <template #reference>
                  <button class="btn-ghost" :disabled="busy === 'uninstall'">卸载</button>
                </template>
              </el-popconfirm>
            </div>
            <p class="muted-line mt8">
              桌面和开始菜单的快捷方式会一起清掉；只删数据的话用上面的清理工具就行。
            </p>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped src="../styles/views.css"></style>
