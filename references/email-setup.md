# 主流邮箱配置

邮箱下载器使用基础 IMAP 登录。一般需要开启 IMAP，并使用客户端专用密码/授权码，而不是网页登录密码。脚本不内置 OAuth；如果组织强制 OAuth，需要管理员提供可用的应用认证，或先从邮箱导出附件。

IMAP 是邮箱服务商提供给客户端读取邮件的标准协议。对批量简历邮件，它比浏览器逐封打开更适合：脚本可以先按日期和邮件标题过滤，再只抓取命中的完整邮件和附件。没有邮箱 connector 不影响这个脚本工作。

运行时不要把授权码写在 `--password` 参数里。省略密码参数后，脚本会在终端中隐藏输入；也可以临时设置 `IMAP_PASSWORD` 环境变量，但不要写入仓库文件。

## 附件邮件和平台链接邮件

脚本会输出两个本地清单：

- `_source_manifest.csv`：实际下载成功的附件。
- `_email_message_manifest.csv`：所有符合日期/标题条件的邮件，以及每封邮件的附件数量和网页链接。

如果命中邮件很多，但 `messages with matching attachments` 为 0，通常说明邮件只是招聘平台通知，简历在实习僧、Boss、ATS 等登录页面里。IMAP 可以批量取得这些通知链接，但无法绕过平台登录下载简历。

这种情况应优先寻找招聘平台的批量导出或 API。浏览器只适合验证一两个链接、完成登录或验证码，不适合逐封处理数百封邮件。

## 腾讯企业邮箱

脚本参数：

```bash
--provider tencent-exmail
```

如果公司网络或海外线路连接异常，可尝试：

```bash
--provider tencent-exmail-hw
```

服务器：

- IMAP：`imap.exmail.qq.com`
- 端口：`993`
- 加密：SSL/TLS

使用建议：

- 用完整邮箱地址作为用户名。
- 如果公司开启了安全登录，通常需要客户端专用密码。
- 如果连接失败，可能是管理员关闭了 IMAP 或限制了第三方客户端，需要找邮箱管理员开启。

## QQ 邮箱

脚本参数：

```bash
--provider qq
```

服务器：

- IMAP：`imap.qq.com`
- 端口：`993`
- 加密：SSL/TLS

使用建议：

- 在 QQ 邮箱网页版的设置里开启 IMAP/SMTP 服务。
- 通常需要授权码或客户端专用密码。

## Gmail

脚本参数：

```bash
--provider gmail
```

服务器：

- IMAP：`imap.gmail.com`
- 端口：`993`
- 加密：SSL/TLS

使用建议：

- 账号需要允许 IMAP。
- 这个 preset 只适用于账号仍允许 IMAP app password 的情况。强制 OAuth 的 Google Workspace 组织不能直接使用当前下载器。

## Outlook / Microsoft 365

脚本参数：

```bash
--provider outlook
```

服务器：

- IMAP：`outlook.office365.com`
- 端口：`993`
- 加密：SSL/TLS

使用建议：

- 部分 Microsoft 365 组织默认禁用 IMAP，需管理员开启。
- 这个 preset 只适用于组织允许 IMAP 客户端密码的情况。许多 Microsoft 365 组织强制现代认证；登录失败不一定是密码错。

## 网易 163 / 126

脚本参数：

```bash
--provider netease-163
--provider netease-126
--provider netease-enterprise
```

常见服务器：

- 个人 163：`imap.163.com`
- 个人 126：`imap.126.com`
- 网易企业邮箱：`imap.qiye.163.com`
- 端口：`993`
- 加密：SSL/TLS

使用建议：

- 先在网页端开启 IMAP/SMTP。
- 通常使用客户端授权码，不用网页登录密码。

## 自定义邮箱

如果不是上述邮箱：

```bash
python3 "$SKILL_DIR/scripts/email_attachment_downloader.py" \
  --server imap.example.com \
  --port 993 \
  --username hr@example.com \
  --save-dir ./resumes
```

## 排障

- 登录失败：检查是否用的是客户端专用密码/授权码。
- 连接失败：检查 IMAP 是否开启、端口 993 是否可用、公司网络是否拦截。
- 没下载到附件：放宽 `--subject-keyword` 和 `--filename-keyword`。
- 命中邮件但附件为 0：查看 `_email_message_manifest.csv`；这批邮件可能只有招聘平台链接。
- 重复下载：确认 `.email_download_state.json` 没被删除。
- Gmail / Microsoft 365 一直登录失败：确认组织是否强制 OAuth；当前脚本不绕过组织认证策略。
