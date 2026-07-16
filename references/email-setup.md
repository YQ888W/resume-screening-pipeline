# 主流邮箱配置

邮箱下载使用 IMAP。一般需要开启 IMAP，并使用客户端专用密码/授权码，而不是网页登录密码。

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
- Google 官方建议优先用 OAuth；如果使用 app password，通常需要开启两步验证。

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
- Outlook.com / Microsoft 365 可能要求现代认证；如果 IMAP 密码登录失败，不一定是密码错，可能是组织策略不允许。

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
python3 scripts/email_attachment_downloader.py \
  --server imap.example.com \
  --port 993 \
  --username hr@example.com \
  --password '<客户端密码或授权码>' \
  --save-dir ./resumes
```

## 排障

- 登录失败：检查是否用的是客户端专用密码/授权码。
- 连接失败：检查 IMAP 是否开启、端口 993 是否可用、公司网络是否拦截。
- 没下载到附件：放宽 `--subject-keyword` 和 `--filename-keyword`。
- 重复下载：确认 `.email_download_state.json` 没被删除。
