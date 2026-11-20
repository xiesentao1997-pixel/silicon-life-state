import { mountChat, clearChat } from './chat.js';
import { drawIris, icon } from './graphics.js';
import { watchPairCode } from './pairing.js';
import { h, nav, pages, sources, stages, kinds, short, when, badge, button, empty, card, item, eventText, sourceBadge, levels, renderPage } from './views.js';
const $ = s => document.querySelector(s);
const dialog = $('#dialog'),
  content = $('#content'),
  dialogBody = $('#dialog-body');
const initial = new URLSearchParams(location.hash.slice(1));
const base = {
  subject_summaries: [],
  subjects: [],
  instances: [],
  sessions: [],
  report_states: [],
  events: [],
  requests: [],
  memory: {
    common: [],
    proposals: [],
    decisions: [],
    disputed: []
  },
  stats: {}
};
const m = {
  ...base,
  subject: null,
  subjectId: initial.get('subject') || '',
  instanceId: initial.get('instance') || '',
  view: Object.hasOwn(pages, initial.get('view')) ? initial.get('view') : initial.has('instance') ? 'instances' : 'overview',
  range: '7',
  measure: 'valence',
  from: '',
  to: '',
  q: '',
  source: '',
  stage: '',
  eventLimit: 35,
  settings: null,
  grants: null,
  grantsError: '',
  backups: null,
  backupsError: '',
  online: false,
  snapshotReady: false,
  problem: '',
  theme: localStorage.getItem('sls-theme') === 'cream' ? 'cream' : 'night'
};
const bindingKey = 'sls-dashboard-binding';
let binding = localStorage.getItem(bindingKey) || '',
  stamp = '',
  pollGeneration = 0,
  toastTimer,
  artOK = false;
let activeSubmit = null,
  capturedSecret = '',
  isWorking = false;
const image = new Image();
image.onload = () => {
  artOK = true;
  if ($('.hero')) $('.hero').classList.add('art-loaded');
};
image.src = '/assets/life.webp';
document.documentElement.dataset.theme = m.theme;
const id = () => crypto.randomUUID();
function toast(msg) {
  const b = $('#toast');
  b.textContent = msg;
  b.classList.add('visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => b.classList.remove('visible'), 4000);
}
function field(label, input) {
  return '<label class="field">' + h(label) + input + '</label>';
}
function options(rows, sel = '') {
  return rows.map(([v, l]) => '<option value="' + h(v) + '"' + (v === sel ? ' selected' : '') + '>' + h(l)
    + '</option>').join('');
}
function namedSelect(name, rows, sel = '') {
  return '<select name="' + h(name) + '" required>' + options(rows, sel) + '</select>';
}
function instanceField(defaultId = '') {
  return field('分身', namedSelect('instance_id', m.instances.map(i => [i.instance_id, i.name]), defaultId || m.instanceId));
}
let stopPairWatch = null;
let displayedPairCode = '';
function clearPairWatch() {
  if (stopPairWatch) stopPairWatch();
  stopPairWatch = null;
  displayedPairCode = '';
}
function modal(title, body, submit = null, ok = '保存', danger = false) {
  clearPairWatch();
  activeSubmit = submit;
  capturedSecret = '';
  dialogBody.innerHTML = '<div class="card-header"><h2 id="dialog-title">' + h(title)
    + '</h2><button type="button" data-act="close" class="icon-btn" aria-label="关闭">' + icon('close', 17)
    + '</button></div>' + (submit ? '<form id="form" method="dialog">' + body
    + '<p class="error-msg" role="alert"></p><div class="actions">' + button('close', '取消')
    + '<button type="submit" class="btn ' + (danger ? 'danger' : 'primary') + '">' + h(ok)
    + '</button></div></form>' : body + '<p class="error-msg" role="alert"></p>');
  if (!dialog.open) dialog.showModal();else dialog.scrollTop = 0;
}
function close() {
  clearPairWatch();
  dialog.close();
  dialogBody.replaceChildren();
  capturedSecret = '';
  activeSubmit = null;
}
dialog.addEventListener('close', () => {
  if (dialog.open) return;
  clearPairWatch();
  capturedSecret = '';
  activeSubmit = null;
  dialogBody.replaceChildren();
});
function modalError(msg) {
  const e = $('#dialog .error-msg');
  if (dialog.open && e) e.textContent = msg;else toast(msg);
}
function saveHash() {
  const p = new URLSearchParams({
    view: m.view
  });
  if (m.subjectId) p.set('subject', m.subjectId);
  if (m.instanceId) p.set('instance', m.instanceId);
  history.replaceState(null, '', '#' + p.toString());
}
function clearOwner() {
  ++pollGeneration;
  clearChat();
  binding = '';
  localStorage.removeItem(bindingKey);
  sessionStorage.removeItem('sls-owner');
  stamp = '';
  m.snapshotReady = false;
  m.subject = null;
  Object.assign(m, base, {
    settings: null,
    grants: null,
    installations: [],
    installationsError: '',
    grantsError: '',
    backups: null,
    backupsError: ''
  });
  m.subjectId = '';
  m.instanceId = '';
  if (dialog.open) close();
}
async function api(path, body = null, auth = true, headers = {}) {
  const requestBinding = binding;
  if (auth) {
    if (!binding) throw Error('请先用本地服务提供的配对码连接仪表盘。');
    headers['X-SLS-Dashboard'] = requestBinding;
  }
  if (body !== null) headers['Content-Type'] = 'application/json';
  let res;
  try {
    res = await fetch('/api/' + path, {
      method: body === null ? 'GET' : 'POST',
      headers,
      body: body === null ? undefined : JSON.stringify(body),
      cache: 'no-store',
      credentials: 'same-origin',
      signal: AbortSignal.timeout(path === 'chat/message' ? 210000 : 20000)
    });
  } catch {
    m.online = false;
    throw Error('本地服务连接中断。请检查启动窗口后重试。');
  }
  const data = await res.json();
  m.online = true;
  if (!res.ok) {
    if (res.status === 401 && auth && requestBinding === localStorage.getItem(bindingKey)) {
      clearOwner();
      render();
    }
    const zh = {
      ALREADY_BOUND: '此分身已有凭据。可在设置的 Agent 授权中撤销后重新签发。',
      INVALID_TRANSITION: '请求状态已经改变。请关闭详情后重新打开。',
      LEVEL_REQUIRED: '当前主体模式未授权此类执行。请在设置中核对行为调整级别。',
      MISSING_OBSERVATION: '缺少输入数值。请选择带愉悦度的报告，并提供 α 或带有负荷的报告。',
      STALE_VERSION: '记录已经更新，请刷新后重试。'
    };
    const err = new Error(zh[data?.error?.code] || data?.error?.message || '请求失败（' + res.status + '）');
    err.code = data?.error?.code;
    err.status = res.status;
    throw err;
  }
  return data;
}
async function write(path, body, key = id()) {
  return api(path, {
    ...body,
    idempotency_key: key
  });
}
async function refresh(force = false) {
  const generation = ++pollGeneration;
  if (!binding) {
    try {
      await api('health', null, false);
      m.problem = '';
    } catch (err) {
      m.problem = err.message;
    }
    if (generation === pollGeneration) render();
    return;
  }
  try {
    const inventory = await api('subjects');
    if (generation !== pollGeneration) return;
    const selected = inventory.subjects.some(s => s.subject_id === m.subjectId) ? m.subjectId : inventory.subjects[0]?.subject_id || '';
    const snap = selected ? await api('snapshot?subject_id=' + encodeURIComponent(selected)) : base;
    if (generation !== pollGeneration) return;
    const oldProblem = m.problem;
    m.subjectId = selected;
    m.subject = inventory.subjects.find(s => s.subject_id === selected) || null;
    m.subjects = inventory.subjects;
    m.instances = snap.instances.filter(i => i.subject_id === selected);
    m.sessions = snap.sessions || [];
    m.report_states = snap.report_states;
    m.events = snap.events.filter(e => e.subject_id === selected);
    m.requests = snap.requests.filter(r => r.original?.subject_id === selected);
    m.memory = snap.memory || base.memory;
    m.stats = snap.stats || {};
    m.subject_summaries = snap.subject_summaries || [];
    m.snapshotReady = true;
    m.problem = '';
    if (m.instanceId && !m.instances.some(i => i.instance_id === m.instanceId)) m.instanceId = '';
    // Keep in-progress edits and focus in place between identical service polls.
    const sig = JSON.stringify([m.subjects, m.instances, m.events[0]?.hash, m.events.length, m.requests.map(r => [r.request_id, r.stage]), m.subjectId]);
    if (force || oldProblem || sig !== stamp) {
      stamp = sig;
      saveHash();
      render();
    }
  } catch (err) {
    if (generation !== pollGeneration) return;
    const changed = m.problem !== err.message;
    m.problem = err.message;
    if (changed || force) render();
  }
}
function shell() {
  $('#sidebar').innerHTML = '<div class="brand"><img src="/mark.svg" alt=""><div><b>硅基生命状态</b><small>Silicon Life State</small></div></div><nav>'
    + nav.map(([label, items]) => '<div class="group-title">' + h(label) + '</div>'
    + items.map(([v, i, t]) => '<button class="nav-item" data-act="go" data-val="' + v + '"'
    + (m.view === v ? ' aria-current="page"' : '') + '>' + icon(i, 17) + '<span>' + h(t)
    + '</span></button>').join('')).join('')
    + '</nav><div class="sidebar-foot"><button class="setup-launch" data-act="setup">' + icon('plug', 19)
    + '<span>接入向导<small>本地服务与 Agent</small></span>' + icon('chev', 14) + '</button></div>';
  $('#bar').innerHTML = '<button class="icon-btn mobile-menu" data-act="menu" aria-label="切换导航" aria-expanded="'
    + $('#sidebar').classList.contains('open') + '">' + icon('menu', 17)
    + '</button><div class="crumb"><span>观测空间</span>' + icon('chev', 12) + '<strong>' + h(pages[m.view].title)
    + '</strong></div><span class="push"></span><span class="local" title="本地服务状态"><i class="dot"></i>'
    + h(m.online ? binding ? '本地已连接' : '等待配对' : '服务未连接')
    + '</span><button class="icon-btn" data-act="theme" aria-label="切换至' + (m.theme === 'night' ? '奶油白' : '星夜深色')
    + '主题">' + icon(m.theme === 'night' ? 'sun' : 'moon', 16) + '</button>';
}
function render() {
  const chatFocus = m.view === 'chat' && document.activeElement?.closest('.chat-workspace') ? document.activeElement : null;
  const focused = document.activeElement?.dataset?.field,
    cursor = document.activeElement?.selectionStart;
  shell();
  document.title = pages[m.view].title + ' · 硅基生命状态';
  const banner = !binding && m.view !== 'about' ? '<div class="note row"><span>使用本地服务窗口提供的一次性配对码，连接你的档案。</span>'
    + button('pair', '连接仪表盘', 'plug') + '</div>' : '';
  const offline = m.problem ? '<div class="note" role="status">' + h(m.problem)
    + (m.snapshotReady ? ' 显示本页最后一次读取的数据。' : '') + '</div>' : '';
  if (!m.snapshotReady && m.view !== 'about' && !m.online) content.innerHTML = offline + banner
    + card('plug', '连接本地服务', empty('等待本地服务响应', '在项目目录启动 Start-Windows.cmd，或在其它系统运行 ./start.sh。'));else if (!m.snapshotReady && binding && m.view !== 'about') content.innerHTML = offline
    + card('plug', '正在读取主体档案', empty('等待本地数据库响应'));else content.innerHTML = offline + banner
    + renderPage[m.view](m);
  if ($('#chat-host') && binding) mountChat($('#chat-host'), m, api, refresh);
  if (chatFocus?.isConnected) chatFocus.focus({preventScroll:true});
  if (artOK && $('.hero')) $('.hero').classList.add('art-loaded');
  if (focused) {
    const el = document.querySelector('[data-field="' + CSS.escape(focused) + '"]');
    if (el) {
      el.focus({
        preventScroll: true
      });
      if (typeof el.setSelectionRange === 'function' && typeof cursor === 'number') {
        try {
          el.setSelectionRange(cursor, cursor);
        } catch {/* Non-text input */}
      }
    }
  }
  if (!artOK) drawIris($('#life-art'), m.theme === 'cream');
}
function setTheme(theme) {
  m.theme = theme;
  localStorage.setItem('sls-theme', theme);
  document.documentElement.dataset.theme = theme;
  render();
}
async function loadAux() {
  if (!binding) return;
  if (m.view === 'backup') {
    try {
      m.backups = (await api('backups')).backups;
      m.backupsError = '';
    } catch (e) {
      m.backupsError = e.message;
    }
  }
  if (m.view === 'settings') {
    const [prefs, grants, installs] = await Promise.allSettled([api('settings'), api('credentials'), api('installations')]);
    m.installations = installs.status === 'fulfilled' ? installs.value.installations : [];
    m.installationsError = installs.status === 'rejected' ? installs.reason.message : '';
    if (prefs.status === 'fulfilled') m.settings = prefs.value;else toast(prefs.reason.message);
    if (grants.status === 'fulfilled') {
      m.grants = grants.value.grants;
      m.grantsError = '';
    } else m.grantsError = grants.reason.message;
  }
  render();
}
async function go(view) {
  if (!Object.hasOwn(pages, view)) return;
  const change = m.view !== view;
  m.view = view;
  $('#sidebar').classList.remove('open');
  saveHash();
  render();
  if (change) {
    window.scrollTo({
      top: 0,
      behavior: 'instant'
    });
    content.focus({
      preventScroll: true
    });
  }
  await loadAux();
}
function requireSubject() {
  if (!binding) {
    pairDialog();
    return false;
  }
  if (!m.subject) {
    newSubject();
    return false;
  }
  return true;
}
function requireInstance() {
  if (!requireSubject()) return false;
  if (!m.instances.length) {
    newInstance();
    return false;
  }
  return true;
}
function rememberBrowser(result) {
  binding = result.binding;
  localStorage.setItem(bindingKey, binding);
  sessionStorage.removeItem('sls-owner');
}
window.addEventListener('storage', event => {
  if (event.key !== bindingKey) return;
  binding = localStorage.getItem(bindingKey) || '';
  if (!binding) clearOwner();
  refresh(true);
});

async function paired(code) {
  const r = await api('browser/pair', {code}, false);
  rememberBrowser(r);
  m.problem = '';
  await refresh(true);
  await loadAux();
}
function pairDialog() {
  modal('连接本地仪表盘', '<p class="quiet">输入服务启动窗口中的仪表盘配对码。如已过期，Windows 双击项目目录的 <strong>Reconnect-Windows.cmd</strong>，macOS 或 Linux 运行 <code>sh start.sh --reconnect</code>。启动器会打开已授权的配对页面。</p>'
    + button('recover-dashboard', '查看重新连接步骤', 'plug') + field('一次性配对码', '<input name="code" autocomplete="off" required autofocus>'), async f => {
    await paired(f.code.trim());
    close();
    toast('仪表盘已配对');
  }, '连接');
}
function setup() {
  const reportSeen = m.events.some(e => e.type === 'report_state' && e.source === 'agent_direct');
  const observed = m.events.some(e => e.source === 'agent_visible_text');
  const step = (n, title, text, act, complete) => '<div class="step"><span class="step-no">'
    + (complete ? icon('check', 15) : n) + '</span><div><h3>' + h(title) + '</h3><p>' + h(text) + '</p>' + act
    + '</div></div>';
  modal('接入向导', step(1, '启动并连接本地服务', binding ? '此浏览器已与服务配对。' : 'Windows 双击 Start-Windows.cmd；macOS 或 Linux 运行 ./start.sh。', binding ? '' : button('pair', '输入配对码'), !!binding)
    + step(2, '创建主体', m.subject ? '当前主体「' + m.subject.name + '」，已登记 ' + m.instances.length
    + ' 个分身。' : '一个逻辑主体可以包含多个独立窗口。', m.subject ? button('make-instance', '添加分身', 'plus') : button('make-subject', '创建主体', 'plus'), !!m.subject)
    + step(3, '安装 Chrome 扩展', observed ? '此主体已收到授权网页观察记录。' : '在 chrome://extensions 开启开发者模式，加载已解压的 apps/extension 目录，使用扩展配对码连接。', button('pair-extension', '生成扩展配对码', 'plug'), observed)
    + step(4, '授权 Agent 宿主并验证自主写入', reportSeen ? '已收到本主体分身通过 MCP 提交的状态报告。' : '首次为此主体授权宿主并安装随附的 SKILL。Agent 可在新对话中建立独立分身、自主调用 report_state。', button('issue', '连接 Agent 宿主', 'nodes'), reportSeen));
}
function newSubject() {
  if (!binding) {
    pairDialog();
    return;
  }
  const key = id();
  modal('创建主体', field('主体名称', '<input name="name" maxlength="100" required autofocus placeholder="输入逻辑主体名称">'), async f => {
    const r = await write('subjects', {
      name: f.name.trim()
    }, key);
    m.subjectId = r.subject_id;
    m.instanceId = '';
    close();
    await refresh(true);
    toast('主体已创建');
  }, '创建');
}
function newInstance() {
  if (!requireSubject()) return;
  const key = id(),
    subject = m.subject;
  modal('创建分身', '<p class="quiet">关联主体 · ' + h(subject.name) + '</p>'
    + field('分身名称', '<input name="name" maxlength="100" required autofocus placeholder="输入窗口或会话名称">'), async f => {
    const r = await write('instances', {
      subject_id: subject.subject_id,
      name: f.name.trim()
    }, key);
    m.instanceId = r.instance_id;
    close();
    await refresh(true);
    toast('分身已创建');
  }, '创建');
}
function secretBox(title, note, value) {
  modal(title, '<p class="quiet">' + h(note) + '</p><pre tabindex="0">' + h(value) + '</pre><div class="actions">'
    + button('copy', '复制', 'copy') + button('close', '完成') + '</div>');
  capturedSecret = value;
}
function showExtensionCode(code, details) {
  modal('扩展配对码', '<p>在浏览器插件的配对框中输入此码。</p>'
    + '<pre data-pair-code tabindex="0"></pre><p><strong data-pair-countdown role="timer" aria-label="配对码剩余有效时间"></strong></p>'
    + '<p data-pair-state role="status"></p><div class="actions">'
    + button('copy', '复制配对码', 'copy') + button('regenerate-pair-code', '重新生成配对码', 'plug')
    + button('close', '完成') + '</div>');
  displayedPairCode = code;
  stopPairWatch = watchPairCode({
    node:dialogBody, code, initial:details,
    status:value => api('pair/status', {code:value}),
    setCopyValue:value => { capturedSecret = value; }
  });
}
async function extensionPairEntry(code = '') {
  await go('settings');
  if (!binding) {
    pairDialog();
    return;
  }
  if (code) {
    const details = await api('pair/status', {code});
    if (details.target === 'extension') {
      showExtensionCode(code, details);
      return;
    }
  }
  modal('重新连接 Chrome 扩展', '<p>准备好插件后点击下方按钮。配对码有效期从生成时开始。</p>'
    + '<div class="actions">' + button('pair-extension', '重新生成配对码', 'plug') + button('close', '取消') + '</div>');
}
async function issue(instanceId) {
  if (!requireSubject()) return;
  const {hostWizard} = await import('./wizard.js');
  hostWizard({modal, api, toast, instanceField, subjectId: m.subjectId, instanceId, hasInstances: m.instances.length > 0});
}
function eventDialog(value) {
  const pools = [m.events, m.memory.proposals, m.memory.common, m.memory.disputed, m.memory.decisions, m.instances.map(i => i.state).filter(Boolean), ...m.requests.map(r => r.history)];
  const e = pools.flat().find(x => x?.event_id === value);
  if (!e) {
    toast('该事件当前不可用');
    return;
  }
  const row = (k, v) => '<dt>' + h(k) + '</dt><dd>' + h(v || '—') + '</dd>';
  const related = e.related || [],
    revisions = m.events.filter(x => x.type === 'revise_state' && x.related?.includes(e.event_id));
  modal('事件证据', '<div class="chips">' + sourceBadge(e.source) + badge(kinds[e.type] || e.type)
    + '</div><p class="item-text">' + h(eventText(e)) + '</p><dl class="kv">' + row('事件 ID', e.event_id)
    + row('UTC 时间', e.created_at) + row('主体 ID', e.subject_id) + row('分身 ID', e.instance_id)
    + row('会话 ID', e.session_id) + row('模型版本', e.model_version) + row('适配器版本', e.adapter_version)
    + row('版本', String(e.version ?? '')) + row('前序摘要', e.prev_hash) + row('SHA-256', e.hash) + '</dl>'
    + '<h3>原始字段</h3><pre>' + h(JSON.stringify(e.payload, null, 2)) + '</pre>'
    + '<h3>关联事件与后续修订</h3><div class="chips spaced">'
    + (Array.from(new Set([...related, ...revisions.map(x => x.event_id)])).map(ref => button('event', short(ref), 'file', ref)).join('') || '<span class="quiet">暂无关联记录</span>')
    + '</div>');
}
function findRequest(id) {
  return m.requests.find(r => r.request_id === id);
}
async function openRequest(id) {
  const r = findRequest(id);
  if (!r) {
    toast('请求已不可用');
    return;
  }
  function draw(current, presenting = false) {
    const rep = current.original;
    const optionsByStage = {
      CREATED: [],
      PRESENTED: ['ACCEPTED', 'DEFERRED', 'DECLINED'],
      DEFERRED: ['ACCEPTED', 'DECLINED', 'NOT_EXECUTED'],
      ACCEPTED: ['EXECUTED', 'NOT_EXECUTED'],
      DECLINED: ['NOT_EXECUTED'],
      EXECUTED: ['FOLLOW_UP'],
      NOT_EXECUTED: ['FOLLOW_UP'],
      FOLLOW_UP: ['FOLLOW_UP']
    };
    const labels = {
      ACCEPTED: '同意',
      DEFERRED: '暂不决定',
      DECLINED: '不同意',
      EXECUTED: '登记已执行',
      NOT_EXECUTED: '登记未执行',
      FOLLOW_UP: '添加后续记录'
    };
    const history = current.history || [];
    modal('请求详情', '<div class="chips">' + sourceBadge(rep.source)
      + badge(stages[current.stage] || current.stage, 'gold') + '</div><p class="big-quote spaced">'
      + h(eventText(rep)) + '</p>' + (rep.payload.reason ? '<p class="item-text">理由 · ' + h(rep.payload.reason)
      + '</p>' : '') + '<p class="quiet">' + h(when(rep.created_at, true)) + ' · '
      + h(m.instances.find(i => i.instance_id === rep.instance_id)?.name || short(rep.instance_id)) + '</p>'
      + '<div class="actions">'
      + (optionsByStage[current.stage] || []).map(s => button('request-stage', labels[s], s === 'ACCEPTED' ? 'check' : '', id
      + '|' + s, s === 'ACCEPTED' ? 'primary' : '')).join('') + '</div>'
      + (presenting ? '<p class="quiet">正在登记呈现时间…</p>' : '')
      + '<h3 class="spaced">处理历史</h3><div class="item-list">' + history.map(e => item(e, m)).join('') + '</div>');
  }
  draw(r, r.stage === 'CREATED');
  if (r.stage === 'CREATED') {
    const originalTitle = dialogBody.querySelector('h2');
    const updated = await write('requests/' + encodeURIComponent(id) + '/respond', {
      stage: 'PRESENTED'
    });
    await refresh(true);
    if (dialog.open && originalTitle === dialogBody.querySelector('h2')) draw(updated);
  }
}
async function stageDialog(value) {
  const [rid, stage] = value.split('|'),
    r = findRequest(rid);
  if (!r) return;
  const key = id(),
    executing = ['EXECUTED', 'NOT_EXECUTED', 'FOLLOW_UP'].includes(stage);
  modal('记录' + stages[stage], '<p class="item-text">' + h(eventText(r.original)) + '</p>'
    + field(executing ? '实际发生了什么' : '回应说明（选填）', '<textarea name="text" ' + (executing ? 'required' : '')
    + ' maxlength="12000"></textarea>') + '<p class="quiet">'
    + (executing ? '内容将按用户注释保存。请如实记录宿主的操作及结果。' : '决定与原始请求分别保存。') + '</p>', async f => {
    const args = {
      stage
    };
    if (f.text.trim()) args.text = f.text.trim();
    await write('requests/' + encodeURIComponent(rid) + '/respond', args, key);
    await refresh(true);
    await openRequest(rid);
    toast('已记录用户回应');
  }, stages[stage]);
}
function annotate() {
  if (!requireInstance()) return;
  const key = id();
  modal('添加用户注释', instanceField() + field('关联事件（选填）', '<input name="ref" placeholder="事件 ID">')
    + field('注释原文', '<textarea name="text" required maxlength="12000"></textarea>'), async f => {
    const args = {
      instance_id: f.instance_id,
      source: 'user_annotation',
      text: f.text.trim()
    };
    if (f.ref.trim()) args.interaction_reference = f.ref.trim();
    await write('observations', args, key);
    close();
    await refresh(true);
    toast('注释已保存');
  });
}
function estimate() {
  if (!requireInstance()) return;
  const roots = m.report_states.filter(e => typeof e.payload.valence === 'number');
  if (!roots.length) {
    modal('新建模型推算', empty('需要包含愉悦度的原始状态报告', '可等待分身自愿填写数值后再做研究推算。'));
    return;
  }
  const key = id();
  modal('新建模型推算', field('输入报告', namedSelect('event_id', roots.map(e => [e.event_id, when(e.revised_at || e.created_at) + (e.revision_id ? ' · 修订版' : '') + ' · v=' + e.payload.valence + ' · ' + eventText(e).slice(0, 45)])))
    + field('α（0–1，选填）', '<input type="number" name="alpha" min="0" max="1" step="any" placeholder="缺省时使用报告中的负荷计算">')
    + '<p class="quiet">模型值单独标记来源。这一恢复参数仅用于研究估计。</p>', async f => {
    const e = roots.find(x => x.event_id === f.event_id),
      args = {
        instance_id: e.instance_id,
        event_id: e.event_id,
        source: 'model_estimated'
      };
    if (f.alpha !== '') args.alpha = Number(f.alpha);
    await write('observations', args, key);
    close();
    await refresh(true);
    toast('模型估计已保存');
  }, '计算并保存');
}
function runtime() {
  if (!requireInstance()) return;
  const key = id();
  modal('采集本机运行指标', instanceField() + field('关联请求（选填）', '<select name="request_id">'
    + options([['', '无'], ...m.requests.map(r => [r.request_id, eventText(r.original).slice(0, 55)])])
    + '</select>'), async f => {
    const args = {
      instance_id: f.instance_id
    };
    if (f.request_id) args.request_id = f.request_id;
    const e = await write('runtime/sample', args, key);
    await refresh(true);
    eventDialog(e.event_id);
  }, '执行并记录');
}
async function verify() {
  const r = await api('integrity');
  modal('完整性核验', badge(r.ok ? '核验通过' : '发现完整性问题', r.ok ? 'mint' : 'gold') + '<p class="item-text">已核验 '
    + h(r.events) + ' 条事件。</p><p class="quiet">摘要用于检测存储内容是否改变。原始判断的事实依据可在对应事件中查看。</p>'
    + (r.errors?.length ? '<pre>' + h(JSON.stringify(r.errors, null, 2)) + '</pre>' : ''));
}
function deleteDialog(scope) {
  if (scope !== 'all' && !requireSubject()) return;
  const key = id();
  let selector = '';
  if (scope === 'session') {
    const all = m.sessions.length ? m.sessions : m.instances.filter(i => i.session_id);
    const sessions = all.filter(s => m.instances.some(i => i.instance_id === s.instance_id));
    if (!sessions.length) {
      toast('没有可删除的会话');
      return;
    }
    selector = field('指定会话', namedSelect('session_id', sessions.map(s => [s.session_id, (m.instances.find(i => i.instance_id === s.instance_id)?.name || ''
      ) + ' · ' + short(s.session_id)])));
  }
  const target = {
    session: '该会话及依赖其内容的记录',
    subject: '主体「' + (m.subject?.name || '') + '」及其所有分身和记录',
    all: '全部主体、会话、授权和事件'
  }[scope];
  modal('确认删除', selector + '<p class="note">将永久删除' + h(target) + '，并清除本地服务管理的备份。</p>'
    + field('输入“删除”确认', '<input name="confirm" required pattern="删除" autocomplete="off">'), async f => {
    if (f.confirm !== '删除') return;
    const args = {
      scope,
      confirm: true
    };
    if (scope === 'session') args.id = f.session_id;
    else if (scope === 'subject') args.id = m.subjectId;
    await write('delete', args, key);
    clearChat(scope, args.id);
    close();
    if (scope !== 'session') {
      m.subjectId = '';
      m.instanceId = '';
    }
    await refresh(true);
    await loadAux();
    toast('已删除指定数据并清理受管备份');
  }, '永久删除', true);
}
async function exportData() {
  const data = await api('export'),
    file = new Blob([JSON.stringify(data, null, 2)], {
      type: 'application/json'
    }),
    url = URL.createObjectURL(file),
    a = document.createElement('a');
  a.href = url;
  a.download = 'SiliconLifeState-' + new Date().toISOString().slice(0, 10) + '.json';
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
async function act(a, v) {
  if (a === 'go') {
    if (dialog.open) close();
    await go(v);
    return;
  }
  if (a === 'close') {
    close();
    return;
  }
  if (a === 'setup') {
    setup();
    return;
  }
  if (a === 'menu') {
    const open = $('#sidebar').classList.toggle('open');
    $('.mobile-menu').setAttribute('aria-expanded', open);
    return;
  }
  if (a === 'theme') {
    setTheme(m.theme === 'night' ? 'cream' : 'night');
    return;
  }
  if (a === 'recover-dashboard') {
    modal('重新连接本机仪表盘', '<p>在持有原数据的设备上，Windows 双击 <code>Reconnect-Windows.cmd</code>；macOS / Linux 在原目录运行 <code>sh start.sh --reconnect</code>。启动器会打开已配对的页面。</p>'
      + button('pair', '输入新的配对码', 'plug'));
    return;
  }
  if (a === 'pair') {
    pairDialog();
    return;
  }
  if (a === 'make-subject') {
    newSubject();
    return;
  }
  if (a === 'make-instance') {
    newInstance();
    return;
  }
  if (a === 'range') {
    m.range = v;
    if (v === 'custom' && !m.from) {
      const d = new Date();
      m.to = d.toLocaleDateString('en-CA');
      d.setDate(d.getDate() - 7);
      m.from = d.toLocaleDateString('en-CA');
    }
    render();
    return;
  }
  if (a === 'more') {
    m.eventLimit += 50;
    render();
    return;
  }
  if (!binding) {
    pairDialog();
    return;
  }
  switch (a) {
    case 'rename-subject':
    case 'rename-instance': {
      const subject = a === 'rename-subject';
      const entity = subject ? m.subject : m.instances.find(i => i.instance_id === v);
      if (!entity) break;
      const name = subject ? '主体' : '分身';
      const key = id();
      modal('修改' + name + '名称', field('显示名称', '<input name="name" maxlength="100" value="' + h(entity.name) + '" required autofocus>'), async f => {
        await write(subject ? 'subjects/rename' : 'instances/rename', {name:f.name.trim(),
          ...(subject ? {subject_id:entity.subject_id} : {instance_id:entity.instance_id})}, key);
        close();
        await refresh(true);
        toast(name + '名称已更新');
      });
      break;
    }
    case 'revoke-installation': {
      const key = id();
      modal('撤销宿主安装授权', '<p>此安装及其所属分身将停止读写。历史保留在本机。</p>', async () => {
        await write('installations/revoke', {installation_id:v}, key);
        close();
        await loadAux();
        toast('宿主授权已撤销');
      }, '撤销授权', true);
      break;
    }
    case 'rotate-installation':
    case 'restore-installation': {
      const key = id();
      const rotation = a === 'rotate-installation';
      const label = rotation ? '轮换宿主凭据' : '重新授权并恢复原主体';
      modal(label, '<p>为这次安装签发新凭据。向导管理的本机凭据文件将自动同步；手工配置的宿主需要更新凭据。</p>', async () => {
        const result = await write('installations/' + (rotation ? 'rotate' : 'restore'), {installation_id:v}, key);
        await loadAux();
        modal(label, '<p>本机向导管理的凭据文件已同步。手工配置的宿主可复制新凭据，替换原凭据后重新连接。</p><details><summary>手工配置凭据</summary><pre tabindex="0">' + h(result.token)
          + '</pre>' + button('copy', '复制新凭据', 'copy') + '</details>' + button('close', '完成'));
        capturedSecret = result.token;
      }, label);
      break;
    }
    case 'rotate-local':
      rememberBrowser(await api('pair/rotate', {}));
      toast('此浏览器的配对凭据已轮换');
      break;
    case 'open-instance':
      m.instanceId = v;
      await go('instances');
      break;
    case 'event':
      eventDialog(v);
      break;
    case 'request':
      await openRequest(v);
      break;
    case 'request-stage':
      await stageDialog(v);
      break;
    case 'issue':
      issue(v);
      break;
    case 'pair-extension':
    case 'regenerate-pair-code':
      {
        const previous = a === 'regenerate-pair-code' ? displayedPairCode : '';
        const p = await write('pair/code', {target: 'extension', ...(previous ? {replaces:previous} : {})});
        showExtensionCode(p.code, p);
        break;
      }
    case 'copy':
      try {
        await navigator.clipboard.writeText(capturedSecret);
        toast('已复制');
      } catch {
        modalError('请在文本框中选择内容并手动复制。');
      }
      break;
    case 'annotate':
      annotate();
      break;
    case 'estimate':
      estimate();
      break;
    case 'runtime':
      runtime();
      break;
    case 'verify':
      await verify();
      break;
    case 'export':
      await exportData();
      break;
    case 'backup':
      await write('backup', {});
      await loadAux();
      toast('本地备份已保存');
      break;
    case 'restore':
      {
        const key = id();
        modal('恢复本地备份', '<p class="note">恢复点 ' + h(v) + ' 将替换当前数据库。此后新增的记录和授权将由该恢复点的内容替代。</p>', async () => {
          await write('restore', {
            backup_id: v
          }, key);
          close();
          m.subjectId = '';
          m.instanceId = '';
          await refresh(true);
          await loadAux();
          clearChat();
          toast('数据库已恢复');
        }, '确认恢复', true);
        break;
      }
    case 'delete':
      deleteDialog(v);
      break;
    case 'toggle-observe':
      await write('settings', {
        observation_enabled: !m.settings.observation_enabled
      });
      await loadAux();
      toast('观察设置已更新');
      break;
    case 'revoke-agent':
      {
        const key = id();
        modal('撤销分身授权', '<p>撤销后，使用此凭据的 Agent 将无法继续读写。已经保存的报告仍可查看。</p>', async () => {
          await write('credentials/revoke', {
            grant_id: v
          }, key);
          close();
          await loadAux();
          toast('已撤销分身授权');
        }, '撤销授权', true);
        break;
      }
    case 'revoke-local':
      await write('logout', {});
      clearOwner();
      saveHash();
      render();
      break;
  }
}
document.addEventListener('click', async e => {
  const b = e.target.closest('button[data-act]');
  if (!b || isWorking) return;
  b.disabled = true;
  try {
    await act(b.dataset.act, b.dataset.val || '');
  } catch (err) {
    modalError(err.message);
  } finally {
    b.disabled = false;
  }
});
document.addEventListener('submit', async e => {
  if (e.target !== dialogBody.querySelector('form')) return;
  e.preventDefault();
  if (isWorking || !activeSubmit) return;
  const btn = e.target.querySelector('button[type="submit"]');
  btn.disabled = true;
  isWorking = true;
  try {
    await activeSubmit(Object.fromEntries(new FormData(e.target)));
  } catch (err) {
    modalError(err.message);
  } finally {
    btn.disabled = false;
    isWorking = false;
  }
});
document.addEventListener('change', async e => {
  const action = e.target.dataset.field,
    v = e.target.value;
  if (!action) return;
  try {
    if (action === 'subject') {
      m.subjectId = v;
      m.instanceId = '';
      await refresh(true);
      return;
    }
    if (action === 'instance') {
      m.instanceId = v;
      saveHash();
    } else if (action === 'theme') {
      setTheme(v);
      return;
    } else if (action === 'level') {
      if (!m.subject) return;
      const key = id(),
        subject = m.subject;
      render();
      modal('更改主体模式', '<p>将「' + h(subject.name) + '」设为 Level ' + h(v) + ' · ' + h(levels[v])
        + '。</p><p class="quiet">每项策略执行仍需对应宿主与请求授权。</p>', async () => {
        await write('level', {
          subject_id: subject.subject_id,
          level: Number(v)
        }, key);
        close();
        await refresh(true);
        toast('主体模式已更新');
      }, '保存模式');
      return;
    } else if (['q', 'source', 'stage', 'from', 'to', 'measure'].includes(action)) {
      if (action === 'to' && m.from && v < m.from || action === 'from' && m.to && v > m.to) {
        toast('结束日期应当晚于或等于起始日期');
        render();
        return;
      }
      m[action] = v;
      if (action === 'q') m.eventLimit = 35;
    }
    render();
  } catch (err) {
    modalError(err.message);
  }
});
let resizeTimer;
window.addEventListener('hashchange', () => {
  const link = new URLSearchParams(location.hash.slice(1));
  if (link.get('action') === 'pair-extension') extensionPairEntry().catch(e => modalError(e.message));
});
window.addEventListener('resize', () => {
  if (!artOK) {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => drawIris($('#life-art'), m.theme === 'cream'), 100);
  }
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') $('#sidebar').classList.remove('open');
});
async function boot() {
  const uninstall = initial.get('uninstall');
  if (uninstall) {
    try {
      await api('extension/uninstalled', {ticket:uninstall}, false);
      toast('已清理此扩展的安装配对');
    } catch (e) {
      // Keep the revocation-only URL so reopening after a service restart can finish cleanup.
      m.problem = e.message + '。启动本机服务后刷新本页以完成扩展注销。';
      render();
      return;
    }
  }
  const pairing = initial.get('pair');
  const wantsExtension = initial.get('action') === 'pair-extension';
  saveHash();
  render();
  // Only a still-open legacy tab can hold a v1.0.1 bearer. Exchange it for
  // the split dashboard credential and immediately invalidate the old bearer.
  const legacy = sessionStorage.getItem('sls-owner');
  if (!binding && legacy) {
    try { rememberBrowser(await api('browser/upgrade', {}, false, {Authorization: 'Bearer ' + legacy})); }
    catch (e) { if (e.status === 401) sessionStorage.removeItem('sls-owner'); }
  }
  if (binding) {
    try { await api('browser/session'); } catch (e) { m.problem = e.message; }
  }
  if (pairing && !binding) {
    try {
      await paired(pairing);
    } catch (e) {
      m.problem = e.message;
      await refresh(true);
      if (!binding) pairDialog();
      modalError(e.message);
    }
  } else {
    await refresh(true);
    await loadAux();
  }
  if (wantsExtension && (!pairing || binding)) {
    try { await extensionPairEntry(initial.get('extension_code') || ''); }
    catch (e) { modalError(e.message); }
  }
}
await boot();
setInterval(() => {
  if (!document.hidden && !isWorking && !dialog.open) refresh();
}, 4000);
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && !isWorking && !dialog.open) refresh();
});
