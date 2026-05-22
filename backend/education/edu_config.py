"""
教育模式配置文件
"""
import os


class EduConfig:
    # 后台维护系统数据库路径
    BACKEND_DB_PATH = os.path.join(
        os.path.dirname(__file__), "..", "mcp-server", "data", "knowledge_graph.db"
    )

    # 授课文案生成配置
    LECTURE_STYLE = "引导式教学"
    LECTURE_LENGTH = "中等"  # 短、中等、长
    LECTURE_LANGUAGE = "中文"

    # 问答生成配置
    ANSWER_MAX_LENGTH = 500
    ANSWER_INCLUDE_EXAMPLES = True

    # 练习题生成配置
    EXERCISE_TYPES = ["填空题", "选择题", "简答题"]
    DEFAULT_EXERCISE_COUNT = {
        "填空题": 3,
        "选择题": 3,
        "简答题": 2
    }

    # 知识路径追踪配置
    MAX_PATH_DEPTH = 5
    MIN_PATH_NODES = 2

    # 日志配置
    LOG_LEVEL = "INFO"


config = EduConfig()
