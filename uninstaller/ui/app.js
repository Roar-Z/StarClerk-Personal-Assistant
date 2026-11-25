/* 卸载向导的交互，逻辑都在这一页里，后端只负责扫盘和删文件 */
const state = {
  items: [],
  picked: new Set(),
  scan: null,
  busy: false,
  result: null,
};

const $ = (id) => document.getElementById(id);

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

const LEVEL_TEXT = { safe: '可清理', warn: '注意', danger: '不可恢复' };

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
  syncFooter();
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
  const run = $('run');
  if (!guard) return;
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

// ---------------------------------------------------------------- 勾选
function itemOf(key) {
  return state.items.find((i) => i.key === key);
}

function syncRows() {
  document.querySelectorAll('.row').forEach((row) => {
    const box = row.querySelector('input');
    const on = state.picked.has(row.dataset.key);
    box.checked = on;
    row.classList.toggle('checked', on);
    const note = row.querySelector('[data-note]');
    if (note) note.hidden = !on;
  });
}

function syncFooter() {
  const n = state.picked.size;
  $('go').disabled = state.busy || n === 0;
  $('go').textContent = n ? '卸载所选内容（' + n + ' 项）' : '卸载所选内容';

  const dataKeys = state.scan ? state.scan.all_keys : [];
  const allOn = dataKeys.length > 0 && dataKeys.every((k) => state.picked.has(k));
  $('all').textContent = allOn ? '取消全选' : '删除所有数据';

  const keys = [...state.picked];
  const hasDanger = keys.some((k) => (itemOf(k) || {}).level === 'danger');
  const hasProgram = keys.includes('program');
  const banner = $('banner');

  if (!n) {
    banner.hidden = true;
    return;
  }
  banner.hidden = false;
  banner.className = 'banner' + (allOn || hasDanger || hasProgram ? ' danger' : '');
  $('banner-title').textContent = hasProgram ? '程序文件' : allOn ? '全部数据' : hasDanger ? '不可恢复' : '提醒';
  $('banner-text').textContent = hasProgram
    ? '程序目录会在窗口关闭后删除，这个卸载程序也会一起消失' + (allOn ? '，勾选的数据同样会被删掉。' : '。')
    : allOn
      ? '已选中全部本地数据，删除后无法恢复，建议先把需要的内容导出去。'
      : hasDanger
        ? '勾选的内容删完就没有了，本机没有备份。'
        : '配置、授权、会话这类数据删掉要重新设置或重新导入。';
}

// ---------------------------------------------------------------- 弹窗
function openDialog() {
  state.result = null;
  clearResult();
  $('dlg-title').textContent = '确认删除';
  $('dlg-sub').textContent = '以下 ' + state.picked.size + ' 项内容会被永久删除，本机没有备份。';
  $('dlg-list').innerHTML = [...state.picked].map((key) => {
    const it = itemOf(key) || {};
    return '<li><span>' + esc(it.title || key) + '</span><span class="tag ' + esc(it.level) + '">' +
      LEVEL_TEXT[it.level] + '</span></li>';
  }).join('');

  const danger = [...state.picked].some((k) => (itemOf(k) || {}).level === 'danger');
  const warnBox = $('dlg-warn');
  warnBox.hidden = !danger;
  warnBox.textContent = '其中包含不可恢复的数据（知识库、记忆或程序文件），确认后无法撤销。';

  $('dlg-input').hidden = false;
  $('phrase').value = '';
  $('confirm').disabled = true;
  $('confirm').textContent = '确认删除';
  $('back').disabled = false;
  $('mask').hidden = false;
  $('phrase').focus();
}

function closeDialog() {
  $('mask').hidden = true;
  $('phrase').value = '';
  $('confirm').disabled = true;
}

function showResult(r) {
  state.result = r;
  const bad = (r.results || []).filter((x) => !x.ok).length;
  $('dlg-title').textContent = bad ? '部分内容没有删掉' : '清理完成';
  $('dlg-sub').textContent = bad
    ? '下面是逐项结果，标红的那几项可能被占用了，关掉相关程序再试一次。'
    : '选中的内容已经删掉了，下面是逐项结果。';
  $('dlg-list').hidden = true;
  $('dlg-input').hidden = true;
  $('dlg-warn').hidden = true;

  const list = (r.results || []).map((x) => {
    return '<li class="' + (x.ok ? '' : 'bad') + '">' +
      '<span class="mark">' + (x.ok ? '✓' : '×') + '</span>' +
      '<span class="mark-text">' + esc(x.title) + '<span>' + esc(x.detail) + '</span></span>' +
      '</li>';
  }).join('');

  const sum = '共释放 <b>' + esc(r.freed_text || '0 B') + '</b>';
  $('dlg-sub').insertAdjacentHTML(
    'afterend',
    '<ul class="result" id="result-list">' + list + '</ul><p class="sum" id="result-sum">' + sum + '</p>',
  );

  $('back').hidden = true;
  $('confirm').disabled = false;
  $('confirm').textContent = r.need_exit ? '完成并退出' : '完成';
}

function clearResult() {
  const list = $('result-list');
  if (list) list.remove();
  const sum = $('result-sum');
  if (sum) sum.remove();
  $('dlg-list').hidden = false;
  $('dlg-warn').hidden = false;
  $('back').hidden = false;
}

// ---------------------------------------------------------------- 主流程
async function execute() {
  if (state.busy) return;
  state.busy = true;
  $('confirm').disabled = true;
  $('confirm').textContent = '正在删除…';
  $('back').disabled = true;

  const r = await api().run([...state.picked]);
  state.busy = false;
  $('back').disabled = false;

  if (r.need_stop) {
    closeDialog();
    paintGuard(r.guard);
    const banner = $('banner');
    banner.hidden = false;
    banner.className = 'banner danger';
    $('banner-title').textContent = '先关主程序';
    $('banner-text').textContent = r.message || '主程序还在运行，关掉之后再删。';
    return;
  }
  if (r.message && !(r.results || []).length) {
    closeDialog();
    alert(r.message);
    return;
  }
  showResult(r);
}

// ---------------------------------------------------------------- 绑定
function bind() {
  $('list').addEventListener('change', (e) => {
    const box = e.target;
    if (!box || box.type !== 'checkbox') return;
    if (box.checked) state.picked.add(box.value);
    else state.picked.delete(box.value);
    syncRows();
    syncFooter();
  });

  $('all').addEventListener('click', () => {
    const keys = state.scan ? state.scan.all_keys : [];
    const allOn = keys.every((k) => state.picked.has(k));
    state.picked = new Set(allOn ? [] : keys);
    syncRows();
    syncFooter();
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

  $('go').addEventListener('click', openDialog);
  $('cancel').addEventListener('click', () => api().close());
  $('back').addEventListener('click', closeDialog);

  $('phrase').addEventListener('input', (e) => {
    $('confirm').disabled = e.target.value.trim() !== 'DELETE';
  });

  $('confirm').addEventListener('click', () => {
    if (state.result) {
      if (state.result.need_exit) api().close();
      else {
        closeDialog();
        clearResult();
        boot();
      }
      return;
    }
    execute();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !$('mask').hidden && !state.busy) closeDialog();
  });
}

// 接口可能比脚本先就绪，也可能后到，两边都试一次，保证只启动一遍
let started = false;
function start() {
  if (started || !api()) return;
  started = true;
  bind();
  boot();
}

window.addEventListener('pywebviewready', start);
start();
