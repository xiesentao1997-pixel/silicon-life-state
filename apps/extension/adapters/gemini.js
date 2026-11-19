globalThis.slsAdapter = {
  key: 'gemini', origin: 'https://gemini.google.com',
  selectors: ['model-response message-content', 'model-response .model-response-text', 'model-response .markdown'],
  excludes: 'user-query, thought-panel, model-thoughts, .thoughts-container'
};
