# SQT Read

基于科学问题追踪法（Scientific Question Tracking）的论文阅读技能。围绕三个问题组织阅读：**论文实际在问什么、作者回答了什么、已检查的证据支持到哪里。**

正式发布版 **0.5.1**，基于 `sqt-read-lab 0.5.1` 的独立存档。保留该版阅读规则、状态结构和四个执行脚本；整理名称、入口、依赖与发布流程。未合入后续 0.5.1.1 / 0.5.1.2 的论证图改版。

## 能做什么

- 预读：识别研究对象、科学问题、材料边界与下一步。
- 精读：逐项连接 Q（问题）、C（命题）、E（证据），区分支持、受限支持、反证与待判。
- 呈现：默认生成关键关系图、简短正文和同文件证据附录；按真实端点绘制箭头，关系过密时分图。
- 接续：保留来源身份、实际已读范围、修订与下一步；内容或关系含义改变后要求重新复核。
- 相关任务：复现准备、用户要求的跨论文比较、写作主张核查。

本技能供 AI 助手执行。Python 脚本负责 PDF 定位、状态检查及已复核报告的本地生成，不自动完成论文科学判断，不独立调用语言模型或绘图 API。

## 安装

技能目录的结构是 `sqt-read/SKILL.md`，同级包含 `agents/`、`references/` 和 `scripts/`。

### Codex

下载 [发布包](dist/sqt-read-v0.5.1.zip)，将其中完整的 `sqt-read` 目录放入 `$CODEX_HOME/skills/`；未设置 `CODEX_HOME` 时放入用户主目录的 `.codex/skills/`。重新打开会话以加载技能。

也可把仓库直接克隆到技能目录：

```sh
git clone https://github.com/yitang4math/sqt-read.git ~/.codex/skills/sqt-read
# 或使用 Gitee
git clone https://gitee.com/yitang4math/sqt-read.git ~/.codex/skills/sqt-read
```

如果目标已有同名技能，先另存旧目录，再安装；旧阅读报告与状态另行保留。`sqt-read-lab` 可继续留在独立目录，使用技能名称明确选择版本。

其他支持 `SKILL.md` 的助手可将完整目录放入其技能目录；具体发现方式由宿主决定。仅把 `SKILL.md` 粘贴到聊天中不能提供本地脚本。

### 脚本依赖

Python **3.9+**。建议在独立虚拟环境中安装：

```sh
python -m venv .venv
# Windows PowerShell
.venv/Scripts/python -m pip install -r requirements.txt
# Linux / macOS
.venv/bin/python -m pip install -r requirements.txt
```

后续命令中的 `python` 指向已安装依赖的解释器。`PyMuPDF` 用于 PDF 定位和页面渲染，`Pillow` 用于本地关系图。中文图另需系统中文字体，可通过报告入口的 `--font` 指定字体文件；缺字体或绘图依赖时明确退化为 Mermaid。阅读流程本身仍可使用宿主已验证的 PDF 工具。

## 使用

在支持技能调用的助手中输入：

```text
使用 $sqt-read 预读这篇论文，识别科学问题、作者回答和仍需核查的证据。
使用 $sqt-read 精读这篇论文，检查与我的目标相关的关键材料，生成阅读报告和接续状态。
使用 $sqt-read 核查这段写作主张，逐项说明引用支持范围与缺少的限定。
```

未指定模式时先预读；多篇输入默认逐篇独立判断。只有明确要求比较、综合或综述时才跨论文综合。

PDF 定位工具（在仓库或技能目录中执行）：

```sh
python scripts/paper.py inspect paper.pdf
python scripts/paper.py read paper.pdf --pages 1-2 --limit 12000 --save packet.json
python scripts/paper.py search paper.pdf --query "limitation" --limit 10
python scripts/paper.py render paper.pdf --page 3 --out page-3.png
python scripts/paper.py verify-state reading.state.json
```

完成实际阅读和语义复核后，按照 [状态规范](references/state.md) 保存 Q/C/E、正文、图关系及其复核绑定，再生成报告：

```sh
python scripts/report.py reading.state.json --out reading.md
# 指定字体或选择文字布局
python scripts/report.py reading.state.json --out reading.md --font /path/to/chinese-font.ttf
python scripts/report.py reading.state.json --out reading-text.md --layout text
```

图文件写入报告旁的 `reading.assets/`。默认拒绝覆盖已有报告及图目录；确需更新时加 `--overwrite`。渲染不会自动绑定新判断，不能用重新绑定掩盖未经复核的内容。

## 版本与兼容

技能实现版本 `0.5.1` 与 SQT 方法协议 `2.0/2.1` 是两套编号。正式发布保留实现版本，发布标签为 `v0.5.1`。

`schema_version` 保持 1，兼容原 0.5.1 的状态与可靠复核绑定。PDF 提取器标识 `sqt-read-lab-pages-2-native` 和缓存名称保留，用于避免仅因改名失去来源定位兼容性。旧 0.3 状态可按其原格式输出；转为图版必须实际补齐展示信息并复核。0.5.1.1/0.5.1.2 的 `argument` 图格式不在此版支持范围内。

## 验证与发布

```sh
python -m unittest discover -s tests -v
python tools/check_release.py
python tools/build_release.py
```

发布包只包含入口、界面元数据、必要参考和脚本，不包含测试临时文件、论文 PDF、个人阅读状态或缓存。`dist/SHA256SUMS` 提供包校验值；`dist/manifest.json` 记录包内文件哈希。发布验证与边界见 [RELEASE.md](RELEASE.md)，变更见 [CHANGELOG.md](CHANGELOG.md)。

## 仓库

- GitHub：<https://github.com/yitang4math/sqt-read>
- Gitee：<https://gitee.com/yitang4math/sqt-read>

维护者：yitang4math。第三方依赖按各自许可证使用；本次未替权利人选择开源许可证。
