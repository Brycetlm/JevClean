(async ({ prompt, cwd, projectId = null }) => {
  if (!prompt?.trim() || !cwd?.startsWith('/')) throw new Error('Missing prompt or absolute cwd');
  const bridge = window.electronBridge;
  if (typeof bridge?.sendMessageFromView !== 'function') throw new Error('Not a Codex host renderer');
  const getState = (key) => new Promise((resolve, reject) => {
    const requestId = `jev-prefill-${crypto.randomUUID()}`;
    const finish = (error, value) => {
      clearTimeout(timer);
      window.removeEventListener('message', receive);
      error ? reject(error) : resolve(value);
    };
    const receive = (event) => {
      if (event.source !== null && event.source !== window) return;
      if (event.source === window && event.origin !== window.location.origin) return;
      const msg = event.data;
      if (msg?.type !== 'fetch-response' || msg.requestId !== requestId) return;
      if (!(msg.status >= 200 && msg.status < 300)) return finish(new Error(`Native fetch failed: ${key}`));
      try { finish(null, JSON.parse(msg.bodyJsonString).value); }
      catch (error) { finish(error); }
    };
    const timer = setTimeout(() => finish(new Error(`Native fetch timeout: ${key}`)), 3000);
    window.addEventListener('message', receive);
    Promise.resolve(bridge.sendMessageFromView({
      type: 'fetch', requestId, method: 'POST',
      url: 'vscode://codex/get-global-state', body: JSON.stringify({ key })
    })).catch(error => finish(error));
  });
  const [projects, selected] = await Promise.all([getState('local-projects'), getState('selected-project')]);
  const normalized = value => value === '/' ? value : value.replace(/\/+$/, '');
  const matches = Object.entries(projects ?? {}).filter(([id, project]) =>
    (!projectId || id === projectId) && project?.rootPaths?.length === 1 &&
    normalized(project.rootPaths[0]) === normalized(cwd));
  const target = matches.length === 1 ? matches[0] : null;
  if (!target) throw new Error('No unambiguous single-root local project matching cwd; refusing project/worktree substitution');
  const project = { type: 'local', projectId: target[0] };
  window.postMessage({
    type: 'navigate-to-route', path: '/',
    state: { codexAppMode: 'codex', project, prefillComposerMode: 'local',
      focusComposerNonce: Date.now(), prefillPrompt: prompt }
  }, window.location.origin);
  return { status: 'dispatched', projectId: project.projectId, cwd, submitted: false };
})
