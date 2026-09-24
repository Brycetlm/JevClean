# JevClean

**Keep the context that matters.** A local conversation organizer for Codex, powered by Jev through Vercel AI Gateway.

**English** · [简体中文](README.zh-CN.md)

![JevClean English interface](docs/screenshots/overview-en.jpg)

*Actual JevClean UI with synthetic demo conversations and illustrative classifications. Screenshots are not model quality or performance benchmarks.*

## What it does

- Find Codex conversations by partial keywords, project, task ID or link; show the three most recent conversations.
- Preview message counts before starting, then watch segments flow into Keep / Omit buckets with live counts.
- Configure your own prompt and separate classification criteria. Optional manual review adds a third bucket.
- Control the neighboring context window (default: previous + target + next), batch size and concurrency.
- Skip whole messages with editable regular expressions. Visible defaults are `key` and `apikey`, case-insensitive; matching messages stay local and are kept.
- Configure your own Vercel AI Gateway Key in the UI. Missing credentials open the configuration dialog before classification.
- Review the compact copy, confirm Apply, then export Markdown or copy a handoff prompt.
- Switch between English and Chinese, with four themes: Prism, Fresh, Tech and Plain.

**JevClean produces a new, extractive Markdown copy. It does not delete your original conversations, rewrite Codex JSONL/SQLite files, or replace an active task's context.** Classification is fallible; inspect the preview before continuing with a compact copy.

## Requirements

- **macOS**, Python **3.9+**, and local Codex conversation records (normally `~/.codex`).
- **Node.js 22+** for the optional embedded sidebar. The standalone browser UI uses only Python's standard library.
- A Vercel account with a working **AI Gateway API Key** and access to `typesafe-ai/jev`. Availability, billing and account verification depend on Vercel / TypeSafe; this project does not promise free usage.

The sidebar is an **experimental CDP integration**, not an official Codex plugin or supported extension API. Codex UI/storage updates can break integration. Windows and Linux launchers have not been validated.

## Quick start

1. Download this repository using **Code → Download ZIP**, then extract it. Open Terminal in the extracted project folder.
2. Check your Python version and open the standalone panel:

   ```sh
   python3 --version
   python3 -m context_panel.launch --browser
   ```

   Alternatively, on macOS run `bash Open-JevClean.command`. If double-clicking a downloaded script is unavailable, use this terminal command.
3. In [Vercel AI Gateway](https://vercel.com/ai-gateway), open your account/team dashboard and create an AI Gateway API Key. See the [official quick start](https://vercel.com/docs/ai-gateway/getting-started) and [TypeSafe API documentation](https://vercel.com/docs/ai-gateway/sdks-and-apis/typesafe).
4. Click **API Key** in JevClean, paste your own Key and save. Saving does not validate its balance or start a model request.
5. Select a conversation. Check the message count, automatic keeps and regex skips. Adjust **Prompts** if needed, then click **Organize**.
6. When classification finishes, click **Preview & apply…**, inspect the compact copy and confirm. Download the approved Markdown or copy a handoff prompt to a new task.

The launcher opens an authenticated localhost URL. Opening bare `http://127.0.0.1:8766/` in a new browser session may require relaunching to supply the access token. Do not share that URL/token.

### Embed in the Codex sidebar

```sh
node --version
python3 -m context_panel.launch
```

Or run `bash Start-JevClean.command`. The launcher attaches to a local CDP listener on port **9231**. If none exists, it attempts to open a separate debug-profile Codex window; your original window remains open. This may require signing in again, and can result in **two app windows/processes**.

In the CDP-enabled window, click **JevClean** below **Explore** in the left navigation. Drag the panel header to move it. Keep the bridge terminal running; Ctrl+C removes the injected panel. New-task prefill is available in embedded mode and still requires you to send the new task yourself.

Reload after a source update:

```sh
python3 -m context_panel.launch --reload
```

If the sidebar cannot attach, use `--browser`. A debug endpoint exposes control of the app: keep it on loopback and do not expose it to other machines. See [implementation notes](context_panel/README.md) for details and troubleshooting.

## Configuration

![English settings](docs/screenshots/settings-en.jpg)

| Setting | Default | Behavior |
| --- | --- | --- |
| Regex skip rules | `key`, `apikey` | One Python regex per line; any case-insensitive substring match skips the entire message. Empty disables. `keyboard` also matches the defaults. |
| User-message classification | On | Turning it off protects user messages. |
| Manual review | Off | Two classes by default; uncertainty/failure keeps content. On adds Review. |
| Context window | 3 segments | Previous + target + next. Odd numbers 1–21; skipped neighbors are excluded without extending the window. |
| Omit probability threshold | 0.90 | Lower-confidence omissions are kept, or sent to Review when enabled. |
| Segments per request | 5 | Range 1–8. Overlapping context windows share text. |
| Concurrent requests | 2 | Range 1–4. |
| Include tool output | Off | Opt in explicitly; can increase usage. |

Complete segments over 6,000 characters are always kept. Regex matching runs locally before redaction and segmentation; matched messages never become classification targets or neighboring model context. Rules are limited to 20 entries of 500 characters each, with a 3-second matching timeout. These filters are not comprehensive secret detection.

HTTP **502/503/504** batches are requeued with up to two retries. Other queued work can continue while retries wait. Unprocessed/failed content is kept. Stopping cannot undo requests already sent.

### Credentials and storage

The panel's saved Key takes priority over `AI_GATEWAY_API_KEY`, followed by an explicitly selected environment file:

```sh
python3 -m context_panel.launch --browser --env-file /path/to/your.env
```

`JEV_ENV_FILE` can supply that path. No personal environment-file location is built into the distributed launchers. Set `CODEX_HOME` if your Codex records live elsewhere.

Local configuration, credentials and reports live under `~/Library/Application Support/JevContext/` (the legacy directory name is retained for compatibility). `credentials.json` has owner-only file permissions, **is not encrypted**, and is never returned by the API. Reports may contain private conversation excerpts. Do not commit or share this data directory.

Only selected readable conversation text and neighboring context are sent to **Vercel / TypeSafe** for classification. The tool uses best-effort redaction; review your data before sending it. It does not parse encrypted compaction data or read unrelated files across the disk. See [SECURITY.md](SECURITY.md).

## Themes

![English theme picker](docs/screenshots/themes-en.jpg)

Themes and language are independent of classification rules. Custom prompts and conversation content are not automatically translated.

## Development

There are no third-party runtime dependencies. Tests use synthetic data and mocked model responses.

```sh
python3 -m unittest discover -s context_panel -t . -p 'test_*.py' -v
node --test context_panel/test_renderer.mjs

# Optional browser regression tests (development dependencies only)
npm install
npx playwright install chromium
npm run test:ui
```

Main files: `context_panel/core.py` (transcript parsing / requests), `server.py` (local API), `web/` (UI), `cdp.mjs` and `renderer.mjs` (experimental integration). `scripts/demo.py` serves synthetic screenshot fixtures without reading your Codex data or calling Jev.

```sh
python3 scripts/demo.py
# Open http://127.0.0.1:8777/#token=demo-only
python3 scripts/package_release.py
```

The packager uses an explicit file allowlist and produces a source ZIP and checksums under `dist/`; local credentials, reports, caches, Git metadata and historic experiment outputs are excluded. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE). Independent community project; not affiliated with or endorsed by OpenAI, Vercel or TypeSafe. Their names identify the services JevClean integrates with.
