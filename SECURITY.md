# Security and data / 安全与数据

- Codex SQLite and JSONL sources are read-only. Apply writes a separate compact Markdown report; it cannot replace live context.
- Selected text and neighboring segments go to Vercel AI Gateway / TypeSafe. Redaction and regex skipping are best-effort controls, not a guarantee that all sensitive information is detected.
- Local API access requires a bearer token and rejects foreign Host / Origin headers. Keep service and CDP endpoints bound to loopback.
- Saved API Keys use a separate owner-readable/writable (0600) file. They are not encrypted. Local reports can contain private excerpts and paths.
- Never upload the application data directory, `.env` files, `runtime.json`, browser debug profiles or real transcripts.
- This is experimental desktop integration; it depends on application internals. Do not expose CDP to a network.

中文：原始 Codex 数据只读，Apply 只生成独立 Markdown。模型调用会外发选定文本和相邻上下文；脱敏及正则过滤不能保证发现所有秘密。服务及 CDP 仅用于本机回环访问。Key 以独立 0600 文件保存，但未加密；报告可能包含私密内容和路径。请勿上传环境文件、应用数据目录、运行令牌、调试配置或真实对话。

For vulnerabilities, use GitHub's private vulnerability reporting if the repository offers it. Otherwise open a minimal issue requesting a private contact channel; do not include an exploit or secrets in the public issue.

报告漏洞时优先使用仓库提供的 GitHub 私密漏洞报告入口；若未启用，可提交只请求私密联系渠道的简短 Issue，不要公开利用细节或密钥。
