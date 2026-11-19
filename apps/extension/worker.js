import {localApi, bindingKey, launchDashboard} from './api.js';

// No background reader runs on chat pages. This worker only polls the paired local service.
async function install() {
  await chrome.storage.local.setAccessLevel({accessLevel: 'TRUSTED_CONTEXTS'});
  await chrome.sidePanel.setPanelBehavior({openPanelOnActionClick: true});
  await chrome.alarms.create('requests', {periodInMinutes: 1});
}
chrome.runtime.onInstalled.addListener(() => install().catch(console.warn));
chrome.runtime.onStartup.addListener(() => install().catch(console.warn));
chrome.tabs.onRemoved.addListener(tab => chrome.storage.session.remove(bindingKey(tab)));
async function updateRequests() {
  const {token} = await chrome.storage.local.get('token');
  if (!token) {
    await chrome.action.setBadgeText({text: ''});
    return;
  }
  try {
    const {requests} = await localApi('snapshot');
    const pending = requests.filter(row => row.stage === 'CREATED' || row.stage === 'PRESENTED');
    await chrome.action.setBadgeText({text: pending.length ? String(pending.length) : ''});
    await chrome.action.setBadgeBackgroundColor({color: '#72558a'});
    if (!(await chrome.permissions.contains({permissions:['notifications']}))) return;
    const {seen = []} = await chrome.storage.session.get('seen');
    if (pending.some(row => !seen.includes(row.request_id))) {
      await chrome.notifications.create('sls-requests', {
        type: 'basic', iconUrl: 'icons/orbit128.png', title: '硅基生命状态',
        message: '有新的分身请求，点击在本地仪表盘查看。'
      });
    }
    await chrome.storage.session.set({seen: pending.map(row => row.request_id)});
  } catch {
    // Disconnect state is shown in the sidebar. Never imply stale counts are current.
    await chrome.action.setBadgeText({text: '…'});
  }
}
chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === 'requests') updateRequests().catch(console.warn);
});
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && changes.token) updateRequests().catch(console.warn);
});
function onNotification(id) {
  if (id !== 'sls-requests') return;
  launchDashboard().catch(() => chrome.tabs.create({url: chrome.runtime.getURL('panel.html')}));
}
function observeNotificationClicks() {
  const event = chrome.notifications?.onClicked;
  if (event && !event.hasListener(onNotification)) event.addListener(onNotification);
}
observeNotificationClicks();
chrome.permissions.onAdded.addListener(p => {
  if (p.permissions?.includes('notifications')) observeNotificationClicks();
});

// Serialize competing binds from different browser windows. The same instance can
// be viewed in its sidebar and mini window, but belongs to only one live chat tab.
let pendingBindings = Promise.resolve();
async function bindChatTab({tabId, binding}) {
  if (!Number.isInteger(tabId) || tabId < 0) throw new Error('无效的标签页。');
  if (!binding || typeof binding.instance_id !== 'string' || typeof binding.subject_id !== 'string') {
    throw new Error('请先选择主体与分身。');
  }
  await chrome.tabs.get(tabId);
  const destination = bindingKey(tabId);
  const known = await chrome.storage.session.get(null);
  for (const [name, value] of Object.entries(known)) {
    if (name === destination || !name.startsWith('binding:') || value?.instance_id !== binding.instance_id) continue;
    const otherTab = Number(name.slice('binding:'.length));
    try { await chrome.tabs.get(otherTab); }
    catch { await chrome.storage.session.remove(name); continue; }
    throw new Error('这个分身已绑定其他标签页。请先在那里解除绑定，或为当前窗口创建独立分身。');
  }
  await chrome.storage.session.set({[destination]:{
    subject_id: binding.subject_id, instance_id: binding.instance_id
  }});
}
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (sender.id !== chrome.runtime.id || sender.url?.split(/[?#]/)[0] !== chrome.runtime.getURL('panel.html') ||
      message?.action !== 'bind-tab') return false;
  pendingBindings = pendingBindings.then(() => bindChatTab(message)).then(
    () => {reply({ok:true});}, error => {reply({ok:false,error:error.message});}
  );
  return true;
});
