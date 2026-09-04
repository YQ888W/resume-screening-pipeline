# 简历批量筛选流水线

把「岗位需求 + 一批简历」变成可复查的初筛表。AI 只做辅助初筛，不替招聘负责人做最终约面或淘汰决定。

给 Cursor / Codex / Claude 用时，把它当作 Agent Skill：你用自然语言说要筛什么、简历在哪，agent 会按 `SKILL.md` 建运行目录、下载或收集简历、先小样本再全量，并产出 Excel。招聘同学不一定要自己跑命令。

## 它能做什么

- 从本地文件夹、邮箱附件/正文、飞书、ATS 或云盘收集简历，统一放到本次 `resumes/`
- 对照你确认过的 JD 做初筛，输出 `推荐` / `备选` / `不推荐` / `需复核`
- 默认先在本地去掉电话、邮箱、个人链接和证件号，再把文本发给智谱官方 API
- 先跑 3–5 份小样本；你在 Excel 黄列里改判断后，可以校准口径再全量
- 口径变了可以先回看旧池，不必马上重跑全量 AI
- 需要时把结果写入飞书多维表格（电话、邮箱独立成列，不自动填约面）

它**不会**做的事：把邮件主题或学校预筛规则当成完整 JD；在 JD 未确认时全量打分；用 OpenRouter 或其他代理模型。

## 最快用法：直接跟 agent 说

把本仓库装到 agent 能读到的 skills 目录后，在对话里点名这个 skill，并说清两件事：**简历在哪**、**要招什么样的人**。

```text
用 resume-screening-pipeline 帮我筛简历。
这是 JD：
<直接粘贴 JD，或用自然语言说 must-have / 一票否决>
简历在这个文件夹：<本地路径>
先跑 5 份小样本，等我确认口径后再全量。
```

简历还在邮箱时：

```text
用 resume-screening-pipeline 处理邮箱里的简历。
我是腾讯企业邮箱，账号是 xxx@company.com。
先增量下载最近新到的、标题里包含「财务经理」的附件。
下载完先停下来，等我确认完整 JD 再筛。
```

口径变了、想翻旧池时：

```text
这个岗位口径变了。新 JD 还没有，先按我刚说的回看旧池。
不要重跑全量 AI。
```

要写入飞书表时，把表链接一并丢给 agent。它应先读现表，不自动把「是否约面」改成约面试。

更口语的说明见 [references/hr-quickstart.md](references/hr-quickstart.md)。

## 安装

```bash
git clone https://github.com/YQ888W/resume-screening-pipeline.git
```

让 Cursor / Codex / Claude 能自动用到它：

```bash
# Cursor
ln -s "$(pwd)/resume-screening-pipeline" ~/.cursor/skills/resume-screening-pipeline

# Codex
ln -s "$(pwd)/resume-screening-pipeline" ~/.codex/skills/resume-screening-pipeline

# Claude
ln -s "$(pwd)/resume-screening-pipeline" ~/.claude/skills/resume-screening-pipeline
```

本机筛简历还需要 Python 3 和依赖：

```bash
python3 -m pip install -r requirements.txt
```

扫描件 / 图片简历若要本地 OCR，还需要本机已安装 Tesseract。

## 第一次配置

不要把智谱 Key 或邮箱授权码发进聊天、写进 `.env`，或贴在普通 shell 提示符后面。到**可见终端**里，等脚本出现隐藏输入提示后再粘贴。

```bash
# 把仓库路径换成你的实际路径
export SKILL_DIR="$HOME/.cursor/skills/resume-screening-pipeline"

# 智谱 Key 存进 macOS 钥匙串
python3 "$SKILL_DIR/scripts/resume_screening_pipeline.py" configure-key
python3 "$SKILL_DIR/scripts/resume_screening_pipeline.py" key-status
```

邮箱授权码同样走钥匙串。第一次下载加 `--save-password-to-keychain`，之后同一账号用 `--use-keychain`。日常追加新简历用 `--incremental`，每个岗位单独一个游标文件，例如 `./work/email_cursor_<role>.json`。邮箱服务商和 IMAP 说明见 [references/email-setup.md](references/email-setup.md)。

模型只走智谱官方接口 `https://open.bigmodel.cn/api/paas/v4`：

- 默认 `auto`：不到 20 份用免费 `glm-4.7-flash`，20 份及以上用付费 `glm-4.7-flashx`
- 想省钱：`--performance-mode economy`
- 想尽快：`--performance-mode fast`

## 一次筛选长什么样

agent 会在你的工作目录里建本次运行文件夹，你通常只看 `job_requirements.md` 和 `results/`：

```text
screening-run/
├── job_requirements.md   # agent 根据你的 JD / 口述整理
├── resumes/              # 收集到的简历
├── work/                 # 缓存，一般不用打开
└── results/
    ├── resume_screening_results.xlsx
    ├── 推荐/
    ├── 备选/
    ├── 不推荐/
    └── 需复核/
```

建议顺序：

1. 确认简历来源（本地 / 邮箱 / 飞书 / ATS / 云盘）。没说之前，不要把电脑里碰巧存在的 PDF 当成本次简历。
2. 确认完整 JD。只有岗位名、邮件主题或学校预筛规则时，先下载或预过滤，不要开始 AI 打分。
3. 跑 3–5 份小样本，打开 Excel 抽检。
4. 不同意就改黄列 `人工初筛结果`、`人工初筛判断依据`，保存后让 agent 校准。
5. 口径确认后再全量。
6. 需要的话再写入飞书表。

Excel 里 `推荐` 通常值得先看，`备选` 有缺口，`不推荐` 明显不符，`需复核` 是文件读不清或信息不够，不是拒绝。

## 自己跑脚本（可选）

大多数时候让 agent 执行即可。要自己跑时，先进入本次 `screening-run` 目录：

```bash
python3 "$SKILL_DIR/scripts/resume_screening_pipeline.py" preflight \
  --resumes ./resumes \
  --jd ./job_requirements.md \
  --work ./work \
  --performance-mode auto

python3 "$SKILL_DIR/scripts/resume_screening_pipeline.py" run \
  --resumes ./resumes \
  --jd ./job_requirements.md \
  --work ./work \
  --output ./results \
  --limit 5 \
  --performance-mode economy \
  --privacy-mode contact
```

全量把 `--limit 5` 去掉，并把 `--performance-mode` 改成 `auto`。邮箱增量下载示例见 `SKILL.md`。

## 隐私

- 默认 `--privacy-mode contact`：本地替换联系方式后再发给模型，Excel 再从本地映射还原
- 不要把真实简历、带联系方式的结果表、`work/records/` 提交进 Git
- 扫描件走视觉模型时，可能把原始图片页发给智谱；结果里应标明哪些样本用了视觉解析

## 更多说明

| 文档 | 内容 |
|---|---|
| [SKILL.md](SKILL.md) | agent 必须遵守的完整流程 |
| [references/hr-quickstart.md](references/hr-quickstart.md) | 给招聘同学的口语说明 |
| [references/jd-intake.md](references/jd-intake.md) | JD 门槛和口径整理 |
| [references/criteria-revision.md](references/criteria-revision.md) | 口径变化、旧池回看 |
| [references/feishu-delivery.md](references/feishu-delivery.md) | 写入飞书表 |
| [references/email-setup.md](references/email-setup.md) | 邮箱 IMAP |
| [references/privacy.md](references/privacy.md) | 脱敏边界 |
| [references/model-options.md](references/model-options.md) | 模型和性能模式 |
