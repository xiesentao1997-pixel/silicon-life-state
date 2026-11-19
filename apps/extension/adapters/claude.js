globalThis.slsAdapter = {
  key: 'claude', origin: 'https://claude.ai',
  selectors: ['[data-is-streaming] .font-claude-response', '[data-testid="assistant-message"]', '.font-claude-response'],
  excludes: '[data-testid="user-message"], [data-testid*="thinking"]'
};
