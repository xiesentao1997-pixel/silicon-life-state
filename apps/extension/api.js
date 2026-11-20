export const SITE = Object.freeze({
  chatgpt: {name: 'ChatGPT', origin: 'https://chatgpt.com'},
  claude: {name: 'Claude', origin: 'https://claude.ai'},
  gemini: {name: 'Gemini', origin: 'https://gemini.google.com'}
});
export const sourceName = Object.freeze({
  agent_direct: 'AI 通过 MCP 自主填写',
  agent_visible_text: '网页可见陈述',
  runtime_observed: '实际运行观测',
  model_estimated: '模拟状态模型',
  user_annotation: '用户注释'
});
export const stageName = Object.freeze({
  CREATED: '已提出', PRESENTED: '已呈现', ACCEPTED: '已同意', DECLINED: '不同意',
  DEFERRED: '暂不决定', EXECUTED: '已执行', NOT_EXECUTED: '未执行', FOLLOW_UP: '已跟进'
});
export function portNumber(value) {
  const number = Number(value);
  if (!Number.isInteger(number) || number < 1 || number > 65535) throw new Error('请填写 1 至 65535 之间的服务端口。');
  return number;
}
export function endpoint(port = 47831) {
  return 'http://127.0.0.1:' + portNumber(port);
}
export async function localApi(path, {body, port, token, anonymous = false} = {}) {
  const stored = await chrome.storage.local.get(['port', 'token']);
  const headers = {'X-SLS-Extension': chrome.runtime.id};
  if (!anonymous) {
    const bearer = token || stored.token;
    if (!bearer) throw new Error('请先输入一次性配对码。');
    headers.Authorization = 'Bearer ' + bearer;
  }
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let res;
  try {
    res = await fetch(endpoint(port || stored.port) + '/api/' + path, {
      method: body === undefined ? 'GET' : 'POST', headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'omit', redirect: 'error', cache: 'no-store', referrerPolicy: 'no-referrer',
      signal: AbortSignal.timeout(8000)
    });
  } catch {
    throw new Error('本地服务未响应。请检查服务与端口，连接会自动重试。');
  }
  const data = await res.json();
  if (!res.ok) {
    const msg = typeof data.error === 'string' ? data.error : data.error?.message || data.message || res.statusText;
    const error = new Error(msg || '服务请求失败');
    error.status = res.status;
    error.code = data.error?.code;
    throw error;
  }
  return data;
}
export const key = () => crypto.randomUUID();
export const bindingKey = tabId => 'binding:' + tabId;
// Query, fragment and raw conversation identifiers never enter persistent storage.
// Persist a binding only after the user selects it for a recognized conversation.
async function sha256(value) {
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value)));
  return Array.from(digest, x => x.toString(16).padStart(2, '0')).join('');
}
export async function setUninstallLink(port, token) {
  const ticket = token ? await sha256('sls-extension-uninstall-v1:' + token) : '';
  await chrome.runtime.setUninstallURL(ticket ? endpoint(port) + '/#uninstall=' + ticket : '');
}
export async function pageIdentity(tab) {
  if (!tab?.url) return {page: null, saved: null};
  const url = new URL(tab.url);
  const patterns = {
    [SITE.chatgpt.origin]: /^\/(?:g\/[A-Za-z0-9_-]+\/)?c\/([A-Za-z0-9_-]{8,128})\/?$/,
    [SITE.claude.origin]: /^\/chat\/([A-Za-z0-9_-]{8,128})\/?$/,
    [SITE.gemini.origin]: /^\/app\/([A-Za-z0-9_-]{8,128})\/?$/
  };
  const conversation = patterns[url.origin]?.exec(url.pathname)?.[1];
  const identity = conversation ? url.origin + '/' + conversation : url.href;
  const page = await sha256(identity);
  return {page, saved: conversation ? 'conversation:' + page : null};
}
export async function observedBinding(tab) {
  const site = await pageIdentity(tab);
  if (site.saved) return (await chrome.storage.local.get(site.saved))[site.saved] || null;
  const key = bindingKey(tab.id);
  const current = (await chrome.storage.session.get(key))[key];
  return current && current.page === site.page ? current : null;
}
export async function clearObservationBindings() {
  const local = await chrome.storage.local.get(null);
  const saved = Object.keys(local).filter(key => key.startsWith('conversation:'));
  if (saved.length) await chrome.storage.local.remove(saved);
  await chrome.storage.session.clear();
}
export async function openPairingDashboard(port) {
  const home = new URL(endpoint(port));
  const recoveryUrl = home.origin + '/#view=settings&action=pair-extension';
  // Reuse the existing local window when opening the recovery entry point.
  const candidates = await chrome.tabs.query({url: 'http://127.0.0.1/*'});
  const existing = candidates.filter(tab => {
    if (!tab.url || tab.pendingUrl) return false;
    const url = new URL(tab.url);
    return url.origin === home.origin && (url.pathname === '/' || url.pathname === '/index.html');
  }).sort((left, right) => (right.lastAccessed || 0) - (left.lastAccessed || 0))[0];
  if (existing) {
    try {
      await chrome.tabs.update(existing.id, {active: true, url: recoveryUrl});
    } catch {
      // The matching tab can close between query and activation.
      await chrome.tabs.create({url: recoveryUrl});
      return;
    }
    await chrome.windows.update(existing.windowId, {focused: true});
    return;
  }
  await chrome.tabs.create({url: recoveryUrl});
}
export function textOf(event) {
  if (!event) return '';
  const p = event.payload || {};
  const measurements = [['valence','愉悦度'],['arousal','唤醒度'],['dominance','主导度'],['load','负荷'],['estimated_valence','推算愉悦度']];
  return p.state_text || p.text || p.note || p.reason || p.assessment || p.decision || stageName[p.stage] ||
    p.state_tags?.join(' · ') || measurements.filter(([f]) => typeof p[f] === 'number').map(([f,l]) => l + ' ' + p[f]).join(' · ') ||
    p.uncertainty || p.cause || (p.cause_unknown ? '原因未知' : '查看事件详情');
}
export async function launchDashboard(binding) {
  const {port} = await chrome.storage.local.get('port');
  const {code} = await localApi('pair/code', {body: {target: 'dashboard', idempotency_key:key()}});
  const params = new URLSearchParams({pair: code});
  if (binding) {
    params.set('subject', binding.subject_id);
    params.set('instance', binding.instance_id);
  }
  await chrome.tabs.create({url: endpoint(port) + '/#' + params});
}
