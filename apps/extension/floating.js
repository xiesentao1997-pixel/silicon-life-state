// This entry only inserts a button. State and credentials stay inside the extension.
(() => {
  const id = 'silicon-life-state-entry';
  if (document.getElementById(id)) return;
  const host = document.createElement('div');
  host.id = id;
  host.style.cssText = 'position:fixed;right:18px;bottom:22%;z-index:2147483646;';
  const root = host.attachShadow({mode:'closed'});
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = '✧ 状态';
  button.title = '打开硅基生命状态侧栏';
  button.style.cssText = 'all:initial;display:block;cursor:pointer;font:14px system-ui;color:#f7edff;background:#352942;border:1px solid #af9ac9;border-radius:24px;padding:8px 14px;box-shadow:0 2px 10px #0003;';
  button.addEventListener('click', event => {
    if (event.isTrusted) chrome.runtime.sendMessage({action:'open-status-panel'}).catch(() => {});
  });
  root.append(button);
  document.documentElement.append(host);
})();
