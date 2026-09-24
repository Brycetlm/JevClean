"""Build a source-only release using an explicit public-file allowlist."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ['README.md', 'README.zh-CN.md', 'LICENSE', 'CONTRIBUTING.md', 'SECURITY.md', '.gitignore', 'package.json',
              'Open-JevClean.command', 'Start-JevClean.command', 'Reload-JevClean.command',
              '启动Jev侧栏.command', '打开Jev整理.command', '重新加载Jev侧栏.command']
PANEL_FILES = ['__init__.py', 'core.py', 'server.py', 'launch.py', 'regex_filter.py', 'cdp.mjs', 'renderer.mjs', 'prefill.js',
               'test_core.py', 'test_workflow.py', 'test_credentials.py', 'test_launch.py', 'test_renderer.mjs', 'test_ui.mjs', 'README.md']
WEB_FILES = ['index.html', 'app.js', 'flow.js', 'i18n.js', 'style.css']
FILES = ROOT_FILES + ['context_panel/' + name for name in PANEL_FILES] + ['context_panel/web/' + name for name in WEB_FILES]
FILES += ['scripts/demo.py', 'scripts/package_release.py']
FILES += ['docs/screenshots/%s-%s.jpg' % (kind, lang) for kind in ('overview', 'settings', 'themes') for lang in ('en', 'zh')]


def main():
    output = ROOT / 'dist'
    output.mkdir(exist_ok=True)
    stage = output / 'JevClean'
    # Replace only the generated staging tree, never the working source/data directory.
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir()
    checksums = {}
    for name in FILES:
        source = ROOT / name
        if source.is_symlink() or not source.is_file():
            raise SystemExit('Missing or unsafe public file: ' + name)
        data = source.read_bytes()
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        if name.endswith('.command'):
            target.chmod(0o755)
        checksums[name] = hashlib.sha256(data).hexdigest()
    version = json.loads((ROOT / 'package.json').read_text())['version']
    archive = output / ('JevClean-%s-source.zip' % version)
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in FILES:
            z.write(stage / name, 'JevClean/' + name)
    (output / 'SHA256SUMS.txt').write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n')
    (output / 'file-manifest.json').write_text(json.dumps(checksums, indent=2, ensure_ascii=False) + '\n')
    print('Packaged %s public files: %s' % (len(FILES), archive))


if __name__ == '__main__':
    main()
