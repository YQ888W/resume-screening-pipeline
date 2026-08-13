# 模型配置说明

## 固定供应商

本流水线固定使用智谱官方 API：

- 官方地址：`https://open.bigmodel.cn/api/paas/v4`
- 凭据：`ZHIPUAI_API_KEY`
- 禁止：OpenRouter、`z-ai/...`、`openai/...`、`OPENAI_API_KEY` 和代理 Base URL。

PDF/DOCX 先在本地使用 MarkItDown 转成 Markdown 并脱敏，再把文本发给智谱；不把原始文件交给 OpenRouter。

## 性能模式

- `auto`：默认。少于 20 份使用免费 `glm-4.7-flash`；20 份及以上自动使用付费 `glm-4.7-flashx`。
- `economy`：始终使用免费 `glm-4.7-flash`。
- `fast`：始终使用付费高速 `glm-4.7-flashx`。
- 视觉兜底：本地转换和 OCR 都失败时使用智谱官方 `glm-5v-turbo`。

本用户已经授权批量任务为效率使用付费高速模型，不需要每次重复确认。脚本仍保持逐候选人缓存和失败重试，避免重复消费。

## coding agent 自己的模型

可以，但要分两种情况：

1. 小批量或人工协作场景：可以让 coding agent 自己读几份简历、做 pilot、解释结果。
2. 大批量自动化场景：不建议完全依赖对话里的 coding agent 模型逐份手工处理。

原因：

- 脚本无法天然调用“当前聊天里的 agent 模型”，除非平台提供可调用 API。
- 对话式处理几百份简历更慢，也更容易受上下文长度影响。
- 不如 API 调用容易并发、缓存、失败重试和审计。
- 如果 agent 中途断线，恢复粒度不如 `work/records/C####.json` 清楚。

coding agent 适合确认 JD、查看 pilot 和解释反馈；批量读取与评分统一由脚本调用智谱官方 API，避免供应商和账单不透明。

## 运行前检查

首次使用先在可见终端运行：

```bash
python3 "$SKILL_DIR/scripts/resume_screening_pipeline.py" configure-key
```

看到隐藏输入提示后再粘贴新 Key。Key 保存到 macOS Keychain，后续自动读取。用 `key-status` 检查配置状态，用 `delete-key` 删除；这些命令都不会显示 Key。

先运行 `preflight`。它会检查当前抽取模型和评分模型分别需要哪个 key，并在开始批量调用前直接报错。

- 必须配置 `ZHIPUAI_API_KEY`。
- 若 `EXTRACT_MODEL`、`SCREEN_MODEL` 含 `/` 或 Base URL 不是智谱官方地址，preflight 必须阻断。
- `.env` 中的非敏感模型配置会在每次命令开始时重新读取，但其中的 API Key 会被忽略。

认证失败、模型不存在或请求格式错误不会再长时间重复重试；限流和临时网络错误仍会自动退避重试。

## 关于免费模型和成本

智谱的免费或限免政策会变化。对用户说明实际模型和模式，不承诺永久价格：

- 小样本默认使用免费/限免模型。
- 20 份及以上默认使用付费高速模型提高吞吐。
- 成本通常不是主要瓶颈，时间、限流、失败重试和文件质量更影响体验。
- 如果用户使用公司内部模型或中国 coding agent 自带模型，需确认是否支持 API 调用、并发、结构化输出和简历数据合规。

## 时间预期

实际耗时取决于模型速度、简历页数、扫描件比例、网络、并发数和限流。

粗略预期：

- 5 份 pilot：通常几分钟内。
- 50 份：普通并发下适合短时间内完成。
- 200-300 份：先跑 pilot，再使用 `--performance-mode auto`；默认付费高速模型和 6 并发，中断后可续跑。

不要承诺固定分钟数。更适合承诺：可中断续跑、可失败重试、已完成的不重复付费/不重复处理。
