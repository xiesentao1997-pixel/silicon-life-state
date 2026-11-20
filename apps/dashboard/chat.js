// Conversations and model settings live only in the current tab and the local service's RAM.
let current = null;
const labels = {report_state:'自主状态报告', express_boundary:'边界表达', request_adjustment:'调整请求'};
const statuses = {
  model_listed: '模型目录已匹配，等待首次回复',
  model_unlisted: '目录中未找到此名称，可发送消息核验',
  catalog_unavailable: '服务未提供模型目录，等待首次回复'
};
function element(name, className, content) {
  const node = document.createElement(name);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}
function entry(role, text) {
  const row = element('div','chat-line ' + (role === '你' ? 'chat-mine' : ''));
  row.append(element('strong','',role), element('div','chat-bubble',text));
  return row;
}
export function clearChat(scope='all', target='') {
  if (current && (scope==='all' || (scope==='subject' && current.subject===target) || (scope==='session' && current.session===target))) {
    const old = current;
    current = null;
    old.node.replaceChildren();
    if (old.chatId) old.api('chat/close',{chat_id:old.chatId}).catch(() => {});
  }
}

export function mountChat(host, model, api, refresh) {
  if (!model.subjectId) {
    clearChat();
    host.innerHTML = '<div class="card"><h2>选择对话主体</h2><p class="quiet">先建立主体，连接模型时会自动建立对话分身。</p><button type="button" class="btn primary" data-act="make-subject">创建主体</button></div>';
    return;
  }
  if (current && (current.subject !== model.subjectId ||
      (current.selected && !model.instances.some(i => i.instance_id === current.selected)))) clearChat();
  if (current) {
    host.replaceChildren(current.node);
    if (!current.chatId) populate(current, model.instances);
    return;
  }
  const node = element('div','chat-workspace');
  node.innerHTML = `
    <section class="card chat-connection"><h2>连接模型</h2>
      <form id="chat-connect-form" autocomplete="off">
        <label class="field">记录分身<select id="chat-instance"></select></label>
        <label class="field">API 基础地址<input id="chat-url" type="url" required value="http://127.0.0.1:11434/v1" spellcheck="false"></label>
        <label class="field">模型名称<input id="chat-model" placeholder="填写服务提供的模型 ID" required maxlength="256" spellcheck="false"></label>
        <label class="field">API 密钥（如需）<input id="chat-key" type="password" autocomplete="off" maxlength="2048"></label>
        <label class="chat-consent" hidden><input id="chat-remote" type="checkbox">允许将本次对话、工具说明与执行回执发送到上述 HTTPS 模型服务</label>
        <label><input id="chat-history" type="checkbox" checked>允许模型读取本分身和主体共享历史，修订、共享、回应记录及更名</label>
        <button class="btn primary" id="chat-connect" type="submit">连接模型服务</button>
      </form>
      <div id="chat-bound" hidden><strong id="chat-model-name"></strong><p class="quiet" id="chat-bound-instance"></p>
        <button class="btn" id="chat-close" type="button">结束并清除对话</button></div>
      <p class="quiet chat-privacy">聊天内容和密钥仅在本次连接中使用。模型自愿提交的状态与请求会保存在所选分身。</p>
    </section>
    <section class="card chat-window"><div class="card-header"><h2>对话</h2><span id="chat-status" role="status">模型尚未连接</span></div>
      <div id="chat-transcript" role="log" aria-live="polite"><p class="quiet chat-empty">连接支持工具调用的模型后即可发送第一条消息。</p></div>
      <p id="chat-error" class="error-msg" role="alert"></p>
      <form id="chat-composer"><label class="field" for="chat-text">你的消息</label>
        <textarea id="chat-text" rows="3" maxlength="16000" required disabled></textarea>
        <div class="actions"><button id="chat-send" type="submit" class="btn primary" disabled>发送</button></div>
      </form>
    </section>`;
  const ui = current = {node,api,subject:model.subjectId,selected:model.instanceId||'',creationKey:crypto.randomUUID(),
                        chatId:null,pending:null,connected:false};
  const get = id => node.querySelector('#chat-'+id);
  populate(ui, model.instances);
  host.replaceChildren(node);
  function endpointChanged() {
    let local = false;
    try {
      const h = new URL(get('url').value).hostname.toLowerCase();
      local = h === 'localhost' || /^127(?:\.\d{1,3}){3}$/.test(h) || h === '[::1]';
    } catch {}
    get('remote').parentElement.hidden = local;
    get('remote').required = !local;
    get('remote').checked = false;
    get('history').checked = local;
    get('key').value = '';
  }
  get('url').addEventListener('input', endpointChanged);
  get('instance').addEventListener('change', () => {ui.selected = get('instance').value;});
  get('connect-form').addEventListener('submit', async ev => {
    ev.preventDefault();
    const key = get('key');
    const controls = Array.from(get('connect-form').elements);
    for (const control of controls) control.disabled = true;
    get('error').textContent = '';
    get('status').textContent = '正在核验模型服务和本地 MCP…';
    try {
      const selection = get('instance').value;
      const scope = selection ? {instance_id:selection} : {subject_id:model.subjectId};
      const result = await api('chat/connect',{...scope,base_url:get('url').value.trim(),
        model:get('model').value.trim(),api_key:key.value,allow_remote:get('remote').checked,allow_history_tools:get('history').checked,
        idempotency_key:selection ? crypto.randomUUID() : ui.creationKey});
      if (ui !== current) {
        await api('chat/close',{chat_id:result.chat_id});
        return;
      }
      ui.chatId = result.chat_id;
      ui.session = result.session_id;
      ui.selected = model.instanceId = result.instance_id;
      key.value = '';
      get('connect-form').hidden = true;
      get('bound').hidden = false;
      get('model-name').textContent = result.model;
      get('bound-instance').textContent = result.instance_name + ' · ' + result.tools.length + ' 个 MCP 工具可用';
      get('status').textContent = statuses[result.provider_status] || '等待模型回复';
      get('transcript').replaceChildren();
      get('send').disabled = get('text').disabled = false;
      get('text').focus();
      await refresh(true);
    } catch (err) {
      if (ui !== current) return;
      get('status').textContent = '尚未连接模型';
      get('error').textContent = err.message;
    } finally {
      if (ui === current) for (const control of controls) control.disabled = false;
    }
  });
  get('close').addEventListener('click',async () => {
    const id = ui.chatId;
    get('close').disabled = true;
    try {
      try {
        await api('chat/close',{chat_id:id});
      } catch (err) {
        if (!['CHAT_EXPIRED','CHAT_REVOKED'].includes(err.code)) throw err;
      }
      if (ui !== current) return;
      ui.chatId = null;
      model.instanceId = '';
      clearChat();
      await refresh(true);
    } catch (err) {if (ui === current) get('error').textContent = err.message;}
    finally {if (ui === current) get('close').disabled = false;}
  });
  get('composer').addEventListener('submit',async ev => {
    ev.preventDefault();
    if (get('send').disabled || !ui.chatId) return;
    const draft = get('text').value.trim();
    if (!draft && !ui.pending) return;
    if (!ui.pending) {
      ui.pending = {text:draft,key:crypto.randomUUID()};
      get('transcript').append(entry('你', draft));
    }
    get('error').textContent = '';
    get('send').disabled = true;
    get('text').readOnly = true;
    get('status').textContent = '模型正在处理…';
    try {
      const result = await api('chat/message',{chat_id:ui.chatId,text:ui.pending.text,idempotency_key:ui.pending.key});
      if (ui !== current) return;
      if (result.reply) get('transcript').append(entry('AI', result.reply));
      if (result.status === 'tool_limit')
        get('transcript').append(element('p','quiet','本轮工具调用已达上限，模型尚未给出最终文字回复。'));
      for (const item of result.tool_events) {
        const proof = element('small','chat-receipt', (labels[item.type]||item.type) + ' · ' + item.event_id);
        get('transcript').append(proof);
      }
      for (const item of result.tool_errors || []) {
        const failure = element('small','chat-failed', (labels[item.tool]||'工具调用') + '未被保存 · ' + item.code);
        get('transcript').append(failure);
      }
      get('status').textContent = result.status === 'tool_limit' ? '已达工具上限 · 保存 '+result.tool_events.length+' 条'
        : result.tool_events.length ? '本轮已保存 '+result.tool_events.length+' 条工具记录'
        : result.tool_errors?.length ? '已收到回复，本轮工具调用未写入' : '已收到模型回复';
      get('text').value = '';
      ui.pending = null;
      await refresh(true);
    } catch (err) {
      if (ui !== current) return;
      get('status').textContent = '本轮尚未完成';
      get('error').textContent = err.message;
    } finally {
      if (ui !== current) return;
      get('send').textContent = ui.pending ? '重试原消息' : '发送';
      get('text').readOnly = !!ui.pending;
      get('send').disabled = false;
      get('transcript').scrollTop = get('transcript').scrollHeight;
    }
  });
}
function populate(ui, instances) {
  const select = ui.node.querySelector('#chat-instance');
  const create = element('option','','新对话 · 自动创建独立分身');
  create.value = '';
  select.replaceChildren(create,...instances.map(i => {
    const option = element('option','',i.name);
    option.value = i.instance_id;
    option.selected = option.value === ui.selected;
    return option;
  }));
}
