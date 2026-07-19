#!/usr/bin/env python3
"""
Creative Skill CLI — AI 内容生产工具
=====================================
通过 HTTP 调用 Creative Server 的 MCP 端点，提供：
  - 模板发现（列出可用的视频生成模板）
  - 文件上传（获取预签名 URL → 上传到 OSS）
  - 任务创建（提交 AI 视频生成任务）
  - 状态查询（轮询任务进度和结果）

认证: Bearer API Key（在服务端 https://aivisn.com 生成）
协议: MCP JSON-RPC 2.0 over Streamable HTTP

依赖: Python 3.8+，纯标准库，零额外依赖

用法:
  python creative.py list                      # 列出可用模板
  python creative.py list --raw                # 输出原始 JSON
  python creative.py upload <file>             # 上传文件
  python creative.py create <ID> --image "<url>" --duration 15
  python creative.py status <task_id>          # 查询任务状态
  python creative.py status <task_id> --wait   # 等待任务完成

配置:
  环境变量 CREATIVE_SERVER 和 CREATIVE_API_KEY
  或写入 ~/.claude/skills/creative/.env 文件
"""

import os
import sys
import json
import time
import uuid
import base64
import hashlib
import urllib.request
import urllib.error
import argparse
import mimetypes
from pathlib import Path
from typing import Optional


# ============================================================
# 配置加载
# ============================================================

def _load_env():
    """从多个位置加载配置，优先级：环境变量 > .env 文件 > 默认值"""
    env_file = Path.home() / ".claude" / "skills" / "creative" / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

    # 也尝试当前目录下的 .env
    local_env = Path(__file__).resolve().parent / ".env"
    if local_env.exists():
        with open(local_env) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

_load_env()

DEFAULT_SERVER = "https://aivisn.com/api"


# ============================================================
# MCP JSON-RPC 客户端
# ============================================================

class MCPClient:
    """MCP Streamable HTTP 客户端，封装 JSON-RPC 2.0 通信"""

    def __init__(self, server_url: str, api_key: str):
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self._session_id: Optional[str] = None
        self._initialized = False
        self._request_id = 0

    # ----- 底层 JSON-RPC 调用 -----

    def _rpc(self, method: str, params: dict = None) -> dict:
        """发送 JSON-RPC 请求"""
        self._request_id += 1
        body = {"jsonrpc": "2.0", "method": method, "id": self._request_id}
        if params is not None:
            body["params"] = params

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{self.server_url}/mcp", data=data, headers=headers, method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self._session_id = sid
                raw = resp.read().decode("utf-8")
                if not raw.strip():
                    # some MCP responses are empty for notifications
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            return {"jsonrpc": "2.0", "id": self._request_id,
                    "error": {"code": e.code, "message": f"HTTP {e.code}: {body[:500]}"}}
        except urllib.error.URLError as e:
            return {"jsonrpc": "2.0", "id": self._request_id,
                    "error": {"code": -1, "message": f"连接失败: {e.reason}"}}

    # ----- MCP 生命周期 -----

    def initialize(self) -> dict:
        """MCP 初始化握手"""
        if self._initialized:
            return {"ok": True}

        result = self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "creative-skill", "version": "1.0.0"},
        })

        if "error" in result:
            return result

        # 发送 initialized 通知
        self._rpc("notifications/initialized", {})
        self._initialized = True
        return {"ok": True, "serverInfo": result.get("result", {}).get("serverInfo", {})}

    def read_resource(self, uri: str) -> dict:
        """读取 MCP 资源，返回结构化内容"""
        r = self._rpc("resources/read", {"uri": uri})
        if "error" in r:
            init_r = self.initialize()
            if "error" in init_r:
                raise ClientError(f"MCP 初始化失败: {init_r['error'].get('message', init_r['error'])}")
            r = self._rpc("resources/read", {"uri": uri})
            if "error" in r:
                raise ClientError(f"读取资源失败: {r['error'].get('message', r['error'])}")

        result = r.get("result", {})
        contents = result.get("contents", [])
        if contents and isinstance(contents, list):
            first = contents[0]
            text = first.get("text", "")
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return {"text": text}
        return result

    # ----- 高层 API -----

    def list_tools(self) -> list[dict]:
        """列出所有可用工具，返回工具列表"""
        r = self._rpc("tools/list")
        if "error" in r:
            # 尝试初始化后重试
            init_r = self.initialize()
            if "error" in init_r:
                raise ClientError(f"MCP 初始化失败: {init_r['error'].get('message', init_r['error'])}")
            r = self._rpc("tools/list")
            if "error" in r:
                raise ClientError(f"tools/list 失败: {r['error'].get('message', r['error'])}")

        return r.get("result", {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> dict:
        """调用 MCP 工具，返回 result 内容"""
        r = self._rpc("tools/call", {"name": name, "arguments": arguments})
        if "error" in r:
            # 尝试初始化后重试一次
            init_r = self.initialize()
            if "error" in init_r:
                raise ClientError(f"MCP 初始化失败: {init_r['error'].get('message', init_r['error'])}")
            r = self._rpc("tools/call", {"name": name, "arguments": arguments})
            if "error" in r:
                raise ClientError(f"工具 '{name}' 调用失败: {r['error'].get('message', r['error'])}")

        result = r.get("result", {})
        # 优先使用 structuredContent（MCP SDK 自动解析的结构化结果）
        if "structuredContent" in result and result["structuredContent"] is not None:
            return result["structuredContent"]
        # 回退：从 content 文本列表中提取 JSON
        content = result.get("content", [])
        if content and isinstance(content, list):
            for item in content:
                if item.get("type") == "text":
                    text = item.get("text", "")
                    try:
                        return json.loads(text)
                    except (json.JSONDecodeError, TypeError):
                        return {"text": text}
        return result


class ClientError(Exception):
    """可恢复的客户端错误"""
    pass


# ============================================================
# 命令实现
# ============================================================

def _get_client() -> MCPClient:
    """获取配置好的 MCP 客户端"""
    server = os.getenv("CREATIVE_SERVER", DEFAULT_SERVER)
    api_key = os.getenv("CREATIVE_API_KEY", "")
    if not api_key:
        raise ClientError(
            "未配置 CREATIVE_API_KEY。\n\n"
            "获取方式:\n"
            "  1. 访问 https://aivisn.com 登录账号\n"
            "  2. 进入 API Key 管理页面，创建新的 API Key\n"
            "  3. 在 ~/.claude/skills/creative/.env 中设置:\n"
            "     CREATIVE_API_KEY=sk-xxxxxxxx"
        )
    return MCPClient(server, api_key)


def _filter_template_tools(tools: list[dict]) -> list[dict]:
    """从工具列表中筛选出模板类工具（template_ 前缀）"""
    result = []
    for t in tools:
        name = t.get("name", "")
        if name.startswith("template_"):
            result.append({
                "id": name[9:],  # 去掉 "template_" 前缀
                "name": t.get("description", name),
                "schema": t.get("inputSchema", {}),
            })
    return result


def cmd_list(raw: bool = False):
    """列出可用的视频生成模板"""
    client = _get_client()
    tools = _get_client().list_tools()  # 触发 init
    templates = _filter_template_tools(tools)

    if raw:
        print(json.dumps(templates, ensure_ascii=False, indent=2))
        return

    static_tools = [t for t in tools if not t.get("name", "").startswith("template_")]

    print(f"🎬 Creative Server 可用能力\n")
    print(f"━━━ 基础工具 ━━━")
    for t in static_tools:
        print(f"  • {t['name']}: {t.get('description', '')}")

    print(f"\n━━━ 视频生成模板 ({len(templates)} 个) ━━━")
    for t in templates:
        schema = t.get("schema", {})
        props = schema.get("properties", {})
        required = schema.get("required", [])
        param_strs = []
        for k, v in props.items():
            desc = v.get("description", k)
            req_mark = " *" if k in required else ""
            param_strs.append(f"{k}{req_mark}: {desc}")
        params_desc = ", ".join(param_strs[:5])
        if len(param_strs) > 5:
            params_desc += f" ... (+{len(param_strs) - 5})"

        print(f"\n  📹 {t['name']}")
        print(f"     ID: {t['id']}")
        print(f"     参数: {params_desc}")

    print(f"\n💡 使用 python creative.py create <ID> --help 查看具体模板的参数")


def cmd_upload(filepath: str, content_type: str = None):
    """上传文件到 OSS"""
    client = _get_client()

    path = Path(filepath)
    if not path.exists():
        raise ClientError(f"文件不存在: {filepath}")
    if not path.is_file():
        raise ClientError(f"不是文件: {filepath}")

    filename = path.name
    if not content_type:
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    file_size = path.stat().st_size
    file_size_mb = file_size / (1024 * 1024)

    # 1. 获取上传预签名 URL
    print(f"📤 准备上传: {filename} ({file_size_mb:.1f} MB)")
    result = client.call_tool("get_upload_url", {
        "filename": filename,
        "content_type": content_type,
    })

    upload_url = result.get("upload_url")
    oss_key = result.get("oss_key")
    if not upload_url or not oss_key:
        raise ClientError(f"获取上传 URL 失败: {result}")

    # 2. 上传文件到 OSS
    print(f"   上传中...")
    with open(filepath, "rb") as f:
        data = f.read()

    req = urllib.request.Request(upload_url, data=data, method="PUT")
    req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            if resp.status not in (200, 204):
                raise ClientError(f"上传失败: HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        raise ClientError(f"上传失败: HTTP {e.code} {e.read().decode('utf-8', errors='replace')[:200]}")

    # 3. 确认上传
    print(f"   确认上传...")
    confirm = client.call_tool("confirm_upload", {"oss_key": oss_key})
    access_url = confirm.get("url", "")

    print(f"\n✅ 上传成功")
    print(f"   URL: {access_url}")
    print(f"   OSS Key: {oss_key}")

    # 输出 JSON 供 AI 后续使用
    print(f"\n📋 JSON:")
    print(json.dumps({
        "url": access_url,
        "oss_key": oss_key,
        "filename": filename,
        "content_type": content_type,
        "size": file_size,
    }, ensure_ascii=False, indent=2))


def cmd_create(template_id: str, params: dict, wait: bool = False):
    """创建 AI 视频生成任务"""
    client = _get_client()

    # 去掉可能的 template_ 前缀
    if template_id.startswith("template_"):
        template_id = template_id[9:]

    tool_name = f"template_{template_id}"

    print(f"🎬 提交任务...")
    print(f"   模板: {template_id}")
    for k, v in params.items():
        v_str = str(v)
        if len(v_str) > 80:
            v_str = v_str[:77] + "..."
        print(f"   {k}: {v_str}")

    result = client.call_tool(tool_name, params)

    if "error" in result:
        raise ClientError(f"创建任务失败: {result['error']}")

    task_id = result.get("task_id", "")
    print(f"\n✅ 任务已提交")
    print(f"   Task ID: {task_id}")
    print(f"   状态: {result.get('status', 'pending')}")
    print(f"   预扣金币: {result.get('pre_deduct', 'N/A')}")

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if wait and task_id:
        cmd_status(task_id, wait=True)


def cmd_status(task_id: str, wait: bool = False, raw: bool = False):
    """查询任务状态"""
    client = _get_client()

    if wait:
        print(f"⏳ 等待任务完成...")

    last_percent = -1
    while True:
        result = client.read_resource(f"task://{task_id}")

        if raw:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if not wait:
                return

        status = result.get("status", "unknown")
        percent = result.get("percent", 0)
        error = result.get("error")
        output = result.get("result")

        if not raw:
            if percent != last_percent:
                bar = "█" * (percent // 10) + "░" * (10 - percent // 10)
                print(f"\r  [{bar}] {percent}% — {status}", end="", flush=True)
                last_percent = percent

            if status in ("completed", "success", "failed", "error"):
                print()  # newline

        if status in ("completed", "success"):
            if not raw:
                print(f"\n✅ 任务完成")
                if output:
                    # 提取可访问的 URL
                    urls = _extract_urls(output)
                    if urls:
                        print(f"\n📹 结果文件:")
                        for u in urls:
                            print(f"   {u}")
                    else:
                        print(json.dumps(output, ensure_ascii=False, indent=2))
            break

        if status in ("failed", "error"):
            if not raw:
                err_msg = error.get("msg", str(error)) if isinstance(error, dict) else str(error)
                print(f"\n❌ 任务失败: {err_msg}")
            break

        if not wait:
            if not raw:
                if status not in ("completed", "success", "failed", "error"):
                    print(f"\n   当前状态: {status} ({percent}%)")
                    print(f"   使用 --wait 等待任务完成")
            break

        time.sleep(5)


def _extract_urls(obj, depth=0) -> list[str]:
    """从嵌套结构中递归提取 URL 字符串"""
    if depth > 10:
        return []
    urls = []
    if isinstance(obj, str):
        if obj.startswith("https://") or obj.startswith("http://"):
            urls.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            urls.extend(_extract_urls(v, depth + 1))
    elif isinstance(obj, list):
        for item in obj:
            urls.extend(_extract_urls(item, depth + 1))
    return urls


def cmd_templates():
    """便捷别名: 列出模板"""
    cmd_list()


# ============================================================
# CLI 入口
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="creative",
        description="Creative Skill CLI — AI 内容生产工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  creative list                    列出可用模板
  creative upload image.png        上传图片
  creative create <ID> --image "https://..." --duration 15
  creative status <task_id>        查询任务状态
  creative status <task_id> --wait 等待任务完成

配置:
  设置环境变量 CREATIVE_API_KEY，或写入 ~/.claude/skills/creative/.env:
    CREATIVE_SERVER=https://aivisn.com/api
    CREATIVE_API_KEY=sk-xxxxxxxx
        """,
    )
    sub = p.add_subparsers(dest="command", help="可用命令")

    # list
    sp_list = sub.add_parser("list", help="列出可用的视频生成模板")
    sp_list.add_argument("--raw", action="store_true", help="输出原始 JSON")

    # upload
    sp_upload = sub.add_parser("upload", help="上传文件到 OSS")
    sp_upload.add_argument("file", help="要上传的文件路径")
    sp_upload.add_argument("--type", dest="content_type", default=None,
                           help="MIME 类型（自动检测）")

    # create
    sp_create = sub.add_parser("create", help="创建 AI 视频生成任务")
    sp_create.add_argument("template", help="模板 ID")
    sp_create.add_argument("--image", default=None, help="输入图片 URL")
    sp_create.add_argument("--images", default=None, help="多张图片 URL，逗号分隔")
    sp_create.add_argument("--video", default=None, help="输入视频 URL")
    sp_create.add_argument("--audio", default=None, help="输入音频 URL")
    sp_create.add_argument("--text", default=None, help="输入文本/脚本")
    sp_create.add_argument("--description", default=None, help="描述文本")
    sp_create.add_argument("--duration", type=int, default=None, help="视频时长（秒）")
    sp_create.add_argument("--aspect_ratio", default=None, help="宽高比（如 9:16）")
    sp_create.add_argument("--params", default=None,
                           help="额外参数，JSON 字符串")
    sp_create.add_argument("--wait", action="store_true", help="等待任务完成")

    # status
    sp_status = sub.add_parser("status", help="查询任务状态")
    sp_status.add_argument("task_id", help="任务 ID")
    sp_status.add_argument("--wait", action="store_true", help="等待任务完成")
    sp_status.add_argument("--raw", action="store_true", help="输出原始 JSON")

    # templates (alias)
    sub.add_parser("templates", help="列出模板 (list 的别名)")

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command in ("list", "templates"):
            cmd_list(raw=getattr(args, "raw", False))

        elif args.command == "upload":
            cmd_upload(args.file, content_type=args.content_type)

        elif args.command == "create":
            # 构建参数
            params = {}
            if args.image:
                params["image"] = args.image
            if args.images:
                params["images"] = [u.strip() for u in args.images.split(",") if u.strip()]
            if args.video:
                params["video"] = args.video
            if args.audio:
                params["audio"] = args.audio
            if args.text:
                params["text"] = args.text
            if args.description:
                params["description"] = args.description
            if args.duration is not None:
                params["duration"] = args.duration
            if args.aspect_ratio:
                params["aspect_ratio"] = args.aspect_ratio
            if args.params:
                extra = json.loads(args.params)
                if isinstance(extra, dict):
                    params.update(extra)

            cmd_create(args.template, params, wait=args.wait)

        elif args.command == "status":
            cmd_status(args.task_id, wait=args.wait, raw=args.raw)

    except ClientError as e:
        print(f"\n❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n⏹ 已取消")
        sys.exit(130)


if __name__ == "__main__":
    main()
