#!/usr/bin/env bash
# ============================================================
# Creative Skill 一键安装脚本
# ============================================================
# 兼容两种安装方式:
#   1. 从 aivisn.com 下载（API Key 已自动注入，开箱即用）
#   2. 从 GitHub clone（需手动配置 API Key）
#
# 用法:
#   curl -sSL https://aivisn.com/api/skill/install.sh | bash
#   或
#   ./install.sh
#
# 安装到 ~/.claude/skills/creative/
# ============================================================

set -e

SKILL_DIR="$HOME/.claude/skills/creative"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ---- API Key（服务端下载时自动替换此占位符）----
# 如果从 GitHub clone，此值为占位符，脚本会引导手动配置
INJECTED_API_KEY="___CREATIVE_API_KEY___"

# ---- 颜色 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   🎬 Creative Skill 安装程序       ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""

# ---- 检查 Python ----
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo -e "${RED}❌ 未找到 Python，请先安装 Python 3.8+${NC}"
    exit 1
fi
PYTHON=$(command -v python3 || command -v python)
echo -e "${GREEN}✅ Python: $($PYTHON --version)${NC}"

# ---- 创建目录 ----
mkdir -p "$SKILL_DIR"
echo -e "${GREEN}✅ 目录: $SKILL_DIR${NC}"

# ---- 复制/下载文件 ----
if [ -f "$SCRIPT_DIR/creative.py" ] && [ "$SCRIPT_DIR" != "$SKILL_DIR" ]; then
    cp "$SCRIPT_DIR/creative.py" "$SKILL_DIR/creative.py"
elif [ ! -f "$SKILL_DIR/creative.py" ]; then
    echo -e "${YELLOW}📥 下载 creative.py...${NC}"
    curl -sSL -o "$SKILL_DIR/creative.py" "https://aivisn.com/api/skill/creative.py" || {
        echo -e "${RED}❌ 下载失败，请检查网络或手动从 GitHub 获取${NC}"
        exit 1
    }
fi

if [ -f "$SCRIPT_DIR/skill.md" ] && [ "$SCRIPT_DIR" != "$SKILL_DIR" ]; then
    cp "$SCRIPT_DIR/skill.md" "$SKILL_DIR/skill.md"
elif [ ! -f "$SKILL_DIR/skill.md" ]; then
    echo -e "${YELLOW}📥 下载 skill.md...${NC}"
    curl -sSL -o "$SKILL_DIR/skill.md" "https://aivisn.com/api/skill/skill.md" || {
        echo -e "${YELLOW}⚠ skill.md 下载失败，可手动从 GitHub 获取${NC}"
    }
fi

chmod +x "$SKILL_DIR/creative.py"
echo -e "${GREEN}✅ 文件已安装${NC}"

# ---- 配置 API Key ----
ENV_FILE="$SKILL_DIR/.env"

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  配置 API Key${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# 判断是否已注入真实 Key
if [ -n "$INJECTED_API_KEY" ] && [[ "$INJECTED_API_KEY" != ___* ]]; then
    # 服务端已注入真实 Key，直接写入
    cat > "$ENV_FILE" << EOF
# Creative Skill 配置
CREATIVE_SERVER=https://aivisn.com/api
CREATIVE_API_KEY=$INJECTED_API_KEY
EOF
    chmod 600 "$ENV_FILE"
    echo -e "${GREEN}✅ API Key 已自动配置${NC}"
    echo ""

elif [ -f "$ENV_FILE" ] && grep -q "CREATIVE_API_KEY=sk-" "$ENV_FILE" 2>/dev/null; then
    # 已有有效配置
    echo -e "${GREEN}✅ 检测到已有 API Key 配置${NC}"
    echo ""

else
    # 从 GitHub 安装，需要手动配置
    echo "未检测到 API Key。获取方式:"
    echo ""
    echo "  方式一（推荐）：访问 https://aivisn.com/mcp-guide"
    echo "    在「SKILL 接入」标签中一键下载含 Key 的安装脚本"
    echo ""
    echo "  方式二：手动创建"
    echo "    1. 访问 https://aivisn.com 登录账号"
    echo "    2. 进入「API Key 管理」创建新的 Key（命名为 skill）"
    echo "    3. 手动写入配置："
    echo "       echo 'CREATIVE_API_KEY=sk-你的key' >> $ENV_FILE"
    echo ""

    read -r -p "已有 Key？直接输入 (回车跳过): " API_KEY </dev/tty

    if [ -n "$API_KEY" ]; then
        cat > "$ENV_FILE" << EOF
# Creative Skill 配置
CREATIVE_SERVER=https://aivisn.com
CREATIVE_API_KEY=$API_KEY
EOF
        chmod 600 "$ENV_FILE"
        echo -e "${GREEN}✅ 配置已保存${NC}"
    else
        echo ""
        echo -e "${YELLOW}⚠ 跳过配置。稍后手动编辑 $ENV_FILE 添加 API Key${NC}"
        cat > "$ENV_FILE" << EOF
# Creative Skill 配置
CREATIVE_SERVER=https://aivisn.com
CREATIVE_API_KEY=sk-你的key
EOF
    fi
    echo ""
fi

# ---- 验证 ----
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  验证安装${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE" 2>/dev/null || true
fi
if [ -n "$CREATIVE_API_KEY" ] && [[ "$CREATIVE_API_KEY" == sk-* ]]; then
    echo "正在验证 API Key..."
    if CREATIVE_API_KEY="$CREATIVE_API_KEY" $PYTHON "$SKILL_DIR/creative.py" list --raw &>/dev/null; then
        echo -e "${GREEN}✅ API Key 验证成功！${NC}"
    else
        echo -e "${YELLOW}⚠ API Key 验证失败，请稍后手动测试。${NC}"
    fi
else
    echo -e "${YELLOW}⚠ 未配置有效 API Key，跳过验证。${NC}"
fi

# ---- 完成 ----
echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   🎉 安装完成！                    ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""
echo "文件位置:"
echo "  CLI 工具: $SKILL_DIR/creative.py"
echo "  AI 上下文: $SKILL_DIR/skill.md"
echo "  配置文件: $SKILL_DIR/.env"
echo ""
echo "快速测试:"
echo "  python $SKILL_DIR/creative.py list"
echo ""
echo "现在在 Claude Code 中直接说你的需求即可！"
echo "例如：「帮我生成一个产品展示视频，用这张图」"
echo ""
