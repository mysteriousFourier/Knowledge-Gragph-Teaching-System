#!/usr/bin/env python3
"""
知识图谱可视化运行脚本

功能：
- 启动知识图谱可视化API服务器
- 打开浏览器显示可视化页面
- 提供简单的命令行界面
"""

import os
import sys
import subprocess
import webbrowser
import time
import socket
from pathlib import Path


class GraphVizRunner:
    """知识图谱可视化运行器"""

    def __init__(self):
        # 路径修复：正确计算各文件位置
        self.script_dir = Path(__file__).parent.resolve()
        self.api_script = self.script_dir / "graph_viz_api.py"
        self.viz_html = self.script_dir / "graph_viz.html"
        self.port = 8080

        print("知识图谱可视化运行器初始化")
        print(f"Script directory: {self.script_dir}")
        print(f"API script: {self.api_script}")
        print(f"HTML file: {self.viz_html}")

    def check_port_available(self, port):
        """检查端口是否可用"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(('localhost', port))
            sock.close()
            return result != 0
        except:
            return False

    def check_files(self):
        """检查必要文件是否存在"""
        if not self.api_script.exists():
            print(f"Error: API script not found: {self.api_script}")
            return False

        if not self.viz_html.exists():
            print(f"Warning: HTML file not found: {self.viz_html}")
            print("API will use embedded visualization")

        return True

    def start_api_server(self):
        """启动API服务器"""
        # 检查端口
        if not self.check_port_available(self.port):
            print(f"Port {self.port} is in use, trying other ports...")
            for p in range(8001, 8010):
                if self.check_port_available(p):
                    self.port = p
                    print(f"Using port {self.port}")
                    break

        print(f"Starting API server on port {self.port}")

        # 启动API服务器
        cmd = [sys.executable, str(self.api_script)]
        self.api_process = subprocess.Popen(cmd, cwd=str(self.script_dir))

        # 等待服务器启动
        print("Waiting for server to start...")
        time.sleep(3)

        # 验证服务器是否运行
        for i in range(10):
            if not self.check_port_available(self.port):
                print("Server is running")
                return self.api_process
            time.sleep(1)

        print("Server failed to start")
        return None

    def open_visualization(self):
        """打开可视化页面"""
        viz_url = f"http://localhost:{self.port}/"
        print(f"Opening browser: {viz_url}")
        webbrowser.open(viz_url)

    def run(self):
        """运行主流程"""
        api_process = None
        try:
            # 检查文件
            if not self.check_files():
                return False

            # 启动API服务器
            api_process = self.start_api_server()
            if not api_process:
                return False

            # 打开可视化页面
            self.open_visualization()

            print("\n=== 知识图谱可视化服务已启动 ===")
            print("服务地址: http://localhost:" + str(self.port))
            print()
            print("操作选项:")
            print("1. 重新打开浏览器")
            print("2. 查看服务状态")
            print("0. 返回主菜单")
            print()

            while True:
                # 检查进程是否还在运行
                if api_process.poll() is not None:
                    print("API server stopped unexpectedly")
                    break

                try:
                    choice = input("请输入选项编号 (1/2/0): ").strip()
                    if choice == "0":
                        print("正在停止服务...")
                        break
                    elif choice == "1":
                        self.open_visualization()
                        print("浏览器已重新打开")
                    elif choice == "2":
                        if self.check_port_available(self.port):
                            print("服务未正常运行")
                        else:
                            print("服务运行正常")
                    else:
                        print("无效选项")
                except KeyboardInterrupt:
                    print("\n收到中断信号，正在停止服务...")
                    break
                print()

        except Exception as e:
            print(f"运行时错误: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # 终止API服务器
            if api_process:
                try:
                    api_process.terminate()
                    try:
                        api_process.wait(timeout=5)
                    except:
                        api_process.kill()
                except:
                    pass
            print("服务已停止")
            return True


if __name__ == "__main__":
    runner = GraphVizRunner()
    runner.run()