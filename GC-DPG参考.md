我们希望参考 ai-rag2 项目中的 GC-DPG 思路，但不照搬医学领域实现。这里的 GC-DPG 可以理解为：

  > 先基于知识图谱规划学习内容，再约束大模型生成讲解 / 提问 / 反馈，最后检查输出是否符合知识图谱和学习目标。

  它适合改造成一个 多知识领域的交互式学习流程，例如数学、编程、历史、生物、语言学习等。

  整体流程可以设计为：

  学习者输入
   -> Phase 1: Learning Planning
   -> Phase 2: Constrained Teaching / Interaction Generation
   -> Phase 3: Consistency & Pedagogy Checking
   -> 输出讲解 / 问题 / 反馈 + 知识依据 + 学习状态更新

  Phase 1：Learning Planning

  第一阶段不要直接让大模型回答，而是先做学习规划。

  需要识别：

  - 学习者当前问题或行为
  - 涉及的知识领域，例如数学、编程、历史
  - 核心知识点，例如“二次函数”“Python 列表”“工业革命”
  - 学习意图，例如：
      - explain：请求解释
      - example：请求例子
      - practice：请求练习
      - quiz：出题检测
      - hint：请求提示
      - feedback：对答案进行批改
      - next_step：推荐下一步学习内容
  - 前置知识、相关知识、易错点、练习题等图谱证据

  可以把原项目里的 AnswerPlan 泛化成 LearningPlan：

  {
    "subject": {
      "id": "math.quadratic_function",
      "name": "二次函数",
      "type": "Concept",
      "match_score": 0.92
    },
    "learner_intent": "explain",
    "learning_level": "beginner",
    "slots": [
      {
        "type": "definition",
        "coverage": "full",
        "entities": [
          {
            "id": "math.quadratic_function.definition",
            "name": "二次函数定义"
          }
        ]
      },
      {
        "type": "prerequisite",
        "coverage": "partial",
        "entities": [
          {
            "id": "math.linear_function",
            "name": "一次函数"
          }
        ]
      },
      {
        "type": "misconception",
        "coverage": "full",
        "entities": [
          {
            "id": "math.quadratic_function.vertex_confusion",
            "name": "顶点与零点混淆"
          }
        ]
      }
    ],
    "learning_intent_graph": {
      "nodes": [
        "二次函数",
        "定义",
        "一次函数",
        "顶点",
        "图像"
      ],
      "edges": [
        {
          "from": "一次函数",
          "to": "二次函数",
          "type": "prerequisite_of"
        }
      ]
    }
  }

  Phase 2：Constrained Teaching / Interaction Generation

  第二阶段再让大模型生成内容，但必须受 LearningPlan 约束。

  大模型可以生成：

  - 概念讲解
  - 分步提示
  - 示例
  - 练习题
  - 选择题
  - 对学习者答案的反馈
  - 下一步推荐

  但要遵守规则：

  - 只能使用 LearningPlan 中允许的知识点和关系
  - 不要跳到未掌握的高级知识点
  - 不要编造不存在的概念关系
  - 如果图谱中没有相关内容，要明确说明无法确认
  - 根据学习者水平调整难度
  - 交互式学习中不要一次性给完答案，必要时优先给提示

  示例系统约束：

  你是一个交互式学习助手。
  你必须根据 LearningPlan 生成内容。
  只能使用 LearningPlan 中出现的知识点、前置知识、例子、练习和易错点。
  如果学习者正在做题，优先给提示，不要直接泄露完整答案。
  如果某个知识点没有图谱证据，请说明当前知识库暂无可靠内容。
  输出要符合学习者当前水平。

  Phase 3：Consistency & Pedagogy Checking

  第三阶段检查生成内容是否安全、准确、适合教学。

  可以检查：

  - 输出中的知识点是否都存在于知识图谱
  - 是否引入了未授权的新概念
  - 是否违反学习路径，例如初学者回答里突然引入高阶内容
  - 是否直接泄露了练习题答案
  - 是否和当前学习目标一致
  - 是否覆盖了必要的前置知识
  - 是否存在幻觉内容

  可以输出指标：

  {
    "knowledge_support_ratio": 0.9,
    "unsupported_concept_rate": 0.1,
    "learning_goal_alignment": 0.85,
    "difficulty_match": "appropriate",
    "hint_policy_violated": false,
    "is_safe_to_show": true
  }

  交互式学习项目需要额外加入的状态

  相比普通问答系统，交互式学习还应该维护学习者状态：

  {
    "learner_id": "user_001",
    "current_topic": "二次函数",
    "mastered_concepts": ["一次函数", "坐标系"],
    "weak_concepts": ["顶点", "对称轴"],
    "recent_answers": [],
    "current_mode": "practice",
    "difficulty": "beginner"
  }

  每一轮交互后，系统应该更新：

  - 学习者是否答对
  - 哪些知识点掌握了
  - 哪些知识点仍然薄弱
  - 下一步应该讲解、提示、复习还是出题

  最终建议

  不要把原项目里的 disease / symptom / gene / drug 这些医学字段照搬过去。应该改成更通用的学习字段：

  disease        -> subject / concept / topic
  intent         -> learner_intent
  slots          -> learning_slots
  AnswerPlan     -> LearningPlan
  ConsistencyReport -> LearningConsistencyReport
  GC-DPG Pipeline -> KG-Constrained Interactive Learning Pipeline

  核心思想保持不变：

  先知识图谱规划
  再约束生成教学内容
  最后检查知识一致性和教学适配性

  这样就可以把 GC-DPG 从医学问答迁移成一个适用于多领域的交互式学习框架。
