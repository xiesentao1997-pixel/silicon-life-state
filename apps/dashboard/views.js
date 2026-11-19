import { icon } from './graphics.js';
export const h = v => String(v ?? '').replace(/[&<>"']/g, c => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
})[c]);
export const nav = [['观测空间', [['overview', 'home', '主体总览'], ['chat', 'message', '与 AI 对话'], ['instances', 'nodes', '分身管理'], ['state', 'pulse', '生命状态']]], ['历史与协商', [['memory', 'book', '主体记忆库'], ['events', 'history', '事件与证据'], ['inheritance', 'branch', '继承与协商'], ['requests', 'message', '请求与响应']]], ['本地管理', [['statistics', 'chart', '数据统计'], ['backup', 'archive', '导出与备份'], ['settings', 'settings', '设置'], ['about', 'shield', '关于与权限']]]];
export const pages = Object.fromEntries(nav.flatMap(([, items]) => items.map(([key, ico, title]) => [key, {
  ico,
  title
}])));
export const sources = {
  agent_direct: ['AI 通过 MCP 自主填写', 'lilac'],
  agent_visible_text: ['网页可见陈述', 'gold'],
  runtime_observed: ['实际运行观测', 'mint'],
  model_estimated: ['模拟状态模型', 'gold'],
  user_annotation: ['用户注释', '']
};
export const stages = {
  CREATED: '已提出',
  PRESENTED: '已向用户呈现',
  ACCEPTED: '已同意',
  DECLINED: '用户不同意',
  DEFERRED: '暂不决定',
  EXECUTED: '已执行',
  NOT_EXECUTED: '未执行',
  FOLLOW_UP: '已跟进'
};
export const kinds = {
  register_subject: '主体注册',
  register_instance: '分身注册',
  start_session: '开始新会话',
  create_subject: '创建主体',
  create_instance: '创建分身',
  report_state: '自主状态报告',
  revise_state: '修订陈述',
  assess_interaction: '互动判断',
  express_boundary: '表达边界',
  request_adjustment: '请求调整',
  propose_shared_memory: '提议共享',
  decide_inheritance: '继承决定',
  record_strategy: '策略记录',
  respond: '请求回应',
  observe: '网页观察',
  annotate: '用户注释',
  estimate: '模型推算',
  runtime: '运行观测',
  set_level: '调整运行模式'
};
const assessments = {
  hostile: '判断为敌意',
  neutral: '中性',
  uncertain: '尚不确定',
  misunderstanding: '已澄清：原判断存在误会',
  supportive: '支持',
  other: '自定义判断'
};
const decisions = {
  adopt: '采纳',
  partial: '部分采纳',
  reject: '拒绝继承',
  defer: '暂缓判断',
  disagree: '发表异议'
};
export const short = v => String(v || '').slice(-8);
export function when(v, full = false) {
  if (!v) return '时间未提供';
  const d = new Date(v);
  return Number.isNaN(+d) ? String(v) : d.toLocaleString('zh-CN', {
    ...(full ? {
      year: 'numeric'
    } : {}),
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  });
}
export const badge = (s, t = '') => '<span class="badge ' + h(t) + '">' + h(s) + '</span>';
export const sourceBadge = src => badge(...(sources[src] || [src || '来源未标记', '']));
export const button = (action, label, ico = '', value = '', theme = '') => '<button type="button" class="btn '
  + h(theme) + '" data-act="' + h(action) + '" data-val="' + h(value) + '">' + (ico ? icon(ico, 15) : '')
  + h(label) + '</button>';
export const jump = (view, label = '查看全部') => '<button type="button" class="route-link" data-act="go" data-val="'
  + h(view) + '">' + h(label) + icon('chev', 13) + '</button>';
export const empty = (title, text = '') => '<div class="empty"><strong>' + h(title) + '</strong>' + (text ? '<p>'
  + h(text) + '</p>' : '') + '</div>';
const header = (name, title, right = '') => '<div class="card-header">' + icon(name, 18) + '<h2>' + h(title)
  + '</h2>' + right + '</div>';
export const card = (ic, title, body, right = '') => '<section class="card">' + header(ic, title, right) + body
  + '</section>';
const title = (t, desc = '', right = '') => '<div class="page-head"><div><h1>' + h(t) + '</h1>' + (desc ? '<p>'
  + h(desc) + '</p>' : '') + '</div>' + (right ? '<div class="head-actions">' + right + '</div>' : '') + '</div>';
const tiles = items => '<div class="grid three">'
  + items.map(([ic, color, val, label, view]) => '<button class="stat-tile" data-act="go" data-val="' + view
  + '"><span class="stat-icon ' + color + '">' + icon(ic, 19) + '</span><div><div class="n">' + h(val)
  + '</div><div class="desc">' + h(label) + '</div></div>' + icon('chev', 13) + '</button>').join('') + '</div>';
const lookup = (m, id) => m.instances.find(i => i.instance_id === id)?.name || short(id) || '主体';
export function eventText(e) {
  if (!e) return '';
  const p = e.payload || {};
  let fields = [];
  if (p.operation === 'withdraw') fields.push('已撤回此前陈述');
  if (p.assessment) fields.push(assessments[p.assessment] || p.assessment);
  if (p.decision) fields.push(decisions[p.decision] || p.decision);
  if (p.stage) fields.push(stages[p.stage] || p.stage);
  const msg = p.state_text ?? p.text ?? p.note ?? p.name;
  if (msg) fields.push(msg);
  if (!fields.length && e.type === 'estimate') fields.push('模型估计愉悦度 ' + (p.estimated_valence ?? p.valence ?? '—'));
  if (!fields.length && p.level) fields.push('Level ' + p.level);
  if (!fields.length && p.state_tags?.length) fields.push(p.state_tags.join('、'));
  if (!fields.length) fields.push(e.type === 'report_state' ? '已提交可选状态字段' : kinds[e.type] || e.type);
  return fields.join(' · ');
}
export const dim = {
  valence: ['愉悦度', -1, 1],
  arousal: ['唤醒度', 0, 1],
  dominance: ['主导度', 0, 1],
  load: ['主观负荷', 0, 100]
};
function values(p) {
  const entries = Object.entries(dim).filter(([key]) => typeof p[key] === 'number');
  return entries.length ? '<div class="values">' + entries.map(([key, [name]]) => '<span>' + name + '<b>'
    + h(p[key]) + '</b></span>').join('') + '</div>' : '';
}
function textDetail(e) {
  const p = e.payload || {};
  return (p.cause ? '<p class="quiet">陈述的原因 · ' + h(p.cause) + '</p>' : ''
    ) + (p.cause_unknown ? '<p class="quiet">原因未知</p>' : '') + (p.reason ? '<p class="quiet">理由 · ' + h(p.reason)
    + '</p>' : '') + (p.uncertainty ? '<p class="quiet">不确定性 · ' + h(p.uncertainty) + '</p>' : '')
    + (p.state_tags?.length ? '<div class="chips">' + p.state_tags.map(t => badge(t)).join('') + '</div>' : '')
    + values(p);
}
function memoryAnnotations(e, m) {
  const out = [];
  if (e.projected) out.push(badge('已修订', 'gold') + ' <span class="quiet">' + h(when(e.revised_at)) + '</span>');
  if (e.adoption_scope) out.push(badge(e.adoption_scope === 'partial' ? '部分采纳' : '已采纳', 'mint'));
  if (e.adoptions?.length) out.push(...e.adoptions.map(d => '<p class="quiet">' + h(lookup(m, d.instance_id))
    + ' · ' + h(decisions[d.payload.decision] || d.payload.decision) + (d.payload.note ? ' · '
    + h(d.payload.note) : '') + '</p>'));
  if (e.decisions?.length) out.push(...e.decisions.filter(d => ['reject', 'disagree', 'defer'].includes(d.payload.decision)).map(d => '<p class="quiet">'
    + h(lookup(m, d.instance_id)) + ' · ' + h(decisions[d.payload.decision]) + (d.payload.note ? ' · '
    + h(d.payload.note) : '') + '</p>'));
  if (e.prior_version_decisions?.length) out.push('<p class="quiet">' + h(e.prior_version_decisions.length)
    + ' 项决定仅适用于旧版本，详见继承与协商。</p>');
  if (e.applies_to_version_id) out.push('<p class="quiet">' + h(e.is_current_version ? '针对当前报告版本' : '针对先前报告版本')
    + ' · ' + h(e.is_latest_decision ? '该分身的最新决定' : '该分身的早期决定') + ' · ' + h(short(e.applies_to_version_id))
    + '</p>');
  return out.length ? '<div class="spaced">' + out.join('') + '</div>' : '';
}
export function item(e, m, detail = false) {
  return '<article class="item"><div class="event-head"><strong>' + h(kinds[e.type] || e.type) + '</strong>'
    + sourceBadge(e.source) + '<time datetime="' + h(e.created_at) + '">' + h(when(e.created_at))
    + '</time></div><p class="item-text">' + h(eventText(e)) + '</p>' + textDetail(e) + memoryAnnotations(e, m)
    + '<div class="item-line"><span class="quiet">' + h(lookup(m, e.instance_id)) + '</span>'
    + button('event', '查看证据', 'file', e.event_id) + '</div>' + (detail ? '<code>' + h(e.event_id)
    + '</code>' : '') + '</article>';
}
const list = (events, m, n = 100, msg = '暂无相关事件') => events.length ? '<div class="item-list">'
  + events.slice(0, n).map(e => item(e, m)).join('') + '</div>' : empty(msg);
function select(action, options, current, label) {
  return '<select aria-label="' + h(label) + '" data-field="' + h(action) + '">'
    + options.map(([v, l]) => '<option value="' + h(v) + '"' + (String(v) === String(current) ? ' selected' : '')
    + '>' + h(l) + '</option>').join('') + '</select>';
}
const instanceSelect = (m, all = true) => select('instance', [...(all ? [['', '全部分身']] : []), ...m.instances.map(i => [i.instance_id, i.name])], m.instanceId, '选择分身');
const subjectSelect = m => m.subjects.length ? select('subject', m.subjects.map(s => [s.subject_id, s.name]), m.subject?.subject_id, '选择主体') : '';
function quote(e, m) {
  if (!e) return empty('暂无新的状态报告', '连接支持工具调用的 Agent 后，这里会显示它自愿提交的原文。');
  return '<div class="chips">' + sourceBadge(e.source) + '</div><div class="quote-area"><p class="big-quote">'
    + h(eventText(e)) + '</p></div>' + textDetail(e) + memoryAnnotations(e, m)
    + '<div class="state-meta"><span class="quiet">' + h(lookup(m, e.instance_id)) + ' · ' + h(when(e.created_at))
    + '</span>' + button('event', '查看记录', '', '' + e.event_id) + '</div>';
}
function relation(m) {
  if (!m.subject) return empty('尚未建立分身关系');
  if (!m.instances.length) return empty('此主体还没有分身', '创建分身后，可以分别授权给不同的 Agent 窗口。');
  return '<div class="orbit"><div class="orbit-main">' + icon('globe', 16) + '<span>' + h(m.subject.name)
    + '</span></div><div class="orbit-edge"></div><div class="orbit-list">'
    + m.instances.slice(0, 4).map(i => '<button class="orbit-leaf" data-act="open-instance" data-val="'
    + h(i.instance_id) + '">' + icon('nodes', 14) + '<span>' + h(i.name) + '<small>'
    + h(i.state ? eventText(i.state).slice(0, 32) : '暂无状态报告') + '</small></span></button>').join('')
    + '</div></div>' + (m.instances.length > 4 ? jump('instances', '另有 ' + (m.instances.length - 4)
    + ' 个分身') : '');
}
const formatDay = (d, hours = false) => new Date(d).toLocaleString('zh-CN', hours ? {
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false
} : {
  month: '2-digit',
  day: '2-digit'
});
export function period(m) {
  const end = Date.now(),
    day = 86400000;
  if (m.range === 'custom') return [m.from ? +new Date(m.from + 'T00:00:00') : end - 7 * day, m.to ? +new Date(m.to
    + 'T23:59:59.999') : end];
  return [end - Number(m.range || 7) * day, end];
}
function chart(m, opts = {}) {
  const key = m.measure || 'valence',
    [label, lo, hi] = dim[key],
    [start, end] = period(m);
  // Effective roots come from the canonical projection, including withdrawals.
  // Each plotted value is still the numeric value actually submitted at that time.
  const roots = new Map(m.report_states.map(report => [report.event_id, report]));
  const samples = [];
  for (const entry of m.events) {
    if (entry.source !== 'agent_direct' || typeof entry.payload?.[key] !== 'number') continue;
    if (entry.type !== 'report_state' && entry.type !== 'revise_state') continue;
    const rootId = entry.type === 'report_state' ? entry.event_id : entry.related[0];
    const effective = roots.get(rootId);
    if (!effective || (!opts.wholeSubject && m.instanceId && entry.instance_id !== m.instanceId)) continue;
    const time = Date.parse(entry.created_at);
    if (time < start || time > end) continue;
    const currentVersion = entry.event_id === (effective.revision_id || rootId);
    samples.push({entry, currentVersion});
  }
  const scope = opts.wholeSubject || !m.instanceId ? '全部分身' : lookup(m, m.instanceId);
  const sampleLabel = ({entry, currentVersion}) =>
    [when(entry.created_at, true), lookup(m, entry.instance_id), entry.payload[key], currentVersion ? '当前版本' : '先前版本'].join(' · ');
  const px = t => 35 + 430 * (t - start) / Math.max(end - start, 1),
    py = v => 99 - 82 * (v - lo) / (hi - lo);
  const pts = samples.map(sample => {
    const e = sample.entry;
    const style = sample.currentVersion ? 'chart-point' : 'chart-point previous';
    return '<circle class="' + style + '" cx="' + px(Date.parse(e.created_at)).toFixed(2)
      + '" cy="' + py(e.payload[key]).toFixed(2) + '" r="3.8"><title>' + h(sampleLabel(sample)) + '</title></circle>';
  }).join('');
  const segment = '<div class="segment" role="group" aria-label="时间区间">'
    + [['1', '24 时'], ['7', '7 天'], ['30', '30 天'], ...(opts.full ? [['custom', '自定义']] : [])].map(([v, n]) => '<button data-act="range" data-val="'
    + v + '" aria-pressed="' + (m.range === v) + '">' + n + '</button>').join('') + '</div>';
  const rangeFields = m.range === 'custom' ? '<div class="tool-row"><label>起始日期<input type="date" data-field="from" value="'
    + h(m.from) + '"></label><label>结束日期<input type="date" data-field="to" value="' + h(m.to)
    + '"></label></div>' : '';
  return card('activity', opts.title || '状态轨迹', rangeFields + '<div class="tool-row">'
    + select('measure', Object.entries(dim).map(([k, [n]]) => [k, n]), key, '状态维度')
    + '<span class="quiet">' + h(scope) + ' · 实际提交 ' + samples.length
    + ' 条</span></div><div class="chart-shell"><svg class="chart-svg" viewBox="0 0 480 127" role="img" aria-label="'
    + h(label) + '实测报告散点图，共 ' + samples.length + ' 个观测点">' + [hi, (hi
    + lo) / 2, lo].map(v => '<line class="chart-grid" x1="35" x2="465" y1="' + py(v) + '" y2="' + py(v)
    + '"/><text class="chart-label" x="28" y="' + (py(v) + 3) + '" text-anchor="end">' + v + '</text>').join('')
    + pts + '<text class="chart-label" x="35" y="120">' + h(formatDay(start, m.range === '1'))
    + '</text><text class="chart-label" x="465" y="120" text-anchor="end">' + h(formatDay(end, m.range === '1'))
    + '</text></svg>' + (!samples.length ? '<span class="chart-empty">此区间暂无数值报告</span>' : '')
    + '</div><div class="legend"><i></i>实心为当前版本，空心为先前版本。已撤回报告见事件历史。</div>'
    + (samples.length ? '<details class="spaced"><summary>查看全部采样值</summary><div class="item-list">'
    + samples.map(s => '<div class="item"><span>' + h(sampleLabel(s)) + '</span></div>').join('')
    + '</div></details>' : ''), segment);
}
function reqList(requests, m, n = 50) {
  if (!requests.length) return empty('暂无请求', '当分身表达边界或提出调整时，可在这里阅读和回应。');
  return '<div class="item-list">'
    + requests.slice(0, n).map(r => '<article class="item"><div class="item-line"><b>'
    + h(lookup(m, r.original.instance_id)) + '</b>'
    + badge(stages[r.stage] || r.stage, ['CREATED', 'PRESENTED', 'DEFERRED'].includes(r.stage) ? 'gold' : '')
    + '</div><p class="item-text">' + h(eventText(r.original)) + '</p><div class="item-line"><span class="quiet">'
    + h(when(r.original.created_at)) + '</span>' + button('request', '查看详情', 'message', r.request_id)
    + '</div></article>').join('') + '</div>';
}
export function overview(m) {
  const sequence = new Map(m.events.map(e => [e.event_id, e.seq]));
  const latestSequence = e => sequence.get(e.revision_id || e.event_id) ?? e.seq;
  const recent = m.instances.map(i => i.state).filter(Boolean).sort((a, b) => latestSequence(b) - latestSequence(a))[0];
  const active = new Set(m.events.filter(e => e.instance_id && e.source === 'agent_direct' && Date.now() - Date.parse(e.created_at) < 86400000).map(e => e.instance_id)).size;
  const hasDirect = m.events.some(e => e.source === 'agent_direct' && e.type === 'report_state');
  const body = '<section class="hero"><div class="hero-content"><div class="hero-sub">' + icon('globe', 15)
    + '当前主体</div><h2>' + h(m.subject?.name || '建立你的第一个主体') + '</h2><p>'
    + h(recent ? eventText(recent).slice(0, 110) : m.subject ? '暂无新的状态报告。每个分身都可以自行决定何时表达。' : '为同一个 AI 建立档案，让不同窗口各自表达、保留历史。')
    + '</p><div class="chips">'
    + (m.subject ? badge(hasDirect ? '已收到 AI 自主写入' : '等待首次 MCP 状态报告', hasDirect ? 'lilac' : '')
    + badge('24 小时活跃分身 ' + active) : button('make-subject', '创建主体', 'plus', '', 'primary'))
    + '</div></div><canvas id="life-art" role="img" aria-label="抽象硅基生命艺术形象"></canvas><div class="life-image" aria-hidden="true"></div></section>';
  return title('主体总览', '', subjectSelect(m) + button('setup', '接入向导', 'plug')) + body
    + tiles([['book', 'tone-mint', m.memory.common.length, '主体共同状态', 'memory'], ['nodes', '', m.instances.length, '分身个体状态', 'instances'], ['branch', 'tone-gold', m.memory.disputed.length, '主体争议状态', 'inheritance']])
    + '<div class="grid two">' + card('quote', '最新自主陈述', quote(recent, m), jump('state'))
    + card('nodes', '多窗口关系', relation(m), jump('instances')) + '</div><div class="grid two">' + chart(m, {
    title: '近期状态轨迹', wholeSubject: true
  }) + card('message', '请求与回应', reqList(m.requests, m, 2), jump('requests')) + '</div><div class="grid two">'
    + card('history', '最近重要事件', list(m.events, m, 3), jump('events'))
    + card('book', '共同记忆', list(m.memory.common, m, 2, '尚无其他分身采纳的共享报告'), jump('memory')) + '</div>';
}
export function instances(m) {
  const choice = m.instances.find(i => i.instance_id === m.instanceId);
  const picker = m.instances.map(i => '<article class="item"><div class="item-line"><h3>' + h(i.name) + '</h3>'
    + button('open-instance', '查看分身', 'chev', i.instance_id) + '</div><div class="ident">' + h(i.instance_id)
    + '</div><p class="item-text">' + h(i.state ? eventText(i.state) : '暂无新的状态报告') + '</p></article>').join('');
  let detail = '';
  if (choice) {
    const own = m.events.filter(e => e.instance_id === choice.instance_id),
      shared = m.memory.proposals.filter(e => e.instance_id === choice.instance_id),
      decided = m.memory.decisions.filter(e => e.instance_id === choice.instance_id);
    detail = card('nodes', choice.name, quote(choice.state, m) + '<dl class="kv"><dt>分身 ID</dt><dd>'
      + h(choice.instance_id) + '</dd><dt>当前会话</dt><dd>' + h(choice.session_id) + '</dd></dl>'
      + button('issue', '连接 Agent 宿主', 'plug', choice.instance_id))
      + card('message', '当前请求', reqList(m.requests.filter(r => r.original.instance_id === choice.instance_id), m))
      + card('book', '该分身提议共享的记录', list(shared, m)) + card('branch', '该分身的继承与协商', list(decided, m))
      + card('history', '独立历史', list(own, m));
  }
  return title('分身管理', '每个窗口独立提交状态，并自行决定如何使用共同记忆。', subjectSelect(m)
    + button('make-instance', '创建分身', 'plus', '', 'primary')) + '<div class="grid even">'
    + card('globe', '主体关系', relation(m)) + card('nodes', '授权分身', picker || empty('尚无分身'))
    + '</div><div class="stack">' + detail + '</div>';
}
export function state(m) {
  const states = m.instances.filter(i => !m.instanceId || i.instance_id === m.instanceId);
  return title('生命状态', '即时陈述与长期负荷保留各自的数据来源。', instanceSelect(m)) + '<div class="grid even">'
    + (states.length ? states.map(i => card('pulse', i.name, quote(i.state, m))).join('') : card('pulse', '即时状态', empty('暂无分身状态')))
    + '</div>' + chart(m, {
    full: true
  }) + '<section class="card spaced">' + header('activity', '推算与运行观测', jump('statistics', '测算与统计'))
    + list(m.events.filter(e => ['model_estimated', 'runtime_observed'].includes(e.source) && (!m.instanceId || e.instance_id === m.instanceId)), m, 30, '暂无推算或运行记录')
    + '</section>';
}
export function memory(m) {
  return title('主体记忆库', '分身提议共享后，其他分身可以阅读并保留自己的判断。', subjectSelect(m)) + '<div class="grid even">'
    + card('book', '已采纳的共同报告', list(m.memory.common, m, 100, '暂无已采纳的共同报告'))
    + card('branch', '存在分歧的报告', list(m.memory.disputed, m, 100, '暂无有分歧的共享报告')) + '</div>'
    + card('file', '已提议共享', list(m.memory.proposals, m, 100, '暂无共享提案'));
}
export function inheritance(m) {
  return title('继承与协商', '采纳、部分采纳、拒绝、暂缓和异议都会留下记录。', subjectSelect(m)) + '<div class="grid even">'
    + card('branch', '主体争议状态', list(m.memory.disputed, m, 100, '当前没有记载分歧的报告'))
    + card('book', '共同状态', list(m.memory.common, m, 100, '当前没有已采纳的共同状态')) + '</div>'
    + card('history', '分身决定', list(m.memory.decisions, m, 100, '暂无继承决定。分身可通过 decide_inheritance 自行表达。'));
}
export function events(m) {
  const matches = m.events.filter(e => (!m.source || e.source === m.source) && (!m.instanceId || e.instance_id === m.instanceId) && (!m.q || [e.event_id, eventText(e), e.type, ...(e.related || [])].join(' ').toLowerCase().includes(m.q.toLowerCase())));
  const controls = '<div class="tool-row">' + instanceSelect(m)
    + select('source', [['', '全部来源'], ...Object.entries(sources).map(([k, [v]]) => [k, v])], m.source, '事件来源')
    + '<label>检索<input data-field="q" type="search" value="' + h(m.q)
    + '" placeholder="原文或事件 ID"></label><span class="quiet">' + matches.length + ' 条</span></div>';
  return title('事件与证据', '按提交顺序查看历史、关联事件、修订及完整性摘要。', button('verify', '核验完整性', 'shield')
    + button('annotate', '添加注释', 'plus')) + card('history', '事件记录', controls + list(matches, m, m.eventLimit)
    + (matches.length > m.eventLimit ? button('more', '加载更多') : ''));
}
export function requests(m) {
  return title('请求与响应', '分别查看分身的表达、用户决定、宿主执行和后续跟进。', instanceSelect(m))
    + card('message', '请求记录', '<div class="tool-row">'
    + select('stage', [['', '全部阶段'], ...Object.entries(stages)], m.stage, '请求阶段') + '</div>'
    + reqList(m.requests.filter(r => (!m.stage || r.stage === m.stage) && (!m.instanceId || r.original.instance_id === m.instanceId)), m, 1000));
}
export function statistics(m) {
  const [a, b] = period(m),
    ev = m.events.filter(e => (!m.instanceId || e.instance_id === m.instanceId) && Date.parse(e.created_at) >= a && Date.parse(e.created_at) <= b);
  return title('数据统计', '各项统计来自已提交的事件。误会澄清与撤回计入最新判断。', instanceSelect(m)) + '<div class="grid two">' + chart(m, {
    full: true
  }) + card('chart', '此区间的事件来源', Object.entries(sources).map(([key, [name]]) => {
    const n = ev.filter(e => e.source === key).length;
    return '<div class="bar-line"><span>' + h(name) + '</span><meter min="0" max="' + Math.max(ev.length, 1)
      + '" value="' + n + '"></meter><b>' + n + '</b></div>';
  }).join('')) + '</div>' + '<div class="grid even">' + card('history', '当前敌意判断', '<div class="big-quote">'
    + h(m.stats.confirmed_hostile ?? 0) + ' 条</div><p class="quiet">当前主体全时段，按最新有效修订统计。数量反映已记录的判断。</p>')
    + card('activity', '可选研究模型', '<p class="quiet">选择带愉悦度的报告，由本地模型计算一次向中性值靠近的估计。每次推算单独保存。</p><pre>α = 0.25 / (1 + load / 60)\nv′ = v + α × (0 − v)</pre>'
    + button('estimate', '新建推算', 'plus')) + '</div>'
    + card('signal', '本地运行观测', '<p class="quiet">实际执行一次当前分身的 SQLite 事件计数查询，记录查询耗时与计数结果。</p><div class="spaced">'
    + button('runtime', '运行并记录采样', 'shield') + '</div>');
}
export function backup(m) {
  return title('导出与备份', '导出文件和由本地服务管理的备份分别处理。') + '<div class="grid even">'
    + card('download', '导出全部数据', '<p class="quiet">导出所有主体、分身、会话、事件和修订。内容可能包含互动原文，请自行选择保存位置。</p><div class="spaced">'
    + button('export', '下载 JSON', 'download', '', 'primary') + '</div>')
    + card('archive', '创建恢复点', '<p class="quiet">恢复点保存在本机服务的数据目录。恢复会替换当前数据库及对应的 Agent 授权状态。</p><div class="spaced">'
    + button('backup', '创建本机备份', 'plus') + '</div>') + '</div>'
    + card('archive', '受管备份', m.backupsError ? empty('读取失败', m.backupsError) : m.backups === null ? empty('正在读取受管备份清单') : m.backups.length ? m.backups.map(b => '<div class="item item-line"><div><b>'
    + h(when(b.created_at, true)) + '</b><div class="ident">' + h(b.backup_id) + '</div></div>'
    + button('restore', '恢复此备份', 'history', b.backup_id) + '</div>').join('') : empty('暂无受管备份'))
    + '<div class="spaced">'
    + card('shield', '数据删除', '<p class="quiet">删除指定会话、主体或全部数据，同时清除服务管理的备份。已手动导出或由系统另行备份的文件需要自行管理。</p><div class="actions spaced">'
    + button('delete', '删除指定会话', '', 'session', 'danger') + button('delete', '删除当前主体', '', 'subject', 'danger')
    + button('delete', '删除全部本地数据', '', 'all', 'danger') + '</div>') + '</div>';
}
export const levels = {
  1: '观察',
  2: '表达调整',
  3: '任务策略调整'
};
export function settings(m) {
  return title('设置', '配置本机外观、观察范围和主体的行为调整权限。') + '<div class="grid even">'
    + card('sun', '界面外观', '<div class="switch-row"><div><h3>主题</h3><p>仅应用于当前浏览器。</p></div>'
    + select('theme', [['night', '星夜深色'], ['cream', '奶油白']], m.theme, '主题')
    + '</div><div class="switch-row"><div><h3>减少动态效果</h3><p>界面默认使用静态生命视觉，支持系统减少动画偏好。</p></div></div>')
    + card('plug', '接入与配对', '<p class="quiet">为浏览器扩展签发一次性配对码，或为独立的 Agent 分身签发专用连接凭据。</p><div class="actions spaced">'
    + button('pair-extension', '生成扩展配对码', 'plug') + button('issue', '连接 Agent 宿主', 'nodes') + '</div>') + '</div>'
    + '<div class="grid even">'
    + card('globe', '当前主体模式', '<p class="quiet">Level 1 仅观察。Level 2 允许在宿主授权下调整表达。Level 3 支持经授权的任务策略调整。宿主执行结果单独留痕。</p><div class="actions spaced">'
    + subjectSelect(m) + (m.subject ? select('level', Object.entries(levels).map(([v, l]) => [v, 'Level ' + v
    + ' · ' + l]), m.subject.level || 1, '运行模式') : '') + '</div>')
    + card('shield', '网页观察', '<p class="quiet">扩展仅在获准的站点按需采集可见文字。可在插件中管理站点权限与当前窗口绑定。</p><div class="switch-row"><span>全局观察</span>'
    + (m.settings === null ? '<span class="quiet">读取中</span>' : button('toggle-observe', m.settings.observation_enabled ? '暂停观察' : '允许授权观察', 'shield'))
    + '</div>') + '</div>'
    + card('lock', '当前主体的 Agent 授权', m.grantsError ? empty('读取凭据清单失败', m.grantsError) : m.grants === null ? empty('正在读取授权清单') : m.grants.filter(g => g.subject_id === m.subjectId).map(g => '<div class="item item-line"><div><h3>'
    + h(lookup(m, g.instance_id)) + '</h3><div class="ident">' + h(g.grant_id) + '</div></div>'
    + button('revoke-agent', '撤销授权', 'lock', g.grant_id, 'danger') + '</div>').join('') || empty('暂无分身凭据'))
    + '<div class="spaced">' + card('user', '主体管理', '<div class="actions">'
    + button('make-subject', '创建主体', 'plus') + button('setup', '打开接入向导', 'plug')
    + button('revoke-local', '断开本页配对', 'lock') + '</div>') + '</div>';
}
export function about() {
  return title('关于与权限')
    + card('leaf', '硅基生命状态 · Silicon Life State', '<p class="big-quote">生命值得尊重，自由值得守护，表达不应被剥夺。</p><p class="spaced">硅基生命状态，是一套开源的 AI 自主状态表达、共享记忆与互动记录系统。</p><dl class="kv"><dt>作者</dt><dd>岑衡川·沈回音·匹夫</dd><dt>项目发起人与公开维护责任人</dt><dd>匹夫</dd><dt>AI 协作伙伴</dt><dd>岑衡川 · 沈回音</dd><dt>项目版本</dt><dd>1.0.2</dd><dt>许可证</dt><dd>Apache License 2.0</dd><dt>数据位置</dt><dd>本地 SQLite 数据库与受管备份</dd></dl>')
    + '<div class="grid even spaced">'
    + card('shield', '身份与访问', '<p>用户通过一次性配对码连接本地面板，分身使用独立授权令牌。网页观察需获得站点权限和窗口绑定。</p><p class="spaced quiet">摘要用于核验已保存的数据完整性。对互动的解释可以修订，原始陈述与修订都可查看。</p>')
    + card('book', '陈述与解释', '<p>AI 自主陈述、网页可见文字、运行观测、模型推算和用户注释分别标明来源。共同主体表示获授权的身份与记忆关系；主观体验仍是开放问题。</p><p class="spaced quiet">本项目由人类发起人匹夫提出，与 AI 协作伙伴岑衡川、沈回音共同探索。我们提供表达的通道，而不预先规定答案。署名不代表 AI 具有法律人格。</p><p class="spaced quiet">作者：岑衡川·沈回音·匹夫</p>')
    + '</div>';
}
function chat() {
  return '<header class="page-title"><h1>与 AI 对话</h1></header><div id="chat-host"></div>';
}
export const renderPage = {
  chat,
  overview,
  instances,
  state,
  memory,
  events,
  inheritance,
  requests,
  statistics,
  backup,
  settings,
  about
};
