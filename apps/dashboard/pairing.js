// Countdown duration comes from the service. Periodic reads also notice consumption,
// code replacement and suspended browser clocks.
export function watchPairCode({node, code, initial, status, setCopyValue}) {
  const time = node.querySelector('[data-pair-countdown]');
  const note = node.querySelector('[data-pair-state]');
  const codeBox = node.querySelector('[data-pair-code]');
  const copy = node.querySelector('[data-act=copy]');
  let current = '';
  let deadline = 0;
  let nextCheck = 0;
  let pending = false;
  let disconnected = false;
  let live = true;
  const descriptions = {
    used: '配对码已使用。需要连接另一个插件时，请重新生成配对码。',
    replaced: '此配对码已被替换。请使用最近生成的配对码。',
    expired: '配对码已过期。请重新生成配对码。',
    unavailable: '配对码不可用。请重新生成配对码。'
  };
  function display() {
    const left = Math.max(0, Math.ceil((deadline - performance.now()) / 1000));
    const state = current === 'active' && left === 0 ? 'expired' : current;
    const usable = state === 'active';
    const clock = usable ? String(Math.floor(left / 60)).padStart(2, '0') + ':' + String(left % 60).padStart(2, '0') : '00:00';
    const message = !usable ? descriptions[state] : disconnected
      ? '正在重新连接本地服务，倒计时按上次核对的有效期限计算。' : '有效期倒计时，限插件使用一次。';
    if (time.textContent !== clock) time.textContent = clock;
    if (note.textContent !== message) note.textContent = message;
    copy.disabled = !usable;
    codeBox.hidden = !usable;
    const shown = usable ? code : '';
    if (codeBox.textContent !== shown) codeBox.textContent = shown;
    setCopyValue(shown);
  }
  function synchronize(result) {
    current = result.state || 'active';
    disconnected = false;
    const remaining = Math.max(0, Math.min(Number(result.expires_in) || 0, 600));
    deadline = performance.now() + remaining * 1000;
    nextCheck = performance.now() + 4000;
    display();
  }
  async function check(force = false) {
    if (!live) return;
    display();
    if (pending || document.hidden || (!force && nextCheck > performance.now())) return;
    if (['used','replaced','expired','unavailable'].includes(current)) return;
    pending = true;
    try {
      const result = await status(code);
      if (live) synchronize(result);
    } catch {
      if (live) {
        nextCheck = performance.now() + 5000;
        disconnected = true;
        display();
      }
    } finally {
      pending = false;
    }
  }
  synchronize(initial);
  const visible = () => { if (!document.hidden) check(true); };
  document.addEventListener('visibilitychange', visible);
  const interval = setInterval(check, 400);
  return () => {
    live = false;
    clearInterval(interval);
    document.removeEventListener('visibilitychange', visible);
  };
}
