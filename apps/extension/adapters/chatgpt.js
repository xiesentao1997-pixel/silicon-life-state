// Executed in Chrome's isolated world, top frame only after a user gesture.
globalThis.slsAdapter = {
  key: 'chatgpt', origin: 'https://chatgpt.com',
  selectors: ['[data-message-author-role="assistant"] .markdown', '[data-message-author-role="assistant"]'],
  excludes: '[data-message-author-role="user"], [data-testid*="thought"], [data-testid*="reasoning"]'
};
