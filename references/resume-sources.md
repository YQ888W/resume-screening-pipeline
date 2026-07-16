# 简历来源

本 skill 把本地 `resumes/` 文件夹作为标准输入。真实 HR 工作里，这个文件夹通常来自上游采集步骤。

## 支持的来源

### 本地手动整理

适用于用户已经有 PDF、DOCX、图片版简历的情况。

推荐结构：

```text
screening-run/
├── job_requirements.md
├── resumes/
│   ├── candidate-a.pdf
│   ├── candidate-b.docx
│   └── candidate-c.png
└── results/
```

### 邮箱附件

适用于简历来自招聘网站、内推、猎头、候选人主动投递等邮件附件。

推荐流程：

1. 确认邮箱服务商、账号、是否能使用 IMAP。
2. 确认日期范围、发件人关键词、主题关键词、附件类型。
3. 用 `scripts/email_attachment_downloader.py` 下载附件到 `resumes/`。
4. 保留 `_source_manifest.csv`，记录 message id、发件人、日期、标题、附件名、本地文件名、hash。
5. 再用本 skill 对 `resumes/` 跑 JD 驱动筛选。

腾讯企业邮箱示例：

```bash
python3 scripts/email_attachment_downloader.py \
  --provider tencent-exmail \
  --username you@company.com \
  --password '<客户端专用密码>' \
  --save-dir ./resumes \
  --days-back 30 \
  --subject-keyword 简历
```

通用 IMAP 示例：

```bash
python3 scripts/email_attachment_downloader.py \
  --server imap.example.com \
  --port 993 \
  --username hr@example.com \
  --password '<客户端密码或授权码>' \
  --save-dir ./resumes \
  --from-keyword jobs \
  --filename-keyword resume
```

### 招聘网站导出

适用于 Boss 直聘、LinkedIn、Indeed、Lever、Greenhouse、Ashby 等系统。

推荐流程：

1. 导出或下载所有简历到 staging 文件夹。
2. 如果文件名包含候选人或岗位信息，尽量保留原文件名。
3. 如果有候选人元数据 CSV，把它放在 `resumes/` 同级，最终报告里说明来源。
4. 筛选前先跑 inventory，检查空白文件、扫描件和不支持格式。

### 飞书多维表格附件

适用于简历存在飞书 Base / 多维表格附件列的情况。

推荐流程：

1. 下载相关记录的附件文件。
2. 保留 record id 到本地文件名的映射表。
3. 跑筛选。
4. 如果用户要求回写推荐等级或备注，必须先确认，不能自动写回。

### 云盘文件夹

适用于 Google Drive、SharePoint、Box、Dropbox、本地同步文件夹。

推荐流程：

1. 确认文件可以本地访问或下载。
2. 复制到本次运行专属的 `resumes/`，不要直接改共享源文件夹。
3. 如果文件归属、上传时间、来源目录重要，保留 manifest。

## 来源规则

- 不要只因为来源渠道判断候选人是否匹配。
- 来源信息用于追溯、去重、岗位投递上下文和后续联系，不是评分本身。
- 不要修改、删除、重命名原始来源文件；先复制到运行文件夹。
- 邮箱和招聘网站导入时，优先用文件 hash、message id、候选人 profile id 去重。
- 公开 demo 里删除候选人联系方式、邮件来源和私有 ID。
