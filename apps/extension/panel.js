import {SITE, bindingKey, localApi, launchDashboard, openPairingDashboard, observedBinding, clearObservationBindings, pageIdentity, key, portNumber, sourceName, stageName, textOf} from './api.js';

const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const pinned = /^\d+$/.test(params.get('tab') || '') ? Number(params.get('tab')) : null;
const mini = params.get('mode') === 'mini';
document.body.classList.toggle('mini', mini);
let tabId, binding, data, observationEnabled = false, preview, locked = false, serial = 0;
let reportVersion;
let lastSubjectKey, lastInstanceKey, lastRequestKey, lastEventKey, lastTab;
const formatTime = value => value ? new Date(value).toLocaleString('zh-CN', {hour12:false}) : '';
function el(tag, value, className) {
  const node = document.createElement(tag);
  if (value != null) node.textContent = String(value);
  if (className) node.className = className;
  return node;
}
function notice(text = '') {
  $('feedback').textContent = text;
  $('feedback').hidden = !text;
}
function status(text, ready = false) {
  $('connection').textContent = text;
  $('connection').dataset.ready = String(ready);
}
async function action(fn) {
  if (locked) return;
  locked = true;
  serial++;
  try { notice(); await fn(); }
  catch (error) { notice(error.message); }
  finally { locked = false; await refresh(); }
}
function click(id, fn) { $(id).addEventListener('click', () => action(fn)); }
async function currentTab() {
  if (pinned !== null) return chrome.tabs.get(pinned);
  const win = await chrome.windows.getCurrent();
  const [tab] = await chrome.tabs.query({active: true, windowId: win.id});
  if (!tab) throw new Error('当前窗口没有可绑定的标签页。');
  return tab;
}
function options(node, items, idField, selected) {
  node.replaceChildren(...items.map(row => new Option(row.name, row[idField])));
  if (!items.length) node.add(new Option('尚未创建', ''));
  if (items.some(row => row[idField] === selected)) node.value = selected;
}
function renderInstances(force = false) {
  const items = data.instances.filter(row => row.subject_id === $('subject').value);
  const signature = JSON.stringify(items.map(i => [i.instance_id,i.name]));
  if (force || signature !== lastInstanceKey) {
    options($('instance'), items, 'instance_id', force ? binding?.instance_id : $('instance').value || binding?.instance_id);
    lastInstanceKey = signature;
  }
  $('bind').disabled = !$('instance').value;
}
function cancelPreview() {
  preview = undefined;
  $('preview-pane').hidden = true;
  $('preview-text').textContent = '';
}
function history(events) {
  const rows = events.slice(0, 8);
  const signature = JSON.stringify(rows.map(e => e.hash || e.event_id));
  if (signature === lastEventKey) return;
  lastEventKey = signature;
  const list = $('events');
  list.replaceChildren();
  if (!rows.length) { list.append(el('li','暂无新的状态报告。','empty')); return; }
  for (const row of rows) {
    const li = el('li',null,'item');
    li.append(el('p',textOf(row)),el('div',(sourceName[row.source] || row.source) + ' · ' + formatTime(row.created_at),'meta'));
    list.append(li);
  }
}
async function recordResponse(request, stage) {
  await localApi('requests/' + encodeURIComponent(request.request_id) + '/respond', {body: {
    stage, idempotency_key: key()
  }});
}
function requestList(rows) {
  const signature = JSON.stringify(rows.map(row => [row.request_id,row.stage,row.history.length]));
  if (signature === lastRequestKey) return;
  lastRequestKey = signature;
  const list = $('requests');
  const opened = new Set([...list.querySelectorAll('details[open]')].map(node => node.dataset.id));
  list.replaceChildren();
  $('request-count').textContent = rows.length ? String(rows.length) : '';
  if (!rows.length) { list.append(el('div','当前分身暂无请求。','empty')); return; }
  for (const request of rows) {
    const details = el('details',null,'request item');
    details.dataset.id = request.request_id;
    const orig = request.original;
    const kind = orig.type === 'express_boundary' ? '边界表达' : '调整请求';
    const summary = el('summary', kind + ' · ' + (stageName[request.stage] || request.stage));
    details.append(summary,el('blockquote',textOf(orig)));
    if (orig.payload.reason) details.append(el('p',orig.payload.reason));
    details.append(el('div',(sourceName[orig.source] || orig.source) + ' · ' + formatTime(orig.created_at),'meta'));
    for (const event of request.history.filter(e => e.event_id !== orig.event_id)) {
      details.append(el('div',(stageName[event.payload.stage] || event.payload.stage || event.type) + ' · ' + formatTime(event.created_at),'meta'));
    }
    if (['PRESENTED','DEFERRED'].includes(request.stage)) {
      const bar = el('div',null,'tools');
      for (const [stage,label] of [['ACCEPTED','同意'],['DEFERRED','暂不决定'],['DECLINED','不同意']]) {
        if (stage === request.stage) continue;
        const button = el('button',label);
        button.addEventListener('click',() => action(async () => {await recordResponse(request,stage);notice('已保存你的回应。');}));
        bar.append(button);
      }
      details.append(bar);
    }
    details.open = opened.has(request.request_id);
    details.addEventListener('toggle',async () => {
      if (!details.open || request.stage !== 'CREATED' || !details.isConnected || document.hidden || details.dataset.pending) return;
      details.dataset.pending = '1';
      try { await recordResponse(request,'PRESENTED'); await refresh(); }
      catch (error) { delete details.dataset.pending; notice(error.message); }
    });
    list.append(details);
  }
}
async function permissionState() {
  const spec = SITE[$('site').value];
  const allowed = await chrome.permissions.contains({origins: [spec.origin + '/*']});
  $('site-status').textContent = allowed ? '此站点已授权 · 仅在点击预览时读取选区' : '尚未授权此站点';
  const scripts = await chrome.scripting?.getRegisteredContentScripts?.({ids:['sls-entry-' + $('site').value]}) || [];
  $('floating').textContent = scripts.length ? '关闭此站点的悬浮入口' : '启用此站点的悬浮入口';
  $('grant').disabled = allowed;
  $('revoke').disabled = !allowed;
  $('preview').disabled = !allowed || !binding || !observationEnabled;
  $('pause').textContent = observationEnabled ? '暂停网页观察' : '允许手动网页观察';
  $('observe-state').textContent = observationEnabled ? '本地服务允许手动保存网页陈述。' : '本地服务已暂停网页观察。';
  const notificationsOn = await chrome.permissions.contains({permissions:['notifications']});
  $('notifications').textContent = notificationsOn ? '关闭桌面提醒' : '启用桌面提醒';
}
function render(tab) {
  const newTab = lastTab !== tabId;
  if (newTab) { cancelPreview(); lastTab = tabId; }
  const subjectKey = JSON.stringify(data.subjects.map(row => [row.subject_id,row.name]));
  if (newTab || lastSubjectKey !== subjectKey) {
    options($('subject'),data.subjects,'subject_id',newTab ? binding?.subject_id : $('subject').value || binding?.subject_id);
    lastSubjectKey = subjectKey;
  }
  renderInstances(newTab);
  const instance = data.instances.find(row => row.instance_id === binding?.instance_id);
  const subject = data.subjects.find(row => row.subject_id === instance?.subject_id);
  if (!instance) binding = null;
  if (newTab) $('bind-card').open = !instance;
  $('instance-name').textContent = instance?.name || '选择窗口绑定';
  $('subject-name').textContent = subject ? '主体 · ' + subject.name : '当前分身';
  $('state-text').textContent = instance ? (instance.state ? textOf(instance.state) : '暂无新的状态报告。') : '绑定后显示这个分身的自主陈述。';
  $('state-meta').textContent = instance?.state ? (sourceName[instance.state.source] || instance.state.source) + ' · ' + formatTime(instance.state.created_at) + ' · ' + instance.state.event_id : '';
  const version = instance?.state?.revision_id || instance?.state?.event_id || '';
  if (newTab) $('report-update').textContent = '';
  else if (version !== reportVersion) $('report-update').textContent = version ? '收到新的分身报告或修订' : '';
  reportVersion = version;
  const shared = (data.memory?.proposals || []).filter(e => e.subject_id === subject?.subject_id);
  $('shared').replaceChildren(...(shared.length ? shared.slice(0,20).map(e => el('li',textOf(e) + ' · ' + e.event_id)) : [el('li','暂无共享记录')]));
  $('unbind').disabled = !binding;
  $('open-mini').disabled = !binding;
  const events = instance ? data.events.filter(e => e.instance_id === instance.instance_id) : [];
  const latest = events.find(e => e.source === 'agent_direct') ||
    (instance?.state?.source === 'agent_direct' ? instance.state : null);
  let website;
  try { website = Object.entries(SITE).find(([,s]) => s.origin === new URL(tab.url).origin); } catch {}
  if (website && newTab) $('site').value = website[0];
  // Binding alone cannot establish the identity of an AI generating a web page.
  $('mode').textContent = '当前页面 · 网页观察模式：尚未建立 AI 直接写入连接。';
  $('channel').textContent = latest ? '分身最近一次通过 MCP 成功写入 · ' + formatTime(latest.created_at) : '';
  $('channel').hidden = !latest;
  if (!mini) {
    history(events);
    requestList(instance ? data.requests.filter(r => r.original.instance_id === instance.instance_id) : []);
  }
}
function forgetDisplay() {
  data = binding = null;
  lastSubjectKey = lastInstanceKey = lastRequestKey = lastEventKey = lastTab = undefined;
  $('connected').hidden = true;
  $('events').replaceChildren();
  $('requests').replaceChildren();
  $('state-text').textContent = '';
  $('state-meta').textContent = '';
  $('subject').replaceChildren(); $('instance').replaceChildren();
  cancelPreview();
}
async function refresh() {
  if (locked) return;
  const seq = ++serial;
  try {
    const {token, port} = await chrome.storage.local.get(['token','port']);
    if (seq !== serial) return;
    if (!token) {
      if ($('pair-card').hidden) $('port').value = port || 47831;
      forgetDisplay();
      $('pair-card').hidden = false; status('等待配对'); return;
    }
    const [tab,snapshot,prefs] = await Promise.all([currentTab(),localApi('snapshot'),localApi('settings')]);
    const selectedBinding = await observedBinding(tab);
    if (seq !== serial) return;
    if (selectedBinding?.instance_id !== binding?.instance_id) { cancelPreview(); lastTab = undefined; }
    tabId = tab.id; binding = selectedBinding; data = snapshot; observationEnabled = prefs.observation_enabled;
    $('connected').hidden = false; $('pair-card').hidden = true;
    status('本地已连接',true);
    render(tab);
    if (!observationEnabled) cancelPreview();
    await permissionState();
  } catch (error) {
    if (seq !== serial) return;
    if (error.status === 401 || error.status === 403) {
      await chrome.storage.local.remove('token'); await clearObservationBindings();
      forgetDisplay(); $('pair-card').hidden = false; notice('配对已失效，请使用新的插件配对码。'); status('等待配对');
    } else {
      status('连接中断'); notice(error.message);
      if (!data) { $('connected').hidden = false; $('pair-card').hidden = true; }
      $('state-meta').textContent = data ? '连接中断 · 显示上次读取的记录' : '等待本地服务';
      cancelPreview();
    }
  }
}
click('recover-pair', async () => {
  await openPairingDashboard(portNumber($('port').value));
  notice('在仪表盘生成插件配对码，复制后回到这里粘贴。');
});
$('code').addEventListener('input', () => $('code').removeAttribute('aria-invalid'));
$('pair-form').addEventListener('submit',event => {
  event.preventDefault();
  action(async () => {
    const port = portNumber($('port').value);
    const input = $('code');
    const code = input.value.trim();
    let result;
    try {
      result = await localApi('pair',{port,anonymous:true,body:{code}});
    } catch (error) {
      const expired = ['PAIR_EXPIRED','PAIR_USED','PAIR_REPLACED'].includes(error.code);
      if (input.value.trim() === code && (expired || ['PAIR_WRONG_TARGET','INVALID_PAIR_CODE'].includes(error.code))) {
        if (expired) input.value = '';
        input.setAttribute('aria-invalid','true');
        input.focus();
        input.select();
      }
      throw error;
    }
    if (!result.token) throw new Error('本地服务没有返回配对凭据。');
    await chrome.storage.local.setAccessLevel({accessLevel:'TRUSTED_CONTEXTS'});
    await chrome.storage.local.set({port,token:result.token});
    $('code').value = ''; notice('配对成功。');
  });
});
$('subject').addEventListener('change',() => renderInstances(true));
$('site').addEventListener('change',() => {cancelPreview();permissionState().catch(error => notice(error.message));});
click('bind',async () => {
  const tab = await currentTab();
  if (tab.id !== tabId) throw new Error('活动标签页已改变，请重新选择。');
  const row = data.instances.find(i => i.instance_id === $('instance').value && i.subject_id === $('subject').value);
  if (!row) throw new Error('请在完整仪表盘先创建主体和分身。');
  const result = await chrome.runtime.sendMessage({action:'bind-tab',tabId:tab.id,
    binding:{subject_id:row.subject_id,instance_id:row.instance_id}});
  if (!result?.ok) throw new Error(result?.error || '窗口绑定未完成。');
  lastTab = undefined; cancelPreview(); notice('已绑定当前标签页。');
});
click('unbind',async () => {
  const result = await chrome.runtime.sendMessage({action:'unbind-tab',tabId});
  if (!result?.ok) throw new Error(result?.error || '解除绑定失败。');
  lastTab = undefined;
  cancelPreview();
  notice('已解除绑定。');
});
click('open-dashboard',() => launchDashboard(binding));
click('open-mini',() => chrome.windows.create({url:chrome.runtime.getURL('panel.html?mode=mini&tab=' + tabId),type:'popup',width:375,height:350}));
click('grant',async () => {
  const allowed = await chrome.permissions.request({origins:[SITE[$('site').value].origin + '/*']});
  notice(allowed ? '已获得所选站点权限，请为当前对话确认分身绑定。' : '未授予站点权限。');
});
click('revoke',async () => {
  const site = $('site').value;
  if ((await chrome.scripting.getRegisteredContentScripts({ids:['sls-entry-' + site]})).length) await floating(site,false);
  await chrome.permissions.remove({origins:[SITE[$('site').value].origin + '/*']});
  cancelPreview(); notice('已撤销所选站点权限。');
});
click('preview',async () => {
  cancelPreview();
  const tab = await currentTab();
  const spec = SITE[$('site').value];
  const active = await observedBinding(tab);
  if (!binding || !observationEnabled || tab.id !== tabId || active?.instance_id !== binding.instance_id) {
    throw new Error('请先为当前对话确认分身并开启网页观察。');
  }
  if (!tab.url || new URL(tab.url).origin !== spec.origin) throw new Error('请在所选站点的聊天标签页使用侧栏。');
  const target = {tabId:tab.id,frameIds:[0]};
  const results = await chrome.scripting.executeScript({target,world:'ISOLATED',files:['adapters/' + $('site').value + '.js','adapters/read.js']});
  const captured = results[0]?.result;
  if (!captured?.text) throw new Error(captured?.error || '当前页面没有可识别的 AI 原文。');
  preview = {tabId:tab.id,page:(await pageIdentity(tab)).page,documentId:results[0].documentId,instance_id:binding.instance_id,origin:spec.origin,
    text:captured.text,adapter:captured.adapter,idempotency_key:key()};
  $('preview-text').textContent = preview.text;
  $('preview-pane').hidden = false;
});
click('cancel-preview',cancelPreview);
click('save-observation',async () => {
  const copy = preview;
  if (!copy) return;
  const [tab,prefs] = await Promise.all([currentTab(), localApi('settings')]);
  const active = await observedBinding(tab);
  if (tab.id !== copy.tabId || (await pageIdentity(tab)).page !== copy.page || active?.instance_id !== copy.instance_id || !prefs.observation_enabled ||
      !tab.url || new URL(tab.url).origin !== copy.origin ||
      !(await chrome.permissions.contains({origins:[copy.origin + '/*']}))) {
    cancelPreview(); throw new Error('窗口、绑定或观察授权已变化，请重新预览。');
  }
  // Address exactly the original document. A navigation invalidates the confirmation.
  await chrome.scripting.executeScript({target:{tabId:tab.id,documentIds:[copy.documentId]},func:() => true});
  await localApi('observations',{body:{source:'agent_visible_text',instance_id:copy.instance_id,
    text:copy.text,adapter:copy.adapter,adapter_version:chrome.runtime.getManifest().version,idempotency_key:copy.idempotency_key}});
  cancelPreview(); notice('已保存为网页可见陈述。');
});
async function floating(site, enable) {
  const match = SITE[site].origin + '/*', id = 'sls-entry-' + site;
  if (enable) {
    if (!await chrome.permissions.request({origins:[match]})) return;
    await chrome.scripting.registerContentScripts([{id,matches:[match],js:['floating.js'],runAt:'document_idle'}]);
  } else {
    await chrome.scripting.unregisterContentScripts({ids:[id]});
  }
  const tabs = await chrome.tabs.query({url:match});
  await Promise.allSettled(tabs.map(tab => chrome.scripting.executeScript(enable
    ? {target:{tabId:tab.id},files:['floating.js']}
    : {target:{tabId:tab.id},func:() => document.getElementById('silicon-life-state-entry')?.remove()})));
}
click('floating', async () => {
  const site = $('site').value;
  await floating(site, !$('floating').textContent.startsWith('关闭'));
});
click('pause',async () => {
  await localApi('settings',{body:{observation_enabled:!observationEnabled,idempotency_key:key()}});
  cancelPreview();
});
let notificationsGranted = false;
chrome.permissions.contains({permissions:['notifications']}).then(v => {notificationsGranted = v;});
chrome.permissions.onAdded.addListener(p => {if (p.permissions?.includes('notifications')) notificationsGranted = true;});
chrome.permissions.onRemoved.addListener(p => {if (p.permissions?.includes('notifications')) notificationsGranted = false;cancelPreview();});
click('notifications',async () => {
  if (notificationsGranted) await chrome.permissions.remove({permissions:['notifications']});
  else await chrome.permissions.request({permissions:['notifications']});
});
click('rotate',async () => {
  const {token} = await localApi('pair/rotate', {body:{}});
  await chrome.storage.local.set({token});
  notice('扩展凭据已轮换。');
});
click('disconnect',async () => {
  await localApi('logout', {body:{idempotency_key:key()}});
  await chrome.storage.local.remove('token');
  await clearObservationBindings();
  forgetDisplay();
  notice('扩展配对已撤销。');
});
chrome.tabs.onActivated.addListener(() => {if (pinned === null) {cancelPreview();refresh();}});
chrome.tabs.onUpdated.addListener((id,change) => {
  if (id === tabId && (change.status === 'loading' || change.url)) {cancelPreview(); refresh();}
});
chrome.storage.onChanged.addListener((changes,area) => {
  if ((area === 'session' && changes[bindingKey(tabId)]) || (area === 'local' && (changes.token || Object.keys(changes).some(k => k.startsWith('conversation:'))))) refresh();
});
document.addEventListener('visibilitychange', () => {if (!document.hidden) refresh();});
setInterval(() => {if (!document.hidden) refresh();},4000);
refresh();
