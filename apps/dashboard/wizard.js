import {h} from './views.js';

const names = {claude: 'Claude Desktop', codex: 'Codex CLI', other: '其他 MCP 宿主'};
const platform = {win32: 'Windows', darwin: 'macOS', linux: 'Linux'};
const btn = (key, label, primary = false) =>
  '<button type="button" class="btn' + (primary ? ' primary' : '') + '" data-wiz="' + key + '">' + h(label) + '</button>';
const row = (key, value) => '<dt>' + h(key) + '</dt><dd>' + h(value) + '</dd>';

function activity(status) {
  const {probe, host_discovery: discovery, report} = status;
  return '<dl class="kv">' +
    row('向导工具发现', probe ? probe.transport + ' · 已发现 ' + probe.tools.length + ' 个工具 · ' + probe.at : '尚未试连') +
    row('宿主工具发现', discovery ? discovery.client + ' · 已调用 tools/list · ' + discovery.at : '服务本次启动后，尚未观测到其他客户端发现工具') +
    row('分身自主报告', report ? '已收到经 Agent 凭据提交的报告 · ' + report.at + ' · ' + report.event_id : '尚未收到此分身通过 Agent 工具提交的状态') +
    '</dl><p class="quiet">客户端名称由宿主自报。核验具体模型时，可在宿主工具回执与事件页对照同一事件 ID。</p>';
}

export function hostWizard({modal, api, toast, instanceField, subjectId, instanceId}) {
  modal('连接 Agent 宿主',
    instanceField(instanceId) +
    '<label class="field">宿主<select name="host"><option value="claude">Claude Desktop</option>' +
    '<option value="codex">Codex CLI</option><option value="other">其他 MCP 宿主</option></select></label>' +
    '<div id="wiz-transport" hidden><label class="field">连接方式<select name="transport"><option value="stdio">本机 stdio</option>' +
    '<option value="http">本机 Streamable HTTP</option></select></label></div>' +
    '<p class="quiet">检查目标文件和语法后，你可以复制本项目条目、确认写入或测试本机连接。</p>',
    async f => {
      const form = document.querySelector('#form');
      const plan = await api('hosts/preview', {host: f.host, subject_id: subjectId, instance_id: f.instance_id,
        transport: f.host === 'other' ? f.transport : 'stdio'});
      if (form?.isConnected) preview(f.host, plan);
    }, '检查配置');
  const select = document.querySelector('#dialog select[name=host]');
  select.addEventListener('change', () => {
    document.querySelector('#wiz-transport').hidden = select.value !== 'other';
  });

  function preview(host, plan) {
    const rootId = 'host-wizard-preview';
    const info = '<dl class="kv">' +
      row('操作系统', platform[plan.os] || plan.os) +
      row('安装检测', plan.installation || (plan.existing_file ? '发现已有宿主配置文件' : '未检测到可执行程序')) +
      row('配置路径', plan.target || '由宿主的连接设置指定') +
      row('配置检查', plan.can_write ? (plan.existing_file ? '原配置语法有效 · ' : '目标文件尚未建立 · ') + plan.action : plan.reason) +
      '</dl>';
    const safe = '<p class="note">配置包含此分身的授权令牌。复制或写入时将使用该分身的现有凭据，首次使用会创建凭据。</p>';
    const writeActions = plan.can_write
      ? '<p class="quiet">确认后将保留其他服务与设置；已有目标文件会先在旁边生成私有备份。</p>' + btn('apply','确认写入配置',true)
      : '';
    modal(names[host] + ' · 连接配置',
      '<section id="' + rootId + '">' + info + '<details><summary>查看本项目配置（令牌已隐藏）</summary>' +
      '<pre tabindex="0">' + h(plan.preview) + '</pre></details>' + safe + '<div class="actions">' +
      btn('copy','复制完整配置') + '</div>' + writeActions +
      '<p class="quiet">' + h(plan.manual) + '</p><p data-wiz-status role="status" class="note" hidden></p>' +
      '<h3>连接与写入状态</h3><div data-wiz-activity>' + activity(plan.status) + '</div>' +
      '<div class="actions">' + btn('probe','测试连接，发现工具') + btn('status','刷新实际状态') + '</div>' +
      '<div data-wiz-fallback></div></section>');
    const box = document.getElementById(rootId);
    const msg = box.querySelector('[data-wiz-status]');
    const area = box.querySelector('[data-wiz-activity]');
    box.addEventListener('click', async ev => {
      const button = ev.target.closest('button[data-wiz]');
      if (!button || box.dataset.busy) return;
      const action = button.dataset.wiz;
      const buttons = Array.from(box.querySelectorAll('button'));
      box.dataset.busy = 'yes';
      buttons.forEach(b => {b.disabled = true;});
      msg.hidden = false;
      msg.textContent = action === 'probe' ? '正在通过选定传输调用 tools/list…' : '正在处理…';
      try {
        const response = await api('hosts/' + action, {plan_id: plan.plan_id, confirm: action !== 'status'});
        if (!box.isConnected) return;
        if (action === 'copy') {
          try {
            await navigator.clipboard.writeText(response.config);
            msg.textContent = '已复制本项目配置，请在所选宿主的本机配置中合并。';
          } catch {
            const fallback = box.querySelector('[data-wiz-fallback]');
            const label = document.createElement('label');
            label.className = 'field';
            label.textContent = '浏览器未允许写入剪贴板，请复制下方完整配置';
            const text = document.createElement('textarea');
            text.readOnly = true;
            text.rows = 7;
            text.value = response.config;
            label.append(text);
            fallback.replaceChildren(label);
            text.focus();
            text.select();
            msg.textContent = '配置已生成，关闭窗口后将清除本页明文。';
          }
        } else if (action === 'apply') {
          msg.textContent = '配置已保存到 ' + response.target + '。' +
            (response.backup ? '原文件备份位于 ' + response.backup + '。' : '') +
            '请重新加载宿主，再刷新工具发现状态。';
          toast('宿主配置已保存');
        } else {
          area.innerHTML = activity(response);
          msg.textContent = action === 'probe' ? '试连完成。向导已收到实际工具清单。' : '已刷新此分身的实际状态。';
        }
      } catch (err) {
        if (box.isConnected) msg.textContent = err.message;
      } finally {
        delete box.dataset.busy;
        buttons.forEach(b => {b.disabled = false;});
      }
    });
  }
}
