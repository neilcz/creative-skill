# Creative Skill — AI 内容生产

## 概述

本 Skill 将 Creative Server 的 AI 视频生成能力接入 Claude Code。通过 `creative.py` CLI 工具，你可以帮助用户完成：

- 🎬 **AI 视频生成**：宫格视频、产品展示、数字人、RunningHub 特效
- 📤 **文件上传**：图片、视频、音频上传到 OSS 并获取可访问 URL
- 📊 **任务管理**：提交任务、查询进度、获取结果

## 前置条件（重要）

### API Key 配置

使用前必须配置 API Key。脚本会按以下顺序查找配置：

1. 环境变量 `CREATIVE_API_KEY`
2. `~/.claude/skills/creative/.env` 文件

**首次使用时，先检查是否已配置：**

```bash
cat ~/.claude/skills/creative/.env 2>/dev/null || echo "未配置"
```

**如果未配置，引导用户完成以下步骤：**

> 1. 访问 https://aivisn.com 登录你的账号
> 2. 进入「API Key 管理」页面，创建一个新的 API Key
> 3. 运行以下命令配置：
>    ```bash
>    mkdir -p ~/.claude/skills/creative
>    echo 'CREATIVE_SERVER=https://aivisn.com/api' >> ~/.claude/skills/creative/.env
>    echo 'CREATIVE_API_KEY=sk-你的key' >> ~/.claude/skills/creative/.env
>    ```

**安全提醒：**
- 绝对不要把用户的 API Key 输出到对话中
- 如果用户不小心在对话中暴露了 Key，提醒他们去服务端重新生成

### 服务器地址

默认使用 `https://aivisn.com/api`。

### 金币要求

任务开始前会有部分预扣，任务成功后结算，失败全额退款。如果返回「金币不足」错误，引导用户去 aivisn.com 充值。

---

## 工具参考

所有工具通过 `python <skill-path>/creative.py <command>` 调用。`<skill-path>` 为 Skill 安装路径，通常是 `~/.claude/skills/creative`。

### 1. 列出可用模板

```bash
python ~/.claude/skills/creative/creative.py list
python ~/.claude/skills/creative/creative.py list --raw  # JSON 格式，AI 解析用
```

**输出说明：**
- 基础工具：`get_upload_url`、`confirm_upload`
- 任务状态：通过 `resources/read` 读取 `task://{task_id}` 获取实时进度与结果
- 视频生成模板：每个模板有 ID、名称、参数列表

**AI 使用建议：**
- 用户首次使用或不确定有什么模板时，先执行 `list` 获取最新模板列表
- 用 `--raw` 获取 JSON 时，可以精确解析每个模板的参数 schema（type、required、enum、default 等），帮助用户构造正确的参数

### 2. 上传文件

```bash
python ~/.claude/skills/creative/creative.py upload <文件路径>
python ~/.claude/skills/creative/creative.py upload <文件路径> --type image/png
```

**流程：**
1. 脚本自动获取 OSS 预签名上传 URL
2. 通过 HTTP PUT 上传文件
3. 确认上传并返回可访问的 URL

**返回示例：**
```json
{
  "url": "https://aivisn.com/api/static/xxx/temp/image.png",
  "oss_key": "xxx/temp/image.png",
  "filename": "image.png",
  "content_type": "image/png",
  "size": 204800
}
```

**AI 使用建议：**
- 用户提供本地文件路径时，直接调用 upload
- 用户提供的是 URL 时，不需要上传，直接用 URL 作为模板参数
- 上传后的 `url` 可直接用于后续创建任务

### 3. 创建任务

```bash
python ~/.claude/skills/creative/creative.py create <模板ID> \
    --image "<图片URL>" \
    --duration 15 \
    --aspect_ratio "9:16"
```

**常用参数：**
| 参数 | 说明 |
|------|------|
| `--image` | 输入图片 URL（单张） |
| `--images` | 多张图片 URL，逗号分隔 |
| `--video` | 输入视频 URL |
| `--audio` | 输入音频 URL |
| `--text` | 输入文本/脚本 |
| `--description` | 描述文本 |
| `--duration` | 视频时长（秒） |
| `--aspect_ratio` | 宽高比（如 9:16, 16:9） |
| `--params` | JSON 字符串，传递额外参数 |
| `--wait` | 等待任务完成再返回 |

**返回示例：**
```json
{
  "template_id": "xxx",
  "name": "产品宫格视频",
  "task_id": "xxx-xxx-xxx",
  "status": "pending",
  "pre_deduct": 1800
}
```

**AI 使用建议：**
- 创建任务前，先用 `list --raw` 检查目标模板的参数 schema，确保传入的参数符合要求
- 如果用户同时提供本地文件和 URL，优先使用本地文件（先 upload 再 create）
- 返回的 `task_id` 要记住，用于后续查询状态
- 用 `--wait` 时脚本会阻塞到任务完成，适合短视频（<2分钟）；长视频建议不用 `--wait`，而是间隔轮询

### 4. 查询任务状态

```bash
python ~/.claude/skills/creative/creative.py status <task_id>
python ~/.claude/skills/creative/creative.py status <task_id> --wait   # 阻塞等待完成
python ~/.claude/skills/creative/creative.py status <task_id> --raw    # JSON 输出
```

**状态说明：**
- `pending` — 排队中
- `running` — 执行中
- `completed` — 完成（`result` 字段包含输出文件 URL）
- `failed` — 失败（`error` 字段包含错误信息）

**AI 使用建议：**
- 创建任务后主动告知用户 task_id
- 对于耗时任务（宫格视频通常 2-5 分钟），建议用 `--wait` 或每隔 10-15 秒轮询
- 任务完成后提取结果 URL 展示给用户
- 如果失败，分析 `error` 信息，给用户提供可行的重试建议

---

## 典型工作流

### 流程 A：用户提供图片，要生成产品展示视频

```
1. 确认需求：询问视频时长、宽高比、是否需要额外描述
2. 上传素材：creative.py upload product.jpg
3. 查看模板：creative.py list --raw  → 找到 grid_video 相关模板
4. 创建任务：creative.py create <模板ID> \
       --image "<step2返回的url>" \
       --duration 15 --aspect_ratio "9:16" \
       --description "展示产品特点"
5. 等待完成：creative.py status <task_id> --wait
6. 展示结果：提取输出视频 URL 给用户
```

### 流程 B：用户想了解有哪些视频生成能力

```
1. creative.py list  → 获取所有模板
2. 分类展示：宫格视频、数字人、特效等
3. 推荐模板并解释需要什么素材
```

### 流程 C：用户提供了多张产品图

```
1. 依次上传所有图片（可并行）
2. creative.py create <模板ID> --images "url1,url2,url3" --duration 30
3. creative.py status <task_id> --wait
```

### 流程 D：用户已经有生成好的视频 URL，只需要查询状态

```
1. creative.py status <用户提供的task_id>
2. 如果还在运行，提示用户稍后再查或用 --wait
```

---

## 决策指南

### 参数推理

- 用户说「做一个竖版视频」→ `--aspect_ratio "9:16"`
- 用户说「大概 30 秒」→ `--duration 30`
- 用户说「用这几张图」→ 先 upload 再用 `--images` 传 URL
- 用户提供了多张图片和一段描述 → 同时传递 `--images` 和 `--description`

### 什么时候不用 Skill

- 用户只是问「视频生成怎么做」→ 直接回答，不需要调用工具
- 用户没有素材也没有具体需求 → 先帮他们梳理需求
- 用户的问题是理论性的（如「用什么模型」）→ 直接回答

---

## 错误处理

| 错误 | 原因 | 处理 |
|------|------|------|
| 未配置 CREATIVE_API_KEY | 没有 API Key | 引导用户去 aivisn.com 创建 |
| 金币不足 | 余额不够 | 引导用户去充值 |
| 文件不存在 | 本地路径错误 | 确认文件路径是否正确 |
| 模板未找到 | 模板 ID 错误 | 执行 `list` 获取正确的 ID |
| 连接失败 | 网络/服务不可用 | 检查 CREATIVE_SERVER 是否正确 |
| 任务超时 | 任务执行超时 | 告知用户重试或联系服务端 |

对于任何 4xx 认证错误：提醒用户 API Key 可能已过期，需要重新生成。

---

## 环境变量参考

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CREATIVE_SERVER` | `https://aivisn.com/api` | Creative Server API 基础路径 |
| `CREATIVE_API_KEY` | （必填） | API Key，格式 `sk-xxx` |
