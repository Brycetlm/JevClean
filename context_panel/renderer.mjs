// Renderer discovery is separate from mounting so startup can be tested offline.
export function isMainPage(target) {
  if (target.type !== 'page' || !target.webSocketDebuggerUrl) return false;
  try {
    const url = new URL(target.url);
    return url.protocol === 'app:' && url.hostname === '-' && url.pathname === '/index.html';
  } catch { return false; }
}

export async function findRenderer({list, connect, timeout = 30000,
  now = Date.now, sleep = ms => new Promise(resolve => setTimeout(resolve, ms))}) {
  const deadline = now() + timeout;
  let pageCount = 0, matched = false, connected = false;
  do {
    let targets = [];
    try { targets = await list(); } catch { /* Startup may briefly refuse connections. */ }
    pageCount = targets.filter(target => target.type === 'page').length;
    for (const target of targets.filter(isMainPage)) {
      matched = true;
      let client, selected = false;
      try {
        client = await connect(target.webSocketDebuggerUrl);
        connected = true;
        // Mounting uses DOM and CDP bindings, not the optional native prefill API.
        const check = await client.send('Runtime.evaluate', {
          expression: '!!document.body && document.readyState !== "loading"',
          returnByValue: true,
        });
        if (!check.exceptionDetails && check.result?.value === true) {
          selected = true;
          return client;
        }
      } catch { /* Targets can disappear while the app starts or navigates. */ }
      finally { if (!selected) client?.close(); }
    }
    if (now() >= deadline) break;
    await sleep(Math.min(500, deadline - now()));
  } while (now() < deadline);
  const reason = !matched ? '未发现匹配的主页面，可能是应用页面地址已变化' :
    !connected ? '发现主页面，但调试连接未成功' : '已连接主页面，但页面未就绪';
  throw Error(`未能挂载 Jev：${reason}（等待 ${Math.round(timeout / 1000)} 秒，最后发现 ${pageCount} 个页面）。此信息不代表权限不足。`);
}
