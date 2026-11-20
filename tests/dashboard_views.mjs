// Feed a real disposable Store snapshot on stdin. No DOM or browser is emulated.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {nav, renderPage, sources} from '../apps/dashboard/views.js';

const snapshot = JSON.parse(readFileSync(0, 'utf8'));
const populated = {
  ...snapshot, subject: snapshot.subjects[0], subjectId: snapshot.subjects[0].subject_id,
  instanceId: '', measure: 'valence', range: '7', q: '', source: '', stage: '',
  eventLimit: 50, backups: [], grants: [], settings: {observation_enabled: true}, theme: 'night',
};
const blank = {
  ...populated, subjects: [], instances: [], sessions: [], subject: null, subjectId: '',
  events: [], requests: [], report_states: [], memory: {common: [], disputed: [], proposals: [], decisions: []},
  stats: {confirmed_hostile: 0},
};
for (const view of Object.values(renderPage)) {
  assert.match(view(populated), /<h1>/);
  assert.match(view(blank), /<h1>/);
}
const overview = renderPage.overview(populated);
assert.ok(!nav.flatMap(([,items])=>items).some(([key])=>key==='chat'));
assert.ok(overview.includes('连接我的 AI') && !overview.includes('API 密钥'));
assert.ok(renderPage.pet(populated).includes('只读配对码'));
assert.ok(overview.includes('&lt;em&gt;字面文本&lt;/em&gt;'));
assert.ok(!overview.includes('<em>字面文本</em>'));
assert.ok(overview.includes('测试边界原文'));
assert.ok(overview.includes('原因未知'));
const readerId = snapshot.instances.find(instance => instance.name === '阅读分身').instance_id;
const homeWithPriorFilter = renderPage.overview({...populated, instanceId:readerId});
assert.equal((homeWithPriorFilter.match(/<circle class="chart-point/g) || []).length, 3);
assert.ok(homeWithPriorFilter.includes('class="chart-point previous"'));
assert.ok(!homeWithPriorFilter.includes('· 0.91 ·'));
assert.ok(homeWithPriorFilter.includes('· 0.65 · 当前版本'));
assert.equal((renderPage.state({...populated, instanceId:readerId}).match(/<circle class="chart-point/g) || []).length, 1);
assert.ok(!renderPage.overview(blank).includes('class="chart-point"'));
assert.ok(overview.includes('共享状态分布'));
const distribution = overview.split('共享状态分布')[1].split('</section>')[0];
assert.ok(distribution.includes('&lt;em&gt;字面文本&lt;/em&gt;'));
assert.ok(!distribution.includes('阅读窗口自己的状态'));  // private report
assert.ok(distribution.includes('共享与修订历史'));
assert.ok(overview.includes('data-act="event"'));
assert.ok(renderPage.instances(populated).includes('data-act="rename-instance"'));
assert.ok(renderPage.settings(populated).includes('data-act="rename-subject"'));
const memory = renderPage.memory(populated);
assert.ok(memory.includes('部分采纳'));
assert.ok(memory.includes('仅采纳共享描述中的文本'));
for (const [source,[label]] of Object.entries(sources)) {
  const html = renderPage.events({...populated, source});
  assert.ok(html.includes('>'+label+'</span>'));
  assert.ok(html.includes('class="item"'));
}
const req = renderPage.requests(populated);
assert.ok(req.includes('已提出'));
assert.ok(req.includes('data-act="request"'));
assert.ok(!req.includes('data-act="request-stage"'));
console.log('11 populated and 11 empty pages; consent, requests, input escaping, and all 5 sources passed.');
