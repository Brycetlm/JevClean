"""Start the local service and attach the panel to a CDP-enabled Codex window."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import urllib.request


def reachable(url):
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=1) as response:
            return response.status == 200
    except Exception:
        return False


def reload_services(data):
    """Explicit, user-triggered reload. Never stop the Codex application itself."""
    runtime_file = data / 'runtime.json'
    if not runtime_file.exists():
        return
    runtime = json.loads(runtime_file.read_text())
    if reachable(runtime['url'] + '/'):
        request = urllib.request.Request(runtime['url'] + '/api/runs',
                                         headers={'Authorization': 'Bearer ' + runtime['token']})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=3) as response:
            if any(run['status'] in ('reading', 'running') for run in json.load(response)):
                raise SystemExit('请先完成或停止 Jev 整理，再重新加载。 / Finish or stop the Jev run before reloading.')
    processes = []
    bridge_file = data / 'bridge-runtime.json'
    if bridge_file.exists():
        processes.append((json.loads(bridge_file.read_text())['pid'], 'context_panel/cdp.mjs', signal.SIGINT))
    processes.append((runtime['pid'], 'context_panel.server', signal.SIGTERM))
    # Verify every PID before stopping anything; stale files must not target another app.
    verified = []
    for pid, marker, sig in processes:
        result = subprocess.run(['ps', '-p', str(pid), '-o', 'args='], capture_output=True, text=True)
        if result.returncode:
            continue
        if marker not in result.stdout:
            raise SystemExit('进程身份不匹配，已停止重载。 / Process identity mismatch; reload cancelled.')
        verified.append((pid, sig))
    for pid, sig in verified:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            continue
        for _ in range(50):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(.1)
        else:
            raise SystemExit('本地服务未退出，请稍后重试。 / Local service has not exited; try again shortly.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', default=os.environ.get('JEV_ENV_FILE'))
    parser.add_argument('--reload', action='store_true', help='Reload Jev service and bridge; leave Codex running')
    parser.add_argument('--browser', action='store_true', help='Open standalone view instead of CDP')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    data = Path.home() / 'Library/Application Support/JevContext'
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.reload:
        reload_services(data)
    if not reachable('http://127.0.0.1:8766/'):
        command = [sys.executable, '-m', 'context_panel.server']
        if args.env_file:
            command += ['--env-file', args.env_file]
        with (data / 'service.log').open('ab') as log:
            subprocess.Popen(command, cwd=root, stdout=log, stderr=log, start_new_session=True)
        for _ in range(30):
            if reachable('http://127.0.0.1:8766/'):
                break
            time.sleep(.2)
        else:
            raise SystemExit('服务启动失败，请查看本地 service.log')
    runtime = json.loads((data / 'runtime.json').read_text())
    if args.browser:
        subprocess.run(['open', runtime['url'] + '/#token=' + runtime['token']], check=True)
        return
    if not shutil.which('node'):
        raise SystemExit('需要 Node.js 22 或以上版本')
    if not reachable('http://127.0.0.1:9231/json/version'):
        app = next((p for p in ['/Applications/ChatGPT.app', '/Applications/Codex.app'] if Path(p).exists()), None)
        if not app:
            raise SystemExit('未找到 Codex / ChatGPT 桌面应用')
        subprocess.run(['open', '-n', '-a', app, '--args', '--user-data-dir=' + str(data / 'cdp-profile'),
                        '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=9231',
                        '--remote-allow-origins=http://127.0.0.1:9231'], check=True)
        for _ in range(60):
            if reachable('http://127.0.0.1:9231/json/version'):
                break
            time.sleep(.25)
        else:
            raise SystemExit('独立窗口未开启 CDP；原有窗口保持不变。可用 --browser 独立打开。')
    print('服务已就绪。连接 CDP 侧栏；保持此进程运行，Ctrl+C 卸载侧栏。', flush=True)
    result = subprocess.run(['node', str(root / 'context_panel/cdp.mjs')], cwd=root)
    if result.returncode:
        raise SystemExit('Jev 侧栏未挂载成功。请保留上方具体错误；本地整理服务仍可使用。')


if __name__ == '__main__':
    main()
