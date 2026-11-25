/* 卸载向导：四步走，后端只管扫盘和删文件，流程都在这 */
const state = {
  step: 1,
  items: [],
  picked: new Set(),
  scan: null,
  busy: false,
  result: null,
};

const $ = (id) => document.getElementById(id);
const LEVEL_TEXT = { safe: '可清理', warn: '注意', danger: '不可恢复' };

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

function itemOf(key) {
  return state.items.find((i) => i.key === key);
}

// ---------------------------------------------------------------- 首屏
async function boot() {
  if (!api()) {
    $('list').innerHTML = '<div class="loading">没有拿到桌面接口，请双击 Uninstall.exe 打开。</div>';
    return;
  }
  const data = await api().scan();
  if (data.error) {
    $('list').innerHTML = '<div class="loading">' + esc(data.error) + '</div>';
    return;
  }

  state.scan = data;
  state.items = data.items || [];
  state.picked = new Set(state.items.filter((i) => i.default).map((i) => i.key));

  $('where').textContent = data.install_dir;
  $('where').title = data.install_dir;
  $('total').textContent = data.data_total_text;
  paintGuard(data.guard);

  $('list').innerHTML = state.items.map(rowHtml).join('');
  syncRows();
  syncNext();
}

function rowHtml(item) {
  const tag = '<span class="tag ' + esc(item.level) + '">' + LEVEL_TEXT[item.level] + '</span>';
  const note = item.note
    ? '<p class="row-note ' + (item.level === 'warn' ? 'warn' : '') + '" data-note hidden>' + esc(item.note) + '</p>'
    : '';
  return (
    '<label class="row" data-key="' + esc(item.key) + '">' +
      '<input type="checkbox" value="' + esc(item.key) + '">' +
      '<div class="row-main">' +
        '<div class="row-top">' +
          '<span class="row-title">' + esc(item.title) + '</span>' + tag +
          '<span class="row-detail">' + esc(item.detail) + '</span>' +
        '</div>' +
        '<p class="row-desc">' + esc(item.desc) + '</p>' + note +
      '</div>' +
    '</label>'
  );
}

function paintGuard(guard) {
  if (!guard) return;
  const run = $('run');
  if (guard.running) {
    run.textContent = guard.can_kill ? '正在运行（端口 ' + guard.port + '）' : '正在运行';
    run.className = 'bad';
    $('kill').hidden = false;
    $('kill').disabled = !guard.can_kill;
  } else {
    run.textContent = '未运行';
    run.className = 'ok';
    $('kill').hidden = true;
  }
}

// ---------------------------------------------------------------- 步骤切换
function showStep(n) {
  state.step = n;
  for (let i = 1; i <= 4; i += 1) $('page' + i).hidden = i !== n;

  document.querySelectorAll('.step').forEach((el) => {
    const s = Number(el.dataset.s);
    el.classList.toggle('on', s === n);
    el.classList.toggle('done', s < n);
  });

  $('prev').hidden = n === 1 || n === 4;
  $('next').hidden = n === 3 || n === 4;
  $('go').hidden = n !== 3;
  $('finish').hidden = n !== 4;
  $('all').hidden = n !== 2;
  $('cancel').textContent = n === 4 ? '关闭' : '取消';
  if (n === 3) renderConfirm();
}

function goto(n) {
  if (state.busy) return;
  if (n === 3 && state.picked.size === 0) return;
  showStep(n);
}

// ---------------------------------------------------------------- 勾选
function syncRows() {
  document.querySelectorAll('.row').forEach((row) => {
    const on = state.picked.has(row.dataset.key);
    row.querySelector('input').checked = on;
    row.classList.toggle('checked', on);
    const note = row.querySelector('[data-note]');
    if (note) note.hidden = !on;
  });
}

function syncNext() {
  $('next').disabled = state.busy || (state.step === 2 && state.picked.size === 0);
  if (state.step !== 2) return;

  const keys = state.scan ? state.scan.all_keys : [];
  const allOn = keys.length > 0 && keys.every((k) => state.picked.has(k));
  $('all').textContent = allOn ? '取消全选' : '删除所有数据';

  const picked = [...state.picked];
  const hasDanger = picked.some((k) => (itemOf(k) || {}).level === 'danger');
  const hasProgram = picked.includes('program');
  const banner = $('banner');

  if (!picked.length) {
    banner.hidden = true;
    return;
  }
  banner.hidden = false;
  banner.className = 'banner' + (allOn || hasDanger || hasProgram ? ' danger' : '');
  $('banner-title').textContent = hasProgram ? '程序文件' : allOn ? '全部数据' : hasDanger ? '不可恢复' : '提醒';
  $('banner-text').textContent = hasProgram
    ? '桌面和开始菜单的快捷方式会先删掉，程序目录要等窗口关闭后再删，这个卸载程序也会一起消失' + (allOn ? '，勾选的数据同样会被删掉。' : '。')
    : allOn
      ? '已选中全部本地数据，删除后无法恢复，建议先把需要的内容导出去。'
      : hasDanger
        ? '勾选的内容删完就没有了，本机没有备份。'
        : '配置、授权、会话这类数据删掉要重新设置或重新导入。';
}

// ---------------------------------------------------------------- 确认页
function renderConfirm() {
  const picked = [...state.picked];
  const freed = picked.reduce((sum, k) => sum + ((itemOf(k) || {}).size || 0), 0);
  const data = state.scan || {};

  $('summary').innerHTML =
    '<span>安装目录</span><b>' + esc(data.install_dir || '—') + '</b>' +
    '<span>删除项</span><b>' + picked.length + ' 项，约 ' + esc(human(freed)) + '</b>';

  $('picked-list').innerHTML = picked.map((key) => {
    const it = itemOf(key) || {};
    return '<li><span>' + esc(it.title || key) + '</span>' +
      '<span class="tag ' + esc(it.level) + '">' + LEVEL_TEXT[it.level] + '</span></li>';
  }).join('');

  const danger = picked.some((k) => (itemOf(k) || {}).level === 'danger');
  $('picked-warn').hidden = !danger;
  $('picked-warn').textContent = '其中包含不可恢复的数据（知识库、记忆或程序文件），确认后无法撤销。';

  $('phrase').value = '';
  $('go').disabled = true;
}

function human(n) {
  if (!n) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return (i === 0 ? v.toFixed(0) : v.toFixed(1)) + ' ' + units[i];
}

// ---------------------------------------------------------------- 执行
async function execute() {
  if (state.busy) return;
  state.busy = true;
  $('mask').hidden = true;
  $('go').disabled = true;
  $('go').textContent = '正在删除…';

  const r = await api().run([...state.picked]);
  state.busy = false;
  $('go').textContent = '卸载';

  if (r.need_stop) {
    paintGuard(r.guard);
    showStep(1);
    const banner = $('banner');
    banner.hidden = false;
    banner.className = 'banner danger';
    $('banner-title').textContent = '先关主程序';
    $('banner-text').textContent = r.message || '主程序还没有完全退出，等一下再试。';
    return;
  }
  if (r.message && !(r.results || []).length) {
    alert(r.message);
    return;
  }
  showResult(r);
}

function showResult(r) {
  state.result = r;
  const results = r.results || [];
  const bad = results.filter((x) => !x.ok).length;

  $('done-mark').textContent = bad ? '!' : '✓';
  $('done-mark').style.color = bad ? 'var(--danger)' : 'var(--ok)';
  $('done-mark').style.background = bad ? 'var(--danger-bg)' : '#eaf4ef';
  $('done-title').textContent = bad ? '有 ' + bad + ' 项没有删掉' : '清理完成';
  $('done-sub').textContent = bad
    ? '标红的那几项可能被占用了，主程序关掉后再进去删一次。'
    : '选中的内容已经删掉了，下面是逐项结果。';

  $('result').innerHTML = results.map((x) => {
    return '<li class="' + (x.ok ? '' : 'bad') + '">' +
      '<span class="mark">' + (x.ok ? '✓' : '×') + '</span>' +
      '<span class="mark-text">' + esc(x.title) + '<span>' + esc(x.detail) + '</span></span>' +
      '</li>';
  }).join('');
  $('result').hidden = results.length === 0;

  $('sum').innerHTML = '共释放 <b>' + esc(r.freed_text || '0 B') + '</b>';
  $('finish').textContent = r.need_exit ? '完成并退出' : '完成';
  showStep(4);
}

// ---------------------------------------------------------------- 绑定
function bind() {
  $('list').addEventListener('change', (e) => {
    const box = e.target;
    if (!box || box.type !== 'checkbox') return;
    if (box.checked) state.picked.add(box.value);
    else state.picked.delete(box.value);
    syncRows();
    syncNext();
  });

  $('all').addEventListener('click', () => {
    const keys = state.scan ? state.scan.all_keys : [];
    const allOn = keys.every((k) => state.picked.has(k));
    state.picked = new Set(allOn ? [] : keys);
    syncRows();
    syncNext();
  });

  $('kill').addEventListener('click', async () => {
    const r = await api().stop_app();
    if (!r.ok) {
      alert(r.message);
      return;
    }
    const data = await api().scan();
    paintGuard(data.guard);
  });

  $('next').addEventListener('click', () => goto(state.step + 1));
  $('prev').addEventListener('click', () => goto(state.step - 1));
  $('cancel').addEventListener('click', () => api().close());
  $('finish').addEventListener('click', () => api().close());

  $('phrase').addEventListener('input', (e) => {
    $('go').disabled = e.target.value.trim() !== 'DELETE';
  });

  $('go').addEventListener('click', () => {
    if (!state.picked.size) return;
    $('mask').hidden = false;
    $('dlg-ok').focus();
  });
  $('dlg-back').addEventListener('click', () => {
    $('mask').hidden = true;
  });
  $('dlg-ok').addEventListener('click', execute);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !$('mask').hidden && !state.busy) $('mask').hidden = true;
  });
}

// 接口有时比脚本先就绪，两边都试一次，保证只启动一遍
let started = false;
function start() {
  if (started || !api()) return;
  started = true;
  bind();
  boot();
}

window.addEventListener('pywebviewready', start);
start();
