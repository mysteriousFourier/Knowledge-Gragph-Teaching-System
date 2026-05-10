"""
MCP服务器配置示例文件
将此文件内容添加到 ~/.claude/settings.json 的 mcpServers 部分
"""

import json
import sys
from pathlib import Path


MCP_SERVER_DIR = Path(__file__).resolve().parent
SERVER_PATH = MCP_SERVER_DIR / "server.py"

mcp_config = {
    "knowledge-graph": {
        "command": sys.executable,
        "args": [
            str(SERVER_PATH)
        ],
        "env": {
            "PYTHONPATH": str(MCP_SERVER_DIR)
        }
    }
}

print("请将以下配置添加到 ~/.claude/settings.json:")
print(json.dumps({"mcpServers": mcp_config}, indent=2, ensure_ascii=False))
