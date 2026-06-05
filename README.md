# Creative Skill — AI 内容生产

将 Creative Server 的 AI 视频生成能力接入 Claude Code。

## 功能

- 🎬 **AI 视频生成** — 宫格视频、产品展示、数字人播报、RunningHub 特效
- 📤 **文件上传** — 图片/视频/音频上传到 OSS
- 📊 **任务管理** — 提交任务、实时进度、结果获取

## 快速开始

### 1. 安装

**在线安装（推荐）：**
```bash
curl -sSL https://aivisn.com/skill/install.sh | bash
```

**本地安装：**
```bash
git clone https://github.com/neilcz/creative-skill.git
cd creative-skill
./install.sh
```

**手动安装：**
```bash
mkdir -p ~/.claude/skills/creative
cp creative.py skill.md ~/.claude/skills/creative/
echo 'CREATIVE_SERVER=https://aivisn.com' > ~/.claude/skills/creative/.env
echo 'CREATIVE_API_KEY=sk-你的key' >> ~/.claude/skills/creative/.env
chmod +x ~/.claude/skills/creative/creative.py
```

### 2. 获取 API Key

1. 访问 [aivisn.com](https://aivisn.com) 登录账号
2. 进入「API Key 管理」页面
3. 创建新的 API Key，格式为 `sk-xxxx`
4. 配置到 `~/.claude/skills/creative/.env`

### 3. 测试

```bash
python ~/.claude/skills/creative/creative.py list
```

### 4. 在 Claude Code 中使用

安装后直接跟 Claude 说：

> "帮我生成一个产品展示视频，用这张图 product.jpg，竖版 15 秒"

AI 会自动调用 Skill 完成上传、创建任务、轮询状态、返回结果。

## 命令参考

```bash
# 列出可用模板
creative.py list

# 上传文件
creative.py upload photo.jpg

# 创建视频任务
creative.py create <模板ID> --image "https://..." --duration 15 --aspect_ratio "9:16"

# 查询任务状态
creative.py status <task_id>

# 等待任务完成
creative.py status <task_id> --wait
```

## 文件结构

```
~/.claude/skills/creative/
├── skill.md       # AI 上下文（Claude Code 自动加载）
├── creative.py    # CLI 工具（纯 Python stdlib，零依赖）
└── .env           # 配置文件（API Key）
```

## 常见问题

**Q: 需要什么依赖？**
A: Python 3.8+，纯标准库，零额外依赖。

**Q: 支持哪些 AI 客户端？**
A: 目前仅 Claude Code。其他客户端（Cursor、Windsurf 等）推荐直接配置 MCP 协议接入。

**Q: 金币怎么算？**
A: 宫格视频 1800 金币/次，RunningHub 200-2000，其他 10-500。在 aivisn.com 充值。

**Q: 能用自建的 Creative Server 吗？**
A: 可以，设置 `CREATIVE_SERVER=http://your-server:8000`。

## 下载

- [GitHub Releases](https://github.com/neilcz/creative-skill/releases)
- [直接下载 ZIP](https://aivisn.com/skill/creative-skill.zip)

## License

MIT
