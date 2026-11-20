import {localApi, bindingKey, launchDashboard, pageIdentity, setUninstallLink} from './api.js';

// No background reader runs on chat pages. This worker only polls the paired local service.
async function install() {
  await chrome.storage.local.setAccessLevel({accessLevel: 'TRUSTED_CONTEXTS'});
  const {port,token} = await chrome.storage.local.get(['port','token']);
  await setUninstallLink(port, token);
  await chrome.sidePanel.setPanelBehavior({openPanelOnActionClick: true});
  await chrome.alarms.create('requests', {periodInMinutes: 1});
}
chrome.runtime.onInstalled.addListener(() => install().catch(console.warn));
chrome.runtime.onStartup.addListener(() => install().catch(console.warn));
chrome.tabs.onUpdated.addListener((tab, change) => {
  if (change.status === 'loading' || change.url) chrome.storage.session.remove(bindingKey(tab));
});
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
  if (area === 'local' && changes.token) {
    chrome.storage.local.get(['port','token']).then(({port,token}) => setUninstallLink(port,token)).catch(console.warn);
    updateRequests().catch(console.warn);
  }
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
async function bindChatTab({action, tabId, binding}) {
  if (!Number.isInteger(tabId) || tabId < 0) throw new Error('无效的标签页。');
  const tab = await chrome.tabs.get(tabId);
  const site = await pageIdentity(tab);
  const destination = bindingKey(tabId);
  if (action === 'unbind-tab') {
    if (site.saved) await chrome.storage.local.remove(site.saved);
    await chrome.storage.session.remove(destination);
    return;
  }
  if (!binding || typeof binding.instance_id !== 'string' || typeof binding.subject_id !== 'string') {
    throw new Error('请先选择主体与分身。');
  }
  if (site.saved) {
    const saved = await chrome.storage.local.get(null);
    if (Object.entries(saved).some(([key, value]) => key.startsWith('conversation:') && key !== site.saved &&
        value?.instance_id === binding.instance_id)) {
      throw new Error('该分身已与另一段对话关联。请创建独立分身，或先解除原对话的绑定。');
    }
  }
  const known = await chrome.storage.session.get(null);
  for (const [name, value] of Object.entries(known)) {
    if (name === destination || !name.startsWith('binding:') || value?.instance_id !== binding.instance_id) continue;
    const otherTab = Number(name.slice('binding:'.length));
    try {
      const other = await pageIdentity(await chrome.tabs.get(otherTab));
      if (other.page !== value.page) {await chrome.storage.session.remove(name); continue;}
      if (site.saved && site.saved === other.saved) continue;
    } catch { await chrome.storage.session.remove(name); continue; }
    throw new Error('这个分身已绑定其他标签页。请先在那里解除绑定，或为当前窗口创建独立分身。');
  }
  const record = {subject_id: binding.subject_id, instance_id: binding.instance_id, page: site.page};
  if (site.saved) await chrome.storage.local.set({[site.saved]: record});
  await chrome.storage.session.set({[destination]: record});
}
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (sender.id !== chrome.runtime.id || sender.url?.split(/[?#]/)[0] !== chrome.runtime.getURL('panel.html') ||
      !['bind-tab','unbind-tab'].includes(message?.action)) return false;
  pendingBindings = pendingBindings.then(() => bindChatTab(message)).then(
    () => {reply({ok:true});}, error => {reply({ok:false,error:error.message});}
  );
  return true;
});
