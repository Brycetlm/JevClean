# JevClean

**留下关键信息，继续下一段工作。** 在本机整理 Codex 对话，通过 Vercel AI Gateway 调用 Jev 分类。

[English](README.md) · **简体中文**

![JevClean 中文界面](docs/screenshots/overview-zh.jpg)

*截图来自真实 JevClean 界面，使用合成对话及演示分类结果，不代表模型准确率或性能基准。*

## 功能

- 按标题片段、项目、任务 ID 或链接搜索 Codex 对话，首页显示最近 3 个对话。
- 开始前统计消息数，整理时以信息流展示段落进入「保留／省略」桶，同步显示数量。
- 自定义整体提示词与独立分类标准；可开启手动复核，增加第三个分类桶。
- 配置相邻上下文窗口（默认前一段＋当前段＋后一段）、批次大小和并发数。
- 通过正则跳过整条消息。显式默认 `key`、`apikey`，忽略大小写；命中消息本地保留，不发送给 Jev。
- 在界面配置自己的 Vercel AI Gateway Key；没有 Key 时点击整理会引导配置。
- 预览精简稿，确认 Apply 后导出 Markdown，或复制交接提示到新任务。
- 中英文切换，以及炫彩、清新、科技、朴素四套皮肤。

**JevClean 生成新的抽取式 Markdown 副本，不删除原对话、不修改 Codex JSONL/SQLite，也不替换活跃任务的上下文。** 模型分类可能出错，继续使用精简稿前应核对预览。

## 环境要求

- **macOS**、**Python 3.9+**，以及本机 Codex 对话记录（通常在 `~/.codex`）。
- 侧栏嵌入模式需要 **Node.js 22+**；独立浏览器模式仅使用 Python 标准库。
- Vercel 账户、可用的 **AI Gateway API Key**，以及 `typesafe-ai/jev` 访问权限。可用性、计费与账户验证以 Vercel / TypeSafe 为准，不承诺免费使用。

侧栏是**实验性的 CDP 集成**，不是官方 Codex 插件或稳定扩展接口。Codex 界面或数据格式更新可能影响兼容性；尚未验证 Windows / Linux 启动器。

## 快速开始

1. 在 GitHub 点击 **Code → Download ZIP**，解压后在项目目录打开终端。
2. 检查 Python 版本，启动独立界面：

   ```sh
   python3 --version
   python3 -m context_panel.launch --browser
   ```

   macOS 也可运行 `bash Open-JevClean.command`。如果下载后无法双击脚本，使用上述终端命令。
3. 进入 [Vercel AI Gateway](https://vercel.com/ai-gateway)，在自己的账户／团队控制台创建 AI Gateway API Key。可参考[官方快速开始](https://vercel.com/docs/ai-gateway/getting-started)与 [TypeSafe API 文档](https://vercel.com/docs/ai-gateway/sdks-and-apis/typesafe)。
4. 点击 JevClean 顶部 **API Key**，粘贴自己的 Key 并保存。保存不会验证余额，也不会发起分类请求。
5. 选择对话，核对消息数、自动保留及正则跳过数量；需要时调整「提示词设置」，再点「一键整理」。
6. 分类完成后点击「预览并应用…」，核对精简稿并确认，再下载 Markdown 或复制交接提示到新任务。

启动器会打开带访问凭证的本地地址。直接在新的浏览器会话访问 `http://127.0.0.1:8766/` 可能需要重新运行启动器取得访问凭证，不要分享该地址中的 Token。

### 嵌入 Codex 侧栏

```sh
node --version
python3 -m context_panel.launch
```

也可以运行 `bash Start-JevClean.command`。启动器连接本机 **9231** 端口的 CDP；不存在时尝试打开独立调试配置的 Codex 窗口，原窗口保持运行。这可能需要重新登录，也可能出现**两个应用窗口／进程**。

在开启 CDP 的窗口中，点击左侧「探索」下方的 **JevClean**。拖动面板标题栏可以移动位置。保持桥接终端运行，Ctrl+C 会卸载注入面板。嵌入模式支持预填新任务，仍需用户自行发送。

更新源码后重新加载：

```sh
python3 -m context_panel.launch --reload
```

侧栏无法挂载时用 `--browser`。CDP 调试端口具备应用控制能力，只应绑定本机回环地址，不要暴露到其他机器。更多细节见[实现说明](context_panel/README.md)。

## 配置

![中文设置](docs/screenshots/settings-zh.jpg)

| 设置 | 默认值 | 含义 |
| --- | --- | --- |
| 正则跳过 | `key`、`apikey` | 每行一条 Python 正则，忽略大小写，任一包含匹配即跳过整条消息；清空关闭。默认也会匹配 `keyboard`。 |
| 用户消息参与判断 | 开启 | 关闭后用户消息直接保留。 |
| 手动复核 | 关闭 | 默认两类，不确定／失败时保留；开启后增加「待复核」。 |
| 上下文窗口 | 3 段 | 前一段＋当前段＋后一段，支持 1–21 奇数；排除跳过邻居后不补入更远消息。 |
| 省略概率门槛 | 0.90 | 低于门槛的省略建议保留；开启复核时进入待复核。 |
| 每批段落数 | 5 | 范围 1–8，重叠上下文去重。 |
| 并发批数 | 2 | 范围 1–4。 |
| 包含工具输出 | 关闭 | 手动开启，可能增加用量。 |

超过 6000 字符的完整段落直接保留。正则在脱敏和分段前匹配整条抽取消息，命中消息既不成为判断目标，也不进入其他目标的相邻上下文。最多 20 条规则，每条最多 500 字符，匹配超时为 3 秒。这些规则不代表完整的秘密识别能力。

HTTP **502/503/504** 会把失败批次放回队尾，最多重试两次；其他批次可继续执行。失败及未处理内容保留。停止整理不能撤销已发出的请求。

### Key 与本机存储

面板保存的 Key 优先于环境变量 `AI_GATEWAY_API_KEY`，最后读取用户明确指定的环境文件：

```sh
python3 -m context_panel.launch --browser --env-file /path/to/your.env
```

也可以用 `JEV_ENV_FILE` 指定路径。发布版启动器不内置个人环境文件位置。对话记录不在默认位置时可设置 `CODEX_HOME`。

设置、凭据、报告保存在 `~/Library/Application Support/JevContext/`（为兼容旧版保留目录名）。`credentials.json` 仅当前系统用户可读写，**文件未加密**，接口不回显 Key。报告可能包含私密对话摘录，不要提交或分享该目录。

分类会将所选可读对话片段及相邻上下文发送到 **Vercel / TypeSafe**。自动脱敏只作尽力识别，外发前请检查材料。程序不解析加密压缩数据，也不全盘扫描无关文件。见 [SECURITY.md](SECURITY.md)。

## 皮肤

![中文皮肤选择](docs/screenshots/themes-zh.jpg)

皮肤、语言与整理规则独立；自定义提示词和对话正文不会自动翻译。

## 开发

运行时没有第三方依赖。测试使用合成数据和模拟模型响应。

```sh
python3 -m unittest discover -s context_panel -t . -p 'test_*.py' -v
node --test context_panel/test_renderer.mjs

# 可选：界面回归，仅开发时需要
npm install
npx playwright install chromium
npm run test:ui
```

核心文件：`context_panel/core.py`（记录解析／模型请求）、`server.py`（本地 API）、`web/`（界面）、`cdp.mjs` 和 `renderer.mjs`（实验性集成）。`scripts/demo.py` 使用合成数据运行截图演示，不读取个人 Codex 数据，不调用 Jev。

```sh
python3 scripts/demo.py
# 打开 http://127.0.0.1:8777/#token=demo-only
python3 scripts/package_release.py
```

打包脚本使用明确的文件清单，在 `dist/` 生成源码 ZIP 和校验值；排除凭据、报告、缓存、Git 元数据及早期试验输出。贡献指南见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

[MIT](LICENSE)。独立社区项目，与 OpenAI、Vercel、TypeSafe 无隶属或背书关系；名称仅用于说明接入的服务。
