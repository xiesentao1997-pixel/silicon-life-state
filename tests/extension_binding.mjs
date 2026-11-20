// Runs the shipped service worker with an in-memory Chrome event/permission adapter.
// The native extension entry point is separately covered by extension_browser.py.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const handlers = {};
const data = {};
const live = new Set([1,2]);
const urls = {};
const local = {};
const channel = name => ({addListener: callback => {handlers[name] = callback;}});
const runtimeId = 'a'.repeat(32);
const panelUrl = 'chrome-extension://' + runtimeId + '/panel.html';
globalThis.chrome = {
  runtime: {id:runtimeId, getURL: file => 'chrome-extension://' + runtimeId + '/' + file,
    onInstalled:channel('install'), onStartup:channel('startup'), onMessage:channel('message')},
  storage: {local:{get:async()=>({...local}),set:async vals=>Object.assign(local,vals),remove:async k=>{delete local[k];}},session:{get:async()=>({...data}), set:async vals => Object.assign(data,vals),
    remove:async k=>{delete data[k];}}, onChanged:channel('changed')},
  tabs: {get:async tab => {if (!live.has(tab)) throw new Error('closed'); return {id:tab,url:urls[tab]};},
    onRemoved:channel('removed'),onUpdated:channel('updated')}, alarms:{onAlarm:channel('alarms')}, permissions:{onAdded:channel('added')}
};
const moduleUrl = url => 'data:text/javascript;base64,' + Buffer.from(url).toString('base64');
const extension = new URL('../apps/extension/', import.meta.url);
const api = moduleUrl(readFileSync(new URL('api.js',extension)));
const worker = readFileSync(new URL('worker.js',extension),'utf8').replace("'./api.js'","'"+api+"'");
await import(moduleUrl(worker));
const bind = tabId => new Promise(resolve => handlers.message(
  {action:'bind-tab',tabId,binding:{subject_id:'sub',instance_id:'ins'}},
  {id:runtimeId,url:panelUrl+'?tab='+tabId},resolve
));
assert.equal(handlers.message({action:'bind-tab'}, {id:runtimeId,url:'https://chatgpt.com'},()=>{}),false);
const results = await Promise.all([bind(1),bind(2)]);
assert.equal(results.filter(r=>r.ok).length,1);
assert.equal(Object.keys(data).length,1);
const previous = Number(Object.keys(data)[0].split(':')[1]);
live.delete(previous);
assert((await bind(previous===1?2:1)).ok);
assert.equal(Object.keys(data).length,1);
console.log('PASS · independent tab binding, concurrent collision, sender boundary, retired tab recovery');

const {observedBinding} = await import(api);
const current = previous === 1 ? 2 : 1;
urls[current]='https://chatgpt.com/c/unique-fixture-thread-one';
assert((await bind(current)).ok);
assert.equal((await observedBinding(await chrome.tabs.get(current))).instance_id,'ins');
urls[current]='https://chatgpt.com/c/unique-fixture-thread-two';
assert.equal(await observedBinding(await chrome.tabs.get(current)), null);
assert(!(await bind(current)).ok);
await handlers.removed(current);
urls[current]='https://chatgpt.com/c/unique-fixture-thread-one?focus=1';
assert.equal((await observedBinding(await chrome.tabs.get(current))).instance_id,'ins');
assert(!JSON.stringify(local).includes('fixture-thread'));
console.log('PASS · SPA conversation change isolates observations; reopened confirmed chat restored; disk contains no raw URL');
