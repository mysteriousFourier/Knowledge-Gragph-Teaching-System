#!/usr/bin/env python3
"""
知识图谱管理系统运行脚本

功能：
- 自动配置环境
- 处理依赖
- 启动知识图谱管理系统
- 提供交互式界面
"""

import os
import sys
import subprocess
import time
from pathlib import Path

class GraphManagerRunScript:
    def __init__(self):
        self.project_dir = Path(__file__).parent
        self.root_dir = self.project_dir.parent
        self.env_file = self.root_dir.parent / ".env"
        self.venv_dir = self.root_dir / "venv"
        # 使用当前Python解释器
        self.python_exe = sys.executable
        
        print("知识图谱管理系统运行脚本初始化")
        print(f"项目目录: {self.project_dir}")
        print(f"根目录: {self.root_dir}")
    
    def check_environment(self):
        """检查环境配置"""
        print("\n检查环境配置...")
        
        # 检查.env文件
        if not self.env_file.exists():
            print("警告: .env文件不存在，将使用默认配置")
        
        # 检查Python版本
        print(f"Python版本: {sys.version}")
        print(f"使用的Python解释器: {self.python_exe}")
        
        # 跳过虚拟环境检查，直接使用miniconda
        print("使用D盘miniconda，跳过虚拟环境创建")
    
    def create_venv(self):
        """创建虚拟环境"""
        print("创建虚拟环境...")
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(self.venv_dir)],
                check=True,
                capture_output=True,
                text=True
            )
            print("虚拟环境创建成功")
        except subprocess.CalledProcessError as e:
            print(f"创建虚拟环境失败: {e.stderr}")
            sys.exit(1)
    
    def install_dependencies(self):
        """安装依赖"""
        print("\n安装依赖...")
        
        # 直接使用miniconda的Python解释器
        python_exe = self.python_exe
        
        # 基础依赖
        dependencies = [
            "numpy",
            "pandas",
            "scikit-learn"
        ]
        
        try:
            for dep in dependencies:
                subprocess.run(
                    [python_exe, "-m", "pip", "install", dep],
                    check=True,
                    capture_output=True,
                    text=True
                )
            print("依赖安装成功")
        except subprocess.CalledProcessError as e:
            print(f"安装依赖失败: {e.stderr}")
            sys.exit(1)
    
    def run_graph_manager(self):
        """运行知识图谱管理系统"""
        print("\n启动知识图谱管理系统...")
        
        # 导入知识图谱UI
        sys.path.insert(0, str(self.root_dir))
        
        try:
            from knowledge_graph.graph_ui import KnowledgeGraphUI
            
            # 初始化知识图谱UI
            data_dir = str(self.root_dir / ".." / "structured")
            storage_path = str(self.root_dir / "knowledge_graph")
            ui = KnowledgeGraphUI(data_dir, storage_path)
            
            print("知识图谱管理系统初始化成功")
            
            # 运行交互式界面
            ui.run()
            
        except Exception as e:
            print(f"启动失败: {str(e)}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    def run(self):
        """运行主流程"""
        try:
            self.check_environment()
            self.install_dependencies()
            self.run_graph_manager()
        except Exception as e:
            print(f"运行失败: {str(e)}")
            sys.exit(1)

if __name__ == "__main__":
    script = GraphManagerRunScript()
    script.run()
