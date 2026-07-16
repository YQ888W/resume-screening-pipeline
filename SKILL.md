---
name: resume-screening-pipeline
description: 当用户要批量筛选简历、对照 JD 做候选人初筛、从邮箱/招聘网站/飞书/本地文件夹收集简历、生成候选人 Excel 表、按推荐/备选/不推荐分类整理简历，或想把招聘筛选流程做成可复用流水线时使用。本 skill 会先明确岗位需求和简历来源，再进行 pilot 口径确认，最后用可并发、可缓存、可重试的方式批量抽取简历事实并评分。
---

# 简历批量筛选流水线

## 概览

把“岗位需求 + 一批简历”变成可复查的候选人 shortlist。这个 skill 适合高数量简历场景：先用低成本模型抽取简历事实，再用更强模型对照 JD 判断匹配度，保留证据、支持失败重试，并输出 Excel 和分类后的简历文件夹。

这个流程不是让 AI 一次性替 HR 做最终决定，而是让 AI 先按明确标准批量初筛，再让 HR 在本地 Excel 里抽检和纠偏。用户可以直接编辑 `人工初筛结果` 和 `人工初筛判断依据` 两列，保存后让 agent 读取这个 Excel，自动提炼口径修正并重评候选人。

如果用户是没有技术背景的 recruiter，先读 `references/hr-quickstart.md`。不要要求用户先填表或建文件夹；让用户直接提供 JD / 自然语言需求和简历来源，由 agent 负责整理岗位需求、创建运行目录、收集简历并先跑 3-5 份小样本试跑。

如果用户担心简历里的邮箱、手机号、身份证号、个人主页等个人信息被发给模型，先读 `references/privacy.md`。默认使用本地联系方式脱敏模式：发给模型前把这些字段替换成占位符，本地保留映射，最终 Excel 再合并回联系方式。

## 什么时候用

用户这样说时使用：

- “这里有 200 份简历，帮我找最适合这个岗位的人。”
- “对照这个 JD 筛简历，给我一个 Excel。”
- “把简历分成推荐、备选、不推荐。”
- “先从邮箱里把简历下载下来，再筛。”
- “我想把这个简历筛选流程做成可复用 skill。”

如果只有 1-2 个候选人，除非用户明确要求流水线，否则用轻量候选人评估即可。

## 前置确认

正式跑全量前，必须确认三件事。

### 1. 单岗位还是多岗位

先问清楚：

- 这次是单一岗位筛选，还是多个岗位一起分流？
- 如果是多个岗位，岗位之间差异大不大？
- 是否允许候选人被推荐到另一个更匹配的岗位？
- 简历来源里是否带岗位信息？例如邮箱标题、附件文件名、招聘网站字段、飞书表格字段。

建议规则：

- 岗位差异很大时，分开跑，每个岗位单独一个 `job_requirements.md`。
- 多岗位只是同一方向的轻微变体时，可以一起跑，但 JD 里要写清楚每个岗位的 must-have 和 best-fit role 规则。
- 邮箱标题一般会写投递岗位，下载简历时要保留 `_source_manifest.csv`，供后续判断候选人原本投递哪个岗位。

### 2. JD 是否达到最低可用标准

不要在 JD 不清楚时直接跑全量。`job_requirements.md` 至少要包含：

- 岗位名称
- 全职/实习/级别/年限范围
- 地点/远程要求
- must-have
- nice-to-have
- 一票否决项
- 筛选优先级
- 输出语言和推荐标签

如果缺失，不要直接把表单丢给用户。先根据用户粘贴的 JD 或自然语言需求生成 `job_requirements.md`，只追问会影响筛选结果的关键问题。`assets/job_requirements_template.md` 是 agent 整理需求时的内部模板，不是要求用户手动填写的前置步骤。最多可以先跑 3-5 份小样本帮用户发现筛选标准，但不能直接全量。

JD 设计细节见 `references/jd-intake.md`。

### 3. 简历来源

本 skill 的标准输入是本地 `resumes/` 文件夹，但简历可以来自：

- 本地手动整理
- 邮箱附件
- Boss 直聘 / LinkedIn / Indeed 等招聘网站导出
- ATS 导出
- 飞书多维表格附件
- 云盘文件夹

如果用户需要先收集简历，读 `references/resume-sources.md`。如果是邮箱，读 `references/email-setup.md`。

## 推荐文件夹结构

面向 HR 时统一使用这些名字。文件夹由 agent 创建，不要求用户手动准备：

```text
screening-run/
├── job_requirements.md   # 岗位需求表
├── resumes/              # 简历放这里
├── work/                 # 中间缓存，agent 管
└── results/              # 最终结果看这里
```

不要让 HR 理解 `work/`。只告诉他们：最终看 `results/`。如果用户没有提供路径，agent 应在当前工作目录下创建一个新的运行文件夹。

## 执行流程

1. 根据用户粘贴的 JD / 自然语言需求生成 `job_requirements.md`，并建立运行文件夹、`resumes/`、`work/`、`results/`。不要要求用户先手动建目录。

2. 如果简历在邮箱里，先下载附件。例如腾讯企业邮箱：

```bash
python3 scripts/email_attachment_downloader.py \
  --provider tencent-exmail \
  --username you@company.com \
  --password '<客户端专用密码>' \
  --save-dir ./resumes \
  --days-back 30 \
  --subject-keyword 简历
```

3. 盘点简历文件：

```bash
python3 scripts/resume_screening_pipeline.py inventory \
  --resumes ./resumes \
  --work ./work
```

4. 先跑 3-5 份 pilot：

```bash
python3 scripts/resume_screening_pipeline.py run \
  --resumes ./resumes \
  --jd ./job_requirements.md \
  --work ./work \
  --output ./results \
  --limit 5 \
  --workers 1 \
  --privacy-mode contact
```

5. 把 pilot 结果给用户确认。必须根据 `references/pilot-feedback.md` 收集反馈：是否太宽、太严、误杀、漏掉硬性条件、是否确认单岗位/多岗位规则。优先引导用户打开 `results/resume_screening_results.xlsx`，直接在 `人工初筛结果` 和 `人工初筛判断依据` 两列里改。

6. 如果用户直接在 Excel 里填写了人工反馈，读取反馈文件并重评。反馈文件可以是 `results/resume_screening_results.xlsx` 或 `results/screening_summary.csv`。重评时，agent 要把人工反馈总结成筛选口径修正，必要时追加到 `job_requirements.md` 的“小样本试跑后修正”部分，再重新评分：

```bash
python3 scripts/resume_screening_pipeline.py score-only \
  --resumes ./resumes \
  --jd ./job_requirements.md \
  --work ./work \
  --output ./results \
  --feedback-file ./results/resume_screening_results.xlsx \
  --workers 2
```

7. 如果只改了 JD 评分口径，但没有 Excel 反馈，也可以使用 `score-only` 重评 pilot 或已处理记录：

```bash
python3 scripts/resume_screening_pipeline.py score-only \
  --resumes ./resumes \
  --jd ./job_requirements.md \
  --work ./work \
  --output ./results \
  --workers 2
```

8. 用户确认口径后跑全量：

```bash
python3 scripts/resume_screening_pipeline.py run \
  --resumes ./resumes \
  --jd ./job_requirements.md \
  --work ./work \
  --output ./results \
  --workers 2 \
  --privacy-mode contact
```

9. 失败重试并最终整理：

```bash
python3 scripts/resume_screening_pipeline.py retry-failures \
  --resumes ./resumes \
  --jd ./job_requirements.md \
  --work ./work \
  --output ./results \
  --workers 1

python3 scripts/resume_screening_pipeline.py finalize \
  --resumes ./resumes \
  --work ./work \
  --output ./results
```

9. 做 QA。读 `references/quality-checks.md`。

## 模型配置

默认推荐“低成本/限免模型抽取 + 更强模型判断”：

- 抽取层：GLM 或其他低成本模型，读简历、OCR、抽取结构化事实。
- 判断层：更强模型，对照 JD 做最终匹配判断。

这样比把几百份完整简历直接丢给最强模型更便宜、更稳，也更容易缓存和失败重试。GLM 是默认抽取选择，不是硬依赖。详细说明见 `references/model-options.md`。

环境变量：

- `OPENAI_API_KEY`：使用 OpenAI-compatible / OpenRouter / 其他兼容平台时需要。
- `OPENAI_BASE_URL`：默认 `https://openrouter.ai/api/v1`。
- `ZHIPUAI_API_KEY`：可选，用智谱原生 GLM API 时使用。
- `EXTRACT_MODEL`：默认 `z-ai/glm-4.7-flash`。
- `VISION_MODEL`：默认 `z-ai/glm-5v-turbo`。
- `SCREEN_MODEL`：默认 `openai/gpt-4.1-mini`。

API key / base URL 属于一次性环境配置。会用 coding agent 的用户通常可以自己配置；团队化使用时，也可以由管理员统一配置好。配置完成后，日常使用只需要提供 JD / 自然语言需求和简历来源。

本地运行依赖：

```bash
pip install -r requirements.txt
```

## 隐私和脱敏

默认建议开启 `--privacy-mode contact`。脚本会在本地抽取文本后，先把邮箱、手机号、个人链接、身份证号等字段替换成 `[EMAIL_1]`、`[PHONE_1]`、`[URL_1]`、`[CN_ID_1]` 这样的占位符，再把脱敏文本发给模型。原始联系方式只保存在本地运行目录的记录里，并在最终 Excel 的 `邮箱`、`电话`、`链接` 列合并回来。

注意：

- 这个默认模式主要保护联系方式和身份号码，不会默认删除公司、title、学校、城市和工作经历，因为这些通常是判断岗位匹配的必要信息。
- 如果简历是扫描件或图片版，隐私模式下默认不把图片发给视觉模型，避免整张原始简历外传。用户明确接受后才使用 `--allow-vision-with-pii`。
- 如果公司要求更严格的脱敏，例如姓名、完整地址、出生日期也不能发给模型，参考 `references/privacy.md`，可接入 Presidio、DataFog 或 scrubadub 这类本地 PII 工具做增强。

## 速度策略

不要把几百份简历一次性塞给 GLM 或任何模型。这样容易超过上下文、JSON 出错、失败后难恢复，而且一个坏文件可能拖垮整批。

推荐用“每人独立记录 + 并发 + 缓存续跑”：

- pilot 或不稳定供应商：`--workers 1`
- 正常全量：`--workers 2`
- pilot 稳定后提速：`--workers 4`
- 供应商限流少时可尝试：`--workers 6` 或 `--workers 8`

时间预期不要承诺固定分钟数。可说明：5 份 pilot 通常较快；200-300 份应预留较长时间，但可以中断续跑，已完成记录不会重复处理。详细见 `references/performance.md`。

## 输出结果

输出包括：

- `records/C###.json`：每位候选人的抽取和评分缓存。
- `inventory.csv`：文件盘点和解析状态。
- `screening_summary.csv`：筛选总表，包含可让用户填写的人工反馈列。
- `screening_evidence.csv`：详细证据表。
- `resume_screening_results.xlsx`：两张 sheet 的 Excel。
- `推荐/`、`备选/`、`不推荐/`、`需复核/`：分类后的简历副本。

`筛选总表` 默认使用压缩主表，避免 HR 横向拖拽太久。主表只保留初筛决策需要的列：

- `Candidate ID`
- `候选人姓名`
- `AI 初筛结果`
- `人工初筛结果`
- `人工初筛判断依据`
- `匹配结论`：合并一句话推荐理由、must-have 匹配和 nice-to-have 匹配。
- `目前（最近）公司和 title`
- `过往经历概况`
- `需要注意的点`
- `学历背景`：合并学历、学校、专业和毕业时间。实习 / 校招 / 应届岗位可以写得更详细，社招岗位只需保留必要摘要。
- `邮箱`
- `电话`
- `链接`
- `原始文件名`
- `解析状态`

`详细证据表` 继续保留拆开的工作经历、项目/研究、岗位相关证据、技能、工具、语言、量化成果和建议面试问题，用于复查和面试准备。

## Excel 人工反馈闭环

交付 pilot 或全量结果时，要主动告诉用户：

1. 打开 `results/resume_screening_results.xlsx`。
2. 在 `筛选总表` 里抽检候选人。
3. 如果不同意 AI 判断，在 `人工初筛结果` 写自己的判断，例如“其实一般”“不该推荐”“被误杀”“需要复核”。
4. 在 `人工初筛判断依据` 写原因，例如“销售经验有，但客户群体偏 IT，不应进入第一优先级”。
5. 保存 Excel，然后让 agent 读取这个文件重评。

agent 读取 Excel 后要做两件事：

- 对比 `AI 初筛结果`、`人工初筛结果` 和 `人工初筛判断依据`，判断上一轮是否高估、低估、误杀或口径太宽/太严。
- 把可复用的口径修正写回 `job_requirements.md`，再用 `score-only --feedback-file` 重新评分。

`筛选总表` 里预留这些人工反馈列。它们主要用于抽检和纠偏，不要求用户每一行都填写；如果人工判断和 AI 判断基本一致，通常可以留空，用户也可以主动写“认可”作为确认：

- `人工初筛结果`：用户对模型判断的直接看法，尤其是不同意 `AI 初筛结果` 时填写，例如“不该推荐”“其实一般”“被误杀”“需要复核”；“认可”只是可选确认项。
- `人工初筛判断依据`：写清楚为什么，例如“技术很强但完全没有销售经验，不应推荐”。

这两列会放在 `AI 初筛结果` 后面。Excel 中会用浅黄色标出可填写区域，表头用橙色提示。用户手填并保存后，重评命令会读取这两列，让模型对比原初筛结果和人工反馈，自动提取“高估/低估/误杀/口径修正”等校准信息。

用户不用判断“高估/低估/误杀”这些结构化类型，也不用再填最终决定。重评时模型会自己对比原初筛结果和人工反馈，判断上一轮是否高估、低估、误杀或基本正确。

## 结果怎么读

- `推荐`：和 JD 明确匹配，通常值得联系或约面。
- `备选`：有相关信号，但还有缺口，适合二线复查或快速确认。
- `不推荐`：相关性弱，或明显不符合硬性要求。
- `需复核`：文件不可读、信息不足或模型无法安全判断；这不是拒绝。

## 邮箱配置

邮箱下载使用 IMAP。主流配置和排障见 `references/email-setup.md`。

常见 preset：

- `tencent-exmail`：腾讯企业邮箱，`imap.exmail.qq.com:993`
- `qq`：QQ 邮箱，`imap.qq.com:993`
- `gmail`：Gmail，`imap.gmail.com:993`
- `outlook`：Outlook / Microsoft 365，`outlook.office365.com:993`
- `netease-163`：网易 163，`imap.163.com:993`

下载器不保存密码。它会在 `resumes/` 中写入 `_source_manifest.csv` 和 `.email_download_state.json`，用于来源追溯和去重。

## 规则和隐私

- 不要根据文件夹名或邮件来源本身判断候选人是否匹配，只能作为上下文。
- 不要把整批简历塞进一个模型 prompt。
- 不要编造学校、日期、地点、薪资、身份、语言能力或任何简历没写的事实。
- 信息不足时标为 `需复核` 或 `备选`，不要强行判断。
- AI 输出只是筛选辅助，不是最终录用/淘汰决定。
- 简历内容可能会发送给模型 API，必须使用公司允许的供应商。
- 公开分享、社媒截图、GitHub demo 里不要暴露真实候选人姓名、电话、邮箱、简历和邮件来源。
- IMAP 使用客户端专用密码/授权码，不要把邮箱密码写进文件。
