# 隐私和本地脱敏

简历里通常包含姓名、邮箱、手机号、个人主页、地址、身份证号等个人信息。处理这类数据时，默认不要把“完整原始简历”直接发给外部模型。

## 默认模式：联系方式脱敏

默认使用 `--privacy-mode contact`：

```bash
python3 "$SKILL_DIR/scripts/resume_screening_pipeline.py" run \
  --resumes ./resumes \
  --jd ./job_requirements.md \
  --work ./work \
  --output ./results \
  --workers 2 \
  --privacy-mode contact
```

脚本会在本地做这些事：

1. 本地读取 PDF / DOCX / TXT 简历文本。
2. 在发给模型前，把邮箱、手机号、个人链接、身份证号替换成占位符，例如 `[EMAIL_1]`、`[PHONE_1]`、`[URL_1]`、`[CN_ID_1]`。
3. 把原始联系方式存在本地记录里，不放进模型 prompt。
4. 评分结束后，在最终 Excel 的 `邮箱`、`电话`、`链接` 列合并回本地联系方式。

这种模式适合大多数招聘初筛：模型仍然能看到岗位相关经历、公司、title、项目、技能和教育背景，但不需要看到候选人的联系方式。

不要把 `work/records/`、`work/all_records.json` 或带真实联系方式的结果表上传到公开仓库或社媒。这些本地运行产物可能包含原始联系方式映射。

## 扫描件和图片简历

扫描件 / 图片版简历需要 OCR 才能读。如果开启 `--privacy-mode contact`，脚本会先尝试本地 `pytesseract` OCR，再对文字脱敏；默认不会把原始图片发给视觉模型，因为图片里可能包含完整手机号、邮箱、地址和照片。

本地 OCR 需要安装 Python 依赖以及系统 Tesseract，并保证中文和英文语言包可用。可用 `OCR_LANG` 调整语言，默认 `chi_sim+eng`。如果本地 OCR 不可用，记录会明确标为 `需复核`，不会拿空白文本强行评分。

如果用户确认公司允许把原始图片发给模型，可以显式加：

```bash
--allow-vision-with-pii
```

如果不希望尝试本地 OCR，可以使用 `--no-local-ocr`；此时隐私模式下的图片简历会直接进入人工复核。

## 什么时候需要更严格

如果公司或岗位要求更高隐私保护，可以采用更严格的本地脱敏策略：

- 姓名也替换为 `候选人 C001`。
- 完整地址只保留城市或地区。
- 出生日期、证件号、微信号、QQ 号全部删除。
- LinkedIn / GitHub 等链接不发给模型，只保留“有作品链接 / 有 GitHub / 有 LinkedIn”这类信号。
- 输出给 hiring manager 的版本也可以不含联系方式，只保留候选人 ID。

注意不要删除岗位判断必须的信息。公司、title、行业、工作年限、项目经历、技能、教育背景通常会直接影响匹配判断。

## 可选开源增强方案

当前脚本内置的是轻量规则脱敏，覆盖邮箱、手机号、URL、身份证号等高风险字段。后续可以接入这些开源工具增强：

- Microsoft Presidio / Data Privacy Stack Presidio：通用 PII 检测和匿名化框架，支持规则、NER、自定义 recognizer、文本和图片等场景。
- DataFog：面向 AI agent / LLM 应用的 PII 检测与 redaction，支持 regex、spaCy、GLiNER 等方式。
- scrubadub：轻量文本 PII 清理工具，适合做简单 free-text scrub。

简历专用 NER 项目可以帮助抽取学校、技能、经历等字段，但它们通常不是完整隐私防护方案。招聘场景更适合“通用 PII 脱敏 + 简历字段抽取”组合。

## 交付时怎么解释给 HR

可以这样说：

```text
默认情况下，我会先在本地把邮箱、电话、个人链接和证件号替换成占位符，再把脱敏后的简历文本发给模型。
原始联系方式不会进入模型 prompt，只保存在本地，最后合并回 Excel 方便你联系候选人。
如果简历是扫描件，我不会默认把整张图片发给模型，除非你确认公司允许。
```
