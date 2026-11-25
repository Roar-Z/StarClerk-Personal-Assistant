/* 安装向导：选目录 → 附加任务 → 三步安装，界面只负责翻页和进度 */
const state = {
  step: 1,
  info: null,
  target: '',
  installing: false,
  failed: false,
};

const $ = (id) => document.getElementById(id);

// 后端按这个顺序干活，进度条也照着它走
const STEPS = [
  { key: 'files', text: '复制程序文件' },
  { key: 'shortcuts', text: '创建快捷方式' },
  { key: 'registry', text: '登记到应用列表' },
];

function api() {
  return window.pywebview && window.pywebview.api;
}

function esc(text) {
  return String(text == null ? '' : text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ---------------------------------------------------------------- 首屏
async function boot() {
  if (!api()) {
    $('welcome').innerHTML = '<span>提示</span><b>没有拿到桌面接口，请双击 Setup.exe 打开</b>';
    return;
  }
  const info = await api().info();
  state.info = info;
  state.target = info.default_dir;

  $('ver').textContent = 'v' + info.version;
  $('dir').value = info.default_dir;
  $('welcome').innerHTML =
    '<span>程序版本</span><b>' + esc(info.app) + ' ' + esc(info.version) + '</b>' +
    '<span>需要空间</span><b>' + esc(info.need_text) + '</b>' +
    '<span>安装位置</span><b>' + esc(info.default_dir) + '</b>';

  if (!info.payload_ok) {
    $('welcome-tip').className = 'tip hint bad';
    $('welcome-tip').textContent =
      '安装包里没有找到程序文件（' + info.payload_dir + '），这个包不完整，得重新打包。';
    $('next').disabled = true;
  }
  syncSpace();
}

async function syncSpace() {
  const r = await api().check($('dir').value);
  $('space').innerHTML =
    '<span>安装到</span><b>' + esc(r.target || $('dir').value) + '</b>' +
    '<span>需要 / 剩余</span><b>' + esc((state.info || {}).need_text || '—') + ' / ' +
    esc((state.info || {}).free_text || '—') + '</b>';

  const hint = $('dir-hint');
  hint.className = 'hint' + (r.ok ? '' : ' bad');
  hint.textContent = r.ok ? (r.message || '路径没问题，会装到这个目录里。') : r.message;
  $('next').disabled = !r.ok;
  state.target = r.target || $('dir').value;
}

// ---------------------------------------------------------------- 翻页
function showStep(n) {
  state.step = n;
  for (let i = 1; i <= 4; i += 1) $('page' + i).hidden = i !== n;
  document.querySelectorAll('.step').forEach((el) => {
    const s = Number(el.dataset.s);
    el.classList.toggle('on', s === n);
    el.classList.toggle('done', s < n);
  });

  $('prev').hidden = n !== 2 && n !== 3;
  $('next').hidden = n !== 1 && n !== 2;
  $('install').hidden = n !== 3;
  $('finish').hidden = n !== 4;
  $('quit').hidden = n === 4;
}

// ---------------------------------------------------------------- 安装
function logLine(text, cls) {
  const li = document.createElement('li');
  li.className = cls || 'now';
  li.textContent = text;
  $('log').appendChild(li);
  return li;
}

async function install() {
  if (state.installing) return;
  state.installing = true;
  state.failed = false;
  showStep(4);

  $('log').innerHTML = '';
  $('done-box').hidden = true;
  $('bar').style.width = '0';
  $('last-title').textContent = '正在安装';
  $('last-sub').textContent = '正在往目标目录写文件，别关窗口。';
  $('finish').disabled = true;

  const options = {
    desktop: $('desktop').checked,
    menu: $('menu').checked,
    autostart: $('autostart').checked,
  };

  for (let i = 0; i < STEPS.length; i += 1) {
    const step = STEPS[i];
    const li = logLine(step.text + '…');
    const r = await api().install(state.target, options, step.key);
    if (!r.ok) {
      li.className = 'bad';
      li.textContent = step.text + '失败：' + r.message;
      state.failed = true;
      break;
    }
    li.className = 'ok';
    li.textContent = step.text + '：' + r.message;
    $('bar').style.width = Math.round(((i + 1) / STEPS.length) * 100) + '%';
  }

  state.installing = false;
  $('finish').disabled = false;

  if (state.failed) {
    $('done-mark').textContent = '!';
    $('done-mark').style.color = 'var(--danger)';
    $('done-mark').style.background = 'var(--danger-bg)';
    $('last-title').textContent = '没有装完';
    $('last-sub').textContent = '看上面标红的那一步，处理完可以点「上一步」再装一次。';
    $('finish').textContent = '关闭';
    $('prev').hidden = false;
    return;
  }

  $('done-mark').textContent = '✓';
  $('last-title').textContent = '安装完成';
  $('last-sub').textContent = 'StarClerk 已经装好了，桌面快捷方式可以直接打开。';
  $('finish').textContent = '完成';
  $('done-box').hidden = false;
  $('done-box').innerHTML =
    '<span>安装目录</span><b>' + esc(state.target) + '</b>' +
    '<span>卸载方式</span><b>应用和功能里找 StarClerk，或目录里的 Uninstall.exe</b>' +
    '<label class="opt" style="grid-column:1/-1;border:0;padding:8px 0 0">' +
      '<input type="checkbox" id="runnow" checked />' +
      '<div><b>立即运行 StarClerk</b><span>装完直接打开，不用自己去找</span></div>' +
    '</label>';
}

async function finish() {
  if (state.failed) {
    api().close();
    return;
  }
  const box = $('runnow');
  if (box && box.checked) await api().launch(state.target);
  api().close();
}

// ---------------------------------------------------------------- 绑定
function bind() {
  $('next').addEventListener('click', () => {
    if (state.step === 1) showStep(2);
    else if (state.step === 2) showStep(3);
  });
  $('prev').addEventListener('click', () => showStep(Math.max(1, state.step - 1)));

  $('browse').addEventListener('click', async () => {
    const r = await api().pick_dir($('dir').value);
    if (!r.ok) return;
    $('dir').value = r.path;
    syncSpace();
  });

  // 每敲一个字都校验一下，省得点了下一步才发现路径不对
  let timer = 0;
  $('dir').addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(syncSpace, 260);
  });

  $('install').addEventListener('click', install);
  $('finish').addEventListener('click', finish);
  $('quit').addEventListener('click', () => {
    if (state.installing) return;
    api().close();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !state.installing) api().close();
  });
}

let started = false;
function start() {
  if (started || !api()) return;
  started = true;
  bind();
  boot();
}

window.addEventListener('pywebviewready', start);
start();
