// Take a deliberate selection, bounded by one rendered assistant message.
// Returning a string from executeScript cannot invoke the service or authorize a write.
(() => {
  const spec = globalThis.slsAdapter;
  delete globalThis.slsAdapter;
  if (!spec || location.origin !== spec.origin || window !== top) return {error: '当前页面与已选站点不一致。'};
  const selection = getSelection();
  if (!selection || selection.rangeCount !== 1 || selection.isCollapsed) return {error: '先在网页中选中一段 AI 回答，再预览。'};
  const range = selection.getRangeAt(0);
  const parent = node => node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
  const root = parent(range.commonAncestorContainer)?.closest(spec.selectors.join(','));
  if (!root || root.closest(spec.excludes)) return {error: '选区需要完整位于一条可识别的 AI 回答内。'};
  const excluded = 'button,textarea,input,select,script,style,noscript,[hidden],[inert],[aria-hidden="true"],[contenteditable="true"],details:not([open]),' + spec.excludes;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const fragments = [];
  const blocks = 'p,li,pre,blockquote,h1,h2,h3,h4,h5,h6,td';
  let size = 0;
  let lastBlock = null;
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (!range.intersectsNode(node) || node.parentElement.closest(excluded)) continue;
    // Range geometry excludes display:none; additionally require visible ancestors.
    let visible = true;
    for (let el = node.parentElement; el && visible; el = el.parentElement) {
      const css = getComputedStyle(el);
      visible = css.visibility === 'visible' && css.display !== 'none' && Number(css.opacity) > 0 && css.contentVisibility !== 'hidden';
    }
    if (!visible) continue;
    const part = document.createRange();
    part.selectNodeContents(node);
    if (node === range.startContainer) part.setStart(node, range.startOffset);
    if (node === range.endContainer) part.setEnd(node, range.endOffset);
    if (!Array.from(part.getClientRects()).some(r => r.width > 0 && r.height > 0)) continue;
    const block = node.parentElement.closest(blocks);
    if (fragments.length && block !== lastBlock) { fragments.push('\n'); size++; }
    const fragment = part.toString();
    size += fragment.length;
    if (size > 4000) return {error: '选区超过 4000 字，请缩短后重试。'};
    fragments.push(fragment);
    lastBlock = block;
  }
  const text = fragments.join('').trim();
  return text ? {text, adapter: spec.key} : {error: '选区内没有可归档的可见原文。'};
})()
