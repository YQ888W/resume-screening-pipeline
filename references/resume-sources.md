# 简历来源和能力边界

流水线最终统一从本地 `resumes/` 读取简历，但这不代表默认假设简历已经在本地。用户没有说明来源时，先问“本地已有，还是需要下载”；确认后再由 agent 把上游文件复制或下载到 `resumes/`，不修改原始来源。

来源未确认前，不要扫描 `Documents` 或工作区之外寻找 PDF，也不要因为发现若干简历样式的文件就自行选择本地分支。

## 来源能力表

| 来源 | 当前能力 | 没有访问能力时怎么办 |
|---|---|---|
| 本地文件夹 | 内置支持，复制后直接盘点 | 无需额外操作 |
| 邮箱附件 | 内置 IMAP 下载器，支持授权码/客户端密码 | OAuth-only 邮箱由管理员开通，或手动导出附件 |
| 邮箱中的招聘平台链接 | IMAP 可批量提取邮件和链接，但不能直接取得平台登录后的简历 | 优先用招聘平台批量导出/API；浏览器只做登录或少量 pilot |
| 飞书多维表格 | agent 有飞书 connector 时可下载附件并保留 record id | 从飞书批量下载后放入本地文件夹 |
| ATS / 招聘网站 | agent 有对应 API/connector 时可导出 | 在系统中批量导出简历和候选人 CSV |
| 云盘 | agent 能访问共享盘或本地同步目录时可复制 | 用户下载或同步到本地 |

不要把“可以接入”描述成“内置支持”。执行前先检查当前 coding agent 是否拥有对应 connector 和权限。

## 本地文件

直接读取 PDF、DOCX、TXT、JPG、JPEG、PNG。旧版 `.doc` 会在 inventory 中标记，但需要先转换成 PDF 或 DOCX。

将源文件复制到本次运行目录。保留原文件名；候选人 ID 由 `work/candidate_index.json` 稳定维护，不依赖文件排序。

## 邮箱附件

先确认邮箱服务商、日期范围、发件人/主题/附件关键词。授权码默认隐藏输入：

```bash
python3 "$SKILL_DIR/scripts/email_attachment_downloader.py" \
  --provider tencent-exmail \
  --username you@company.com \
  --save-dir ./resumes \
  --days-back 30 \
  --subject-keyword 简历
```

自定义 IMAP：

```bash
python3 "$SKILL_DIR/scripts/email_attachment_downloader.py" \
  --server imap.example.com \
  --port 993 \
  --username hr@example.com \
  --save-dir ./resumes \
  --filename-keyword resume
```

下载器先轻量读取邮件头筛选日期和主题，只对命中邮件获取完整内容。它生成 `_source_manifest.csv` 记录实际附件，并生成 `_email_message_manifest.csv` 区分附件型邮件和只有网页链接的平台通知。多岗位时，脚本会把邮件标题作为投递岗位提示，但不会把来源渠道当作匹配证据。

不要先寻找邮箱浏览器 connector。对已支持服务商，内置 IMAP 脚本就是默认批量路径。用户提供网页邮箱链接时，也不能据此直接选择浏览器。

## ATS、招聘网站、飞书和云盘

1. 检查当前 agent 是否有对应 connector 和读取权限。
2. 有权限时下载附件，并保留候选人记录 ID 到本地文件名的映射。
3. 没权限时让用户从系统批量导出，不要求用户逐份下载。
4. 元数据 CSV 放在 `resumes/` 同级或保留为来源 manifest。
5. 只有用户明确要求并确认后，才把筛选结果写回外部系统。

## 去重和追溯

- 邮件使用附件 hash 和 message id 去重。
- 本地相同内容的重复文件按 hash 合并为一个候选人输入。
- 来源信息用于追溯、岗位路由和后续联系，不参与匹配评分。
- 不删除、重命名或覆盖原始来源文件。
- 公开示例删除候选人联系方式、邮件来源和私有 ID。
