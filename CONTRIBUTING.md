# Contributing / 参与贡献

Small, focused pull requests are welcome. Include the behavior change, reproduction steps and relevant test results. Run Python tests and the renderer tests from the README; run the browser regression for UI changes. All fixtures must be synthetic. Add both English and Chinese UI strings, and update both READMEs when public behavior changes.

欢迎提交范围清晰的 PR，说明行为变化、复现方法和测试结果。按 README 运行 Python 与 renderer 测试；界面修改另跑浏览器回归。测试材料必须为合成数据；新增系统文案须补齐中英文，公开行为变化同步更新两份 README。

Do not include API Keys, real transcripts, local reports, environment files, runtime tokens, private endpoints or personal paths. Do not weaken read-only transcript access or the Apply confirmation gate. Sidebar compatibility fixes should identify the app version and UI behavior without attaching private logs.

请勿提交密钥、真实对话、本机报告、环境文件、运行令牌、私有接口或个人路径。保持对话源只读以及 Apply 确认流程。侧栏兼容性修复可说明应用版本与界面行为，不附带私密日志。

Screenshots use `scripts/demo.py`. Capture the actual interface in both languages and label synthetic results as demonstrations. No real model call is required to run tests or create screenshots.

截图使用 `scripts/demo.py`，分别截取真实中英文界面，标明分类结果为演示数据。测试和截图都不需要真实模型调用。
