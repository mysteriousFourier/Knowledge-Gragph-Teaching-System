#!/usr/bin/env python3
"""
运行系统主脚本
"""

import os
import sys
import subprocess
import json

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.json')

def load_config():
    """加载配置"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载配置失败: {e}")
    return {}

def save_config(config):
    """保存配置"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存配置失败: {e}")

config = load_config()

def main():
    """主函数"""
    while True:
        print("=" * 50)
        print("=== 向量索引系统 ===")
        print("请选择要运行的模块:")
        print()
        
        projects = [
            "知识图谱管理",
            "知识图谱可视化",
            "语义消歧",
            "向量检索",
            "知识图谱与向量集成",
            "大模型RAG",
            "Microsoft GraphRAG",
            "Memory系统选择",
            "测试集成功能"
        ]
        
        for i, project in enumerate(projects, 1):
            print(f"{i}. {project}")
        print("0. 退出系统")
        print()
        
        try:
            choice = int(input("请输入选项编号: "))
            if choice == 0:
                print("感谢使用，再见!")
                break
            if choice < 1 or choice > len(projects):
                print("无效的选项编号")
                continue
        except ValueError:
            print("请输入有效的数字")
            continue
        
        print()
        
        if choice == 1:
            print("启动知识图谱管理...")
            try:
                print(f"Python解释器: {sys.executable}")
                script_path = os.path.join(os.path.dirname(__file__), "knowledge_graph", "run_graph_manager.py")
                print(f"脚本路径: {script_path}")
                print(f"脚本是否存在: {os.path.exists(script_path)}")
                
                print("直接导入并运行知识图谱管理...")
                from KGTS.knowledge_graph.graph_ui import KnowledgeGraphUI
                
                data_dir = os.path.join(os.path.dirname(__file__), "..", "structured")
                storage_path = os.path.join(os.path.dirname(__file__), "knowledge_graph")
                
                print(f"数据目录: {data_dir}")
                print(f"存储路径: {storage_path}")
                
                ui = KnowledgeGraphUI(data_dir, storage_path)
                ui.run()
                
            except Exception as e:
                print(f"运行失败: {e}")
                import traceback
                traceback.print_exc()
        elif choice == 2:
            print("启动知识图谱可视化...")
            try:
                python_exe = sys.executable
                api_path = os.path.join(os.path.dirname(__file__), "backend_admin.py")
                if not os.path.exists(api_path):
                    api_path = os.path.join(os.path.dirname(__file__), "simple_api_server.py")
                
                print(f"Python解释器: {python_exe}")
                print(f"API脚本路径: {api_path}")
                print(f"API脚本是否存在: {os.path.exists(api_path)}")
                
                if not os.path.exists(api_path):
                    print("API脚本不存在")
                    continue
                
                import socket
                def check_port(port):
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(2)
                        result = sock.connect_ex(('127.0.0.1', port))
                        sock.close()
                        print(f"端口 {port} 检查结果: {result} (0表示被占用，其他表示可用)")
                        return result != 0
                    except Exception as e:
                        print(f"检查端口 {port} 时出错: {e}")
                        return False
                
                port = 8080
                print(f"开始检查端口 {port}")
                while not check_port(port):
                    print(f"端口 {port} 已被占用，尝试下一个端口")
                    port += 1
                    if port > 9000:
                        print("没有可用端口")
                        continue
                print(f"找到可用端口: {port}")
                
                print(f"直接运行API服务器，使用端口 {port}...")
                import subprocess
                process = subprocess.Popen(
                    [python_exe, api_path, "--port", str(port)]
                )
                
                import time
                print("等待服务器启动...")
                for i in range(10):
                    time.sleep(1)
                    print(f"等待第 {i+1} 秒...")
                    if not check_port(port):
                        print("服务器已启动")
                        break
                else:
                    print("服务器启动超时")
                
                if check_port(port):
                    print("服务器启动失败")
                    process.terminate()
                else:
                    print("服务器启动成功")
                    viz_url = f"http://127.0.0.1:{port}"
                    print(f"请在浏览器中访问 {viz_url}")
                    print("按Enter键停止服务...")
                    import webbrowser
                    webbrowser.open(viz_url)
                    try:
                        input()
                    except KeyboardInterrupt:
                        pass
                    print("停止服务器...")
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except:
                        process.kill()
                    print("服务已停止")
            except Exception as e:
                print(f"运行失败: {e}")
                import traceback
                traceback.print_exc()
        elif choice == 3:
            print("启动语义消歧...")
            try:
                python_exe = sys.executable
                script_path = os.path.join(os.path.dirname(__file__), "test_semantic_disambiguation.py")
                subprocess.run([python_exe, script_path])
            except Exception as e:
                print(f"运行失败: {e}")
        elif choice == 4:
            print("启动向量检索...")
            try:
                from KGTS.vector_retrieval import VectorRetriever
                retriever = VectorRetriever()
                
                print("向量检索系统启动成功")
                print("可用操作:")
                print("1. 添加文本到向量索引")
                print("2. 搜索相似文本")
                print("3. 查看统计信息")
                print("4. 清空向量索引")
                print("0. 返回主菜单")
                
                while True:
                    sub_choice = input("请输入操作编号: ")
                    if sub_choice == "0":
                        break
                    elif sub_choice == "1":
                        text = input("请输入要添加的文本: ")
                        text_id = retriever.add_text(text)
                        print(f"文本已添加，ID: {text_id}")
                    elif sub_choice == "2":
                        query = input("请输入搜索查询: ")
                        results = retriever.search(query, k=3)
                        print("搜索结果:")
                        for i, (text, similarity, metadata) in enumerate(results, 1):
                            print(f"{i}. 相似度: {similarity:.4f}, 文本: {text}")
                    elif sub_choice == "3":
                        stats = retriever.get_stats()
                        print("统计信息:")
                        print(json.dumps(stats, indent=2, ensure_ascii=False))
                    elif sub_choice == "4":
                        retriever.clear()
                        print("向量索引已清空")
                    else:
                        print("无效的操作编号")
            except Exception as e:
                print(f"运行失败: {e}")
        elif choice == 5:
            print("启动知识图谱与向量集成...")
            try:
                from KGTS.graph_vector_integration import GraphVectorIntegration
                integration = GraphVectorIntegration()
                
                print("知识图谱与向量集成系统启动成功")
                print("可用操作:")
                print("1. 索引知识图谱")
                print("2. 搜索知识图谱")
                print("3. 混合搜索")
                print("4. 查看统计信息")
                print("0. 返回主菜单")
                
                while True:
                    sub_choice = input("请输入操作编号: ")
                    if sub_choice == "0":
                        break
                    elif sub_choice == "1":
                        integration.index_knowledge_graph()
                    elif sub_choice == "2":
                        query = input("请输入搜索查询: ")
                        results = integration.search_knowledge_graph(query, k=3)
                        print("搜索结果:")
                        for i, result in enumerate(results, 1):
                            print(f"{i}. 相似度: {result['similarity']:.4f}, 标签: {result['label']}, 类型: {result['type']}")
                    elif sub_choice == "3":
                        query = input("请输入搜索查询: ")
                        results = integration.hybrid_search(query, k=3)
                        print("混合搜索结果:")
                        for i, result in enumerate(results, 1):
                            print(f"{i}. 混合分数: {result['hybrid_score']:.4f}, 标签: {result['label']}")
                    elif sub_choice == "4":
                        stats = integration.get_graph_stats()
                        print("统计信息:")
                        print(json.dumps(stats, indent=2, ensure_ascii=False))
                    else:
                        print("无效的操作编号")
            except Exception as e:
                print(f"运行失败: {e}")
        elif choice == 6:
            print("启动大模型RAG...")
            try:
                from KGTS.llm_integration import LLMIntegration
                llm_integration = LLMIntegration(config=config)
                
                print("大模型RAG系统启动成功")
                print("可用操作:")
                print("1. 查看系统状态")
                print("2. 生成回答")
                print("3. 批量处理查询")
                print("0. 返回主菜单")
                
                while True:
                    sub_choice = input("请输入操作编号: ")
                    if sub_choice == "0":
                        break
                    elif sub_choice == "1":
                        status = llm_integration.get_system_status()
                        print("系统状态:")
                        print(json.dumps(status, indent=2, ensure_ascii=False))
                    elif sub_choice == "2":
                        query = input("请输入问题: ")
                        result = llm_integration.generate_with_rag(query, k=3)
                        print(f"回答: {result['response']}")
                        print(f"检索结果数量: {len(result['retrieved_results'])}")
                        print(f"用时: {result['time_taken']:.2f}秒")
                    elif sub_choice == "3":
                        print("请输入查询（每行一个，空行结束）:")
                        queries = []
                        while True:
                            line = input()
                            if not line:
                                break
                            queries.append(line)
                        if queries:
                            results = llm_integration.batch_process(queries, k=3)
                            for i, result in enumerate(results, 1):
                                print(f"\n查询 {i}: {result['query']}")
                                print(f"回答: {result['response']}")
                    else:
                        print("无效的操作编号")
            except Exception as e:
                print(f"运行失败: {e}")
        elif choice == 7:
            print("启动 Microsoft GraphRAG...")
            try:
                import importlib.util
                
                module_path = os.path.join(os.path.dirname(__file__), 'memory_systems', 'microsoft-graphrag', 'access_entry.py')
                spec = importlib.util.spec_from_file_location("graphrag_access", module_path)
                graphrag_module = importlib.util.module_from_spec(spec)
                sys.modules["graphrag_access"] = graphrag_module
                spec.loader.exec_module(graphrag_module)
                
                GraphRAGAccess = graphrag_module.GraphRAGAccess
                graphrag_access = GraphRAGAccess()
                
                print("Microsoft GraphRAG 系统启动成功")
                print("可用操作:")
                print("1. 查看系统状态")
                print("2. 处理文档")
                print("3. 执行查询")
                print("4. 查看统计信息")
                print("0. 返回主菜单")
                
                while True:
                    sub_choice = input("请输入操作编号: ")
                    if sub_choice == "0":
                        break
                    elif sub_choice == "1":
                        status = graphrag_access.get_status()
                        print("系统状态:")
                        print(json.dumps(status, indent=2, ensure_ascii=False))
                    elif sub_choice == "2":
                        document_path = input("请输入文档路径: ")
                        result = graphrag_access.process_document(document_path)
                        print("处理结果:")
                        print(json.dumps(result, indent=2, ensure_ascii=False))
                    elif sub_choice == "3":
                        query = input("请输入查询: ")
                        result = graphrag_access.query(query)
                        print("查询结果:")
                        print(json.dumps(result, indent=2, ensure_ascii=False))
                    elif sub_choice == "4":
                        stats = graphrag_access.get_stats()
                        print("统计信息:")
                        print(json.dumps(stats, indent=2, ensure_ascii=False))
                    else:
                        print("无效的操作编号")
            except Exception as e:
                print(f"运行失败: {e}")
        elif choice == 8:
            print("Memory系统选择")
            print("请选择要使用的Memory系统:")
            print("1. OpenClaw Engram")
            print("2. Mem0")
            print("0. 返回主菜单")
            
            while True:
                sub_choice = input("请输入选择: ")
                if sub_choice == "0":
                    break
                elif sub_choice == "1":
                    print("启动 OpenClaw Engram...")
                    try:
                        config['memory_system'] = 'openclaw'
                        save_config(config)
                        print("已设置默认记忆系统为: OpenClaw Engram")
                        subprocess.run([sys.executable, "memory_systems/openclaw-engram/run_openclaw.py"])
                    except Exception as e:
                        print(f"运行失败: {e}")
                    break
                elif sub_choice == "2":
                    print("启动 Mem0...")
                    try:
                        config['memory_system'] = 'mem0'
                        save_config(config)
                        print("已设置默认记忆系统为: Mem0")
                        
                        from KGTS.memory_systems.mem0.access_entry import Mem0Access
                        mem0_access = Mem0Access()
                        
                        print("Mem0 系统启动成功")
                        print("可用操作:")
                        print("1. 查看系统状态")
                        print("2. 添加内存")
                        print("3. 搜索内存")
                        print("4. 查看统计信息")
                        print("0. 返回主菜单")
                        
                        while True:
                            mem_sub_choice = input("请输入操作编号: ")
                            if mem_sub_choice == "0":
                                break
                            elif mem_sub_choice == "1":
                                status = mem0_access.get_status()
                                print("系统状态:")
                                print(json.dumps(status, indent=2, ensure_ascii=False))
                            elif mem_sub_choice == "2":
                                content = input("请输入内存内容: ")
                                memory_data = {"content": content}
                                result = mem0_access.add_memory(memory_data)
                                print("添加结果:")
                                print(json.dumps(result, indent=2, ensure_ascii=False))
                            elif mem_sub_choice == "3":
                                query = input("请输入搜索查询: ")
                                result = mem0_access.search_memory(query, k=3)
                                print("搜索结果:")
                                print(json.dumps(result, indent=2, ensure_ascii=False))
                            elif mem_sub_choice == "4":
                                stats = mem0_access.get_stats()
                                print("统计信息:")
                                print(json.dumps(stats, indent=2, ensure_ascii=False))
                            else:
                                print("无效的操作编号")
                    except Exception as e:
                        print(f"运行失败: {e}")
                    break
                else:
                    print("无效的选择")
        elif choice == 9:
            print("测试集成功能...")
            try:
                from KGTS.llm_integration import LLMIntegration
                llm_integration = LLMIntegration(config=config)
                
                print("\n系统状态:")
                status = llm_integration.get_system_status()
                print(json.dumps(status, indent=2, ensure_ascii=False))
                
                print("\n测试RAG生成:")
                test_query = "什么是人工智能？"
                print(f"查询: {test_query}")
                result = llm_integration.generate_with_rag(test_query, k=3)
                print(f"回答: {result['response']}")
                print(f"检索结果数量: {len(result['retrieved_results'])}")
                print(f"用时: {result['time_taken']:.2f}秒")
                
                print("\n测试第二个查询:")
                test_query2 = "人工智能有哪些应用？"
                print(f"查询: {test_query2}")
                result2 = llm_integration.generate_with_rag(test_query2, k=3)
                print(f"回答: {result2['response']}")
                print(f"检索结果数量: {len(result2['retrieved_results'])}")
                print(f"用时: {result2['time_taken']:.2f}秒")
                
                if llm_integration.memory_client:
                    print("\n测试记忆系统搜索:")
                    if llm_integration.memory_system == 'mem0':
                        search_result = llm_integration.memory_client.search_memory("人工智能", k=3)
                        print("记忆系统搜索结果:")
                        print(json.dumps(search_result, indent=2, ensure_ascii=False))
                    else:
                        print("当前记忆系统不支持搜索测试")
                
                print("\n集成测试完成!")
            except Exception as e:
                print(f"测试失败: {e}")
                import traceback
                traceback.print_exc()
        
        print()
        input("按 Enter 键返回主菜单...")
        print()

def run_api_server_directly():
    """直接运行API服务器"""
    print("直接运行知识图谱可视化API服务器...")
    try:
        from KGTS.knowledge_graph.graph_viz_api import run_server
        run_server(port=8080)
    except Exception as e:
        print(f"运行API服务器失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--api":
        run_api_server_directly()
    else:
        main()
