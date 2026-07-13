"""
基于 LangChain 和 ChromaDB 的 LLM 检索解释 Agent

提供强校验的比赛结果解释功能，使用 RAG（检索增强生成）技术，
结合战术资讯和历史数据生成符合 MCP 标准的解释报告。
"""

import sys
from pathlib import Path
# 添加项目根目录到 Python 路径
if __name__ == "__main__":
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))

from typing import Optional, List
from pydantic import BaseModel, Field

# LangChain 相关导入
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.tools import tool

# 智谱AI原生SDK
try:
    from zhipuai import ZhipuAI
    HAS_ZHIPUAI = True
except ImportError:
    HAS_ZHIPUAI = False

# ChromaDB 相关（可选）
try:
    from langchain_chroma import Chroma
    HAS_LANGCHAIN_CHROMA = True
except ImportError:
    HAS_LANGCHAIN_CHROMA = False
    # 使用社区版本的 Chroma
    try:
        from langchain_community.vectorstores import Chroma
        HAS_LANGCHAIN_CHROMA = True
    except ImportError:
        HAS_LANGCHAIN_CHROMA = False

# 本地嵌入模型（无需 API key）
try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False


class MatchExplanation(BaseModel):
    """
    比赛解释的结构化输出 Schema
    
    严格遵循 Pydantic 验证，确保输出格式的一致性。
    """
    
    tactical_analysis: str = Field(
        description="战术相克分析：解释两队在战术风格上的克制关系，如高位逼抢 vs 传控体系的对抗"
    )
    
    key_player_impact: str = Field(
        description="关键球员影响：分析核心球员的表现对比赛结果的决定性作用"
    )
    
    historical_context: str = Field(
        description="历史交锋摘要：回顾两队历史交手记录和心理优势"
    )
    
    confidence_score: float = Field(
        description="置信度评分（0-1），表示解释的可信程度",
        ge=0.0,
        le=1.0
    )
    
    prediction_summary: str = Field(
        description="预测结果摘要：简要复述传入的比分和胜负状态（不得修改）"
    )


class TacticalKnowledgeBase:
    """
    战术知识库（模拟 ChromaDB 向量数据库）
    
    在实际应用中，这里会连接真实的 ChromaDB 实例，
    存储球队战术风格、球员特点、历史战绩等向量化的知识。
    """
    
    def __init__(self):
        """初始化战术知识库"""
        # 模拟的战术知识数据
        self.tactical_knowledge = {
            "Brazil": {
                "style": "技术流进攻足球，擅长边路突破和快速反击",
                "strengths": ["个人技术出色", "进攻创造力强", "定位球威胁大"],
                "weaknesses": ["防守定位球不稳定", "有时过于依赖个人能力"],
                "key_players": ["内马尔", "维尼修斯", "阿利松"],
                "historical_note": "5次世界杯冠军，拥有最辉煌的世界杯历史"
            },
            "Germany": {
                "style": "严谨的战术体系，强调团队配合和高位压迫",
                "strengths": ["战术纪律性强", "体能充沛", "整体防守稳固"],
                "weaknesses": ["进攻端有时缺乏灵感", "面对技术流球队可能被动"],
                "key_players": ["穆勒", "基米希", "诺伊尔"],
                "historical_note": "4次世界杯冠军，以稳定性和效率著称"
            },
            "Argentina": {
                "style": "传控为主，注重中场控制和短传渗透",
                "strengths": ["中场控制力强", "梅西的组织能力", "定位球精准"],
                "weaknesses": ["防守速度较慢", "替补深度不足"],
                "key_players": ["梅西", "迪马利亚", "马丁内斯"],
                "historical_note": "3次世界杯冠军，2022年最新夺冠"
            },
            "France": {
                "style": "身体素质与技术并重，快速转换进攻",
                "strengths": ["球员个体能力强", "反击速度快", "阵容深度厚"],
                "weaknesses": ["有时战术执行力不够", "内部团结问题"],
                "key_players": ["姆巴佩", "格列兹曼", "楚阿梅尼"],
                "historical_note": "2次世界杯冠军，卫冕冠军身份"
            },
            "Spain": {
                "style": "极致传控（Tiki-Taka），强调控球率",
                "strengths": ["控球能力顶级", "传球精度高", "战术素养好"],
                "weaknesses": ["进攻终结能力不足", "面对密集防守办法不多"],
                "key_players": ["罗德里", "莫拉塔", "佩德里"],
                "historical_note": "2010年世界杯冠军，传控足球的代表"
            },
            "England": {
                "style": "传统英式足球与现代战术结合，强调身体对抗",
                "strengths": ["身体优势明显", "定位球威胁大", "年轻球员多"],
                "weaknesses": ["大赛心理素质待检验", "战术变化较少"],
                "key_players": ["凯恩", "贝林厄姆", "福登"],
                "historical_note": "1966年世界杯冠军，近年表现稳步提升"
            },
            "Portugal": {
                "style": "技术流与实用主义结合，注重边路进攻",
                "strengths": ["边路突破能力强", "C罗的经验", "战术灵活"],
                "weaknesses": ["中场控制力一般", "防守老化"],
                "key_players": ["C罗", "B费", "迪亚斯"],
                "historical_note": "2016年欧洲杯冠军，世界杯最佳成绩为第四"
            },
            "Netherlands": {
                "style": "全攻全守理念，强调进攻组织和空间利用",
                "strengths": ["进攻组织流畅", "边后卫助攻强", "战术创新"],
                "weaknesses": ["防守稳定性不足", "关键时刻心理脆弱"],
                "key_players": ["范戴克", "德容", "加克波"],
                "historical_note": "3次世界杯亚军，无冕之王"
            }
        }
        
        # 历史交锋记录（简化版）
        self.historical_records = {
            ("Brazil", "Germany"): [
                "2014年世界杯半决赛：德国 7-1 巴西（米内罗惨案）",
                "历史上巴西对德国稍占优势，但2014年的失利是巴西足球的痛点",
                "两队共交手21次，巴西12胜5平4负"
            ],
            ("Argentina", "France"): [
                "2022年世界杯决赛：阿根廷 4-2 法国（点球大战）",
                "梅西终于圆梦的经典战役",
                "两队历史交锋12次，阿根廷6胜3平3负"
            ],
            ("Germany", "Spain"): [
                "2010年世界杯半决赛：西班牙 1-0 德国",
                "西班牙传控足球的巅峰时期",
                "两队历史交锋26次，西班牙14胜7平5负"
            ]
        }
    
    def get_tactical_info(self, team_name: str) -> dict:
        """
        获取球队的战术信息
        
        Args:
            team_name: 球队名称
            
        Returns:
            包含战术风格、优缺点、关键球员等信息的字典
        """
        return self.tactical_knowledge.get(team_name, {
            "style": "未知战术风格",
            "strengths": [],
            "weaknesses": [],
            "key_players": [],
            "historical_note": "暂无历史记录"
        })
    
    def get_historical_matchup(self, team_a: str, team_b: str) -> List[str]:
        """
        获取两队的历史交锋记录
        
        Args:
            team_a: A队名称
            team_b: B队名称
            
        Returns:
            历史交锋记录列表
        """
        # 尝试两个方向的查找
        record = self.historical_records.get((team_a, team_b))
        if not record:
            record = self.historical_records.get((team_b, team_a))
        
        return record or ["暂无历史交锋记录"]
    
    def search_tactical_knowledge(self, query: str) -> List[dict]:
        """
        搜索战术知识（模拟向量检索）
        
        在实际应用中，这里会使用 ChromaDB 进行真正的向量相似度搜索。
        
        Args:
            query: 搜索查询
            
        Returns:
            相关的战术知识列表
        """
        results = []
        query_lower = query.lower()
        
        for team_name, info in self.tactical_knowledge.items():
            if team_name.lower() in query_lower:
                results.append({
                    "team": team_name,
                    "content": f"{team_name}的战术风格：{info['style']}",
                    "relevance": 0.9
                })
        
        return results[:5]  # 返回最相关的5条结果


# ==================== LangChain Tools（MCP 风格）====================

@tool
def get_team_tactics(team_name: str) -> str:
    """
    获取指定球队的战术风格和特点
    
    Args:
        team_name: 球队名称（如 'Brazil', 'Germany'）
        
    Returns:
        球队的战术信息文本
    """
    kb = TacticalKnowledgeBase()
    info = kb.get_tactical_info(team_name)
    
    result = f"【{team_name} 战术档案】\n"
    result += f"战术风格：{info['style']}\n"
    result += f"优势：{', '.join(info['strengths'])}\n"
    result += f"劣势：{', '.join(info['weaknesses'])}\n"
    result += f"关键球员：{', '.join(info['key_players'])}\n"
    result += f"历史备注：{info['historical_note']}"
    
    return result


@tool
def get_historical_record(team_a: str, team_b: str) -> str:
    """
    查询两队的历史交锋记录
    
    Args:
        team_a: A队名称
        team_b: B队名称
        
    Returns:
        历史交锋记录文本
    """
    kb = TacticalKnowledgeBase()
    records = kb.get_historical_matchup(team_a, team_b)
    
    result = f"【{team_a} vs {team_b} 历史交锋】\n"
    for i, record in enumerate(records, 1):
        result += f"{i}. {record}\n"
    
    return result


@tool
def search_tactical_database(query: str) -> str:
    """
    在战术数据库中搜索相关信息
    
    Args:
        query: 搜索关键词或问题
        
    Returns:
        搜索结果文本
    """
    kb = TacticalKnowledgeBase()
    results = kb.search_tactical_knowledge(query)
    
    if not results:
        return f"未找到与 '{query}' 相关的战术信息"
    
    result = f"【战术数据库搜索结果】（查询：'{query}'）\n"
    for i, item in enumerate(results, 1):
        result += f"{i}. [{item['team']}] {item['content']} (相关度: {item['relevance']:.2f})\n"
    
    return result


# ==================== MatchExplainerAgent ====================

class MatchExplainerAgent:
    """
    比赛解释 Agent
    
    使用 LangChain 和 RAG 技术，基于底层概率引擎的确定性预测结果，
    结合战术资讯和历史数据生成结构化的解释报告。
    
    核心特性：
    - 强校验输出：使用 Pydantic Schema 确保输出格式
    - 工具化接口：封装向量检索和数据库查询为标准化工具
    - MCP 风格：模拟 Model Context Protocol 的工具调用理念
    - 约束明确：LLM 只能解释结果，不能修改比分
    """
    
    def __init__(
        self,
        model_name: str = "glm-4-flash",
        api_key: Optional[str] = None,
        use_local_model: bool = False
    ):
        """
        初始化解释 Agent
        
        Args:
            model_name: 模型名称（如 'glm-4-flash'）
            api_key: 智谱AI API 密钥
            use_local_model: 是否使用本地模型（需要配置 Ollama 或其他本地服务）
        """
        self.kb = TacticalKnowledgeBase()
        
        # 保存模型名称
        self.model_name = model_name
        
        # 初始化 LLM
        if use_local_model:
            # 使用本地模型（如 Ollama）
            from langchain_community.llms import Ollama
            self.llm = Ollama(model="llama2", temperature=0.1)
            self.zhipu_client = None
        else:
            # 使用智谱AI原生SDK
            if not HAS_ZHIPUAI:
                raise ImportError("请安装 zhipuai: pip install zhipuai")
            
            actual_api_key = api_key or "sk-placeholder-key"
            self.zhipu_client = ZhipuAI(api_key=actual_api_key)
            print(f"[LLM] Using ZhipuAI native SDK: model={model_name}")
        
        # 定义工具列表
        self.tools = [
            get_team_tactics,
            get_historical_record,
            search_tactical_database
        ]
        
        # 构建 Prompt 模板
        self.prompt_template = self._build_prompt_template()
        
        # 初始化输出解析器
        self.output_parser = PydanticOutputParser(pydantic_object=MatchExplanation)
    
    def _build_prompt_template(self) -> ChatPromptTemplate:
        """
        构建 Prompt 模板
        
        明确约束 LLM 的行为，确保只解释不修改预测结果。
        """
        system_message = """你是一个专业的足球战术分析师。你的任务是基于给定的比赛预测结果，
结合战术知识和历史数据，生成一份专业的解释报告。

**重要约束**：
1. 你只能解释传入的比分和胜负状态，绝对不能修改或推翻这些结果
2. 必须使用提供的工具查询战术信息和历史记录
3. 输出必须符合 MatchExplanation Schema 的格式要求
4. 保持客观、专业、基于事实的分析风格

**工作流程**：
1. 首先使用 get_team_tactics 工具查询两队的战术风格
2. 然后使用 get_historical_record 工具查询历史交锋记录
3. 如有需要，使用 search_tactical_database 搜索特定战术问题
4. 最后综合所有信息，生成结构化的解释报告

**输出要求**：
- tactical_analysis: 详细分析两队战术风格的克制关系
- key_player_impact: 分析关键球员如何影响比赛走向
- historical_context: 总结历史交锋的心理优势和劣势
- confidence_score: 给出 0-1 之间的置信度评分
- prediction_summary: 简要复述传入的比分（不得修改）

请记住：你的工作是解释为什么会出现这个结果，而不是质疑结果本身。"""

        human_message = """请解释以下比赛预测结果：

比赛信息：
- A队：{team_a_name} (Elo: {team_a_elo})
- B队：{team_b_name} (Elo: {team_b_elo})
- 预测比分：{team_a_name} {score_a}:{score_b} {team_b_name}
- 胜者：{winner_name}

其他信息：
- 调整系数：{adjustment:+.4f}
- 基础胜率：{base_win_prob:.2%}

请使用工具查询相关信息，然后生成解释报告。"""

        return ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("human", human_message)
        ])
    
    def explain_match(
        self,
        team_a_name: str,
        team_a_elo: float,
        team_b_name: str,
        team_b_elo: float,
        score_a: int,
        score_b: int,
        winner_name: str,
        adjustment: float = 0.0,
        base_win_prob: float = 0.5
    ) -> MatchExplanation:
        """
        生成比赛解释报告
        
        Args:
            team_a_name: A队名称
            team_a_elo: A队 Elo 评分
            team_b_name: B队名称
            team_b_elo: B队 Elo 评分
            score_a: A队进球数
            score_b: B队进球数
            winner_name: 胜者名称
            adjustment: 注意力网络调整系数
            base_win_prob: 基础胜率
            
        Returns:
            MatchExplanation: 结构化的解释报告
        """
        # 构建输入变量
        input_variables = {
            "team_a_name": team_a_name,
            "team_a_elo": team_a_elo,
            "team_b_name": team_b_name,
            "team_b_elo": team_b_elo,
            "score_a": score_a,
            "score_b": score_b,
            "winner_name": winner_name,
            "adjustment": adjustment,
            "base_win_prob": base_win_prob
        }
        
        try:
            # 方法 1：使用结构化输出（推荐，需要 OpenAI）
            print(f"🧠 [LLM] Starting structured output generation for {input_variables['team_a_name']} vs {input_variables['team_b_name']}")
            explanation = self._explain_with_structured_output(input_variables)
            print(f"✅ [LLM] Structured output succeeded")
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"❌ [LLM] Structured output failed: {e}")
            print(f"📋 [LLM] Error details:\n{error_details}")
            print(f"🔄 [LLM] Falling back to template method...")
            # 方法 2：回退到模板方法
            explanation = self._explain_with_template(input_variables)
        
        return explanation
    
    def _explain_with_structured_output(self, input_variables: dict) -> MatchExplanation:
        """
        使用智谱AI原生SDK调用并手动解析 JSON 响应
        """
        import json
        import re
        print(f"🔧 [LLM] Calling ZhipuAI native SDK for structured output...")
        
        # 手动调用工具获取信息，注入到 prompt 中
        tactics_a = get_team_tactics.invoke({"team_name": input_variables["team_a_name"]})
        tactics_b = get_team_tactics.invoke({"team_name": input_variables["team_b_name"]})
        history = get_historical_record.invoke({
            "team_a": input_variables["team_a_name"],
            "team_b": input_variables["team_b_name"]}
        )
        
        # 构建系统消息
        system_message = """你是一个专业的足球战术分析师。你的任务是基于给定的比赛预测结果，
结合战术知识和历史数据，生成一份专业的解释报告。

**重要约束**：
1. 你只能解释传入的比分和胜负状态，绝对不能修改或推翻这些结果
2. 输出必须是严格的 JSON 格式（不要用 ```json 包裹），严格符合以下格式：
{
  "tactical_analysis": "战术分析文本",
  "key_player_impact": "关键球员影响文本",
  "historical_context": "历史背景文本",
  "confidence_score": 0.85,
  "prediction_summary": "预测摘要文本"
}
3. 保持客观、专业、基于事实的分析风格

请记住：你的工作是解释为什么会出现这个结果，而不是质疑结果本身。"""

        # 构建用户消息
        user_message = f"""请解释以下比赛预测结果：

比赛信息：
- A队：{input_variables['team_a_name']} (Elo: {input_variables['team_a_elo']})
- B队：{input_variables['team_b_name']} (Elo: {input_variables['team_b_elo']})
- 预测比分：{input_variables['team_a_name']} {input_variables['score_a']}:{input_variables['score_b']} {input_variables['team_b_name']}
- 胜者：{input_variables['winner_name']}

其他信息：
- 调整系数：{input_variables['adjustment']:+.4f}
- 基础胜率：{input_variables['base_win_prob']:.2%}

以下是已查询到的战术信息：

A队战术信息：
{tactics_a}

B队战术信息：
{tactics_b}

历史交锋记录：
{history}

请直接输出 JSON 格式的解释报告。"""
        
        print(f"📡 [LLM] Calling ZhipuAI API (model: {self.model_name})...")
        response = self.zhipu_client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1,
            max_tokens=1000
        )
        
        content = response.choices[0].message.content
        print(f"📝 [LLM] Raw response preview: {content[:200]}...")
        
        # 清理 markdown 代码块包裹
        content = re.sub(r'^```(?:json)?\s*\n?', '', content.strip())
        content = re.sub(r'\n?```\s*$', '', content.strip())
        
        # 提取 JSON 部分
        json_start = content.find('{')
        json_end = content.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            json_str = content[json_start:json_end]
            data = json.loads(json_str)
            
            return MatchExplanation(
                tactical_analysis=str(data.get("tactical_analysis", "战术分析暂缺")),
                key_player_impact=str(data.get("key_player_impact", "关键球员分析暂缺")),
                historical_context=str(data.get("historical_context", "历史背景暂缺")),
                confidence_score=float(data.get("confidence_score", 0.7)),
                prediction_summary=str(data.get("prediction_summary", f"{input_variables['team_a_name']} {input_variables['score_a']}:{input_variables['score_b']} {input_variables['team_b_name']}"))
            )
        else:
            raise ValueError("无法从 LLM 响应中提取 JSON")
    
    def _explain_with_zhipu_native(self, input_variables: dict) -> MatchExplanation:
        """
        使用智谱原生 API 生成解释
        
        由于智谱原生 API 不支持 LangChain 的结构化输出，我们需要手动构建 prompt 并解析响应。
        """
        import json
        
        # 构建系统消息
        system_message = """你是一个专业的足球战术分析师。你的任务是基于给定的比赛预测结果，
结合战术知识和历史数据，生成一份专业的解释报告。

**重要约束**：
1. 你只能解释传入的比分和胜负状态，绝对不能修改或推翻这些结果
2. 必须使用提供的工具查询战术信息和历史记录
3. 输出必须是严格的 JSON 格式，符合以下 Schema：
{
  "tactical_analysis": "战术相克分析...",
  "key_player_impact": "关键球员影响...",
  "historical_context": "历史交锋摘要...",
  "confidence_score": 0.85,
  "prediction_summary": "预测结果摘要..."
}
4. 保持客观、专业、基于事实的分析风格

请记住：你的工作是解释为什么会出现这个结果，而不是质疑结果本身。"""

        # 构建用户消息
        user_message = f"""请解释以下比赛预测结果：

比赛信息：
- A队：{input_variables['team_a_name']} (Elo: {input_variables['team_a_elo']})
- B队：{input_variables['team_b_name']} (Elo: {input_variables['team_b_elo']})
- 预测比分：{input_variables['team_a_name']} {input_variables['score_a']}:{input_variables['score_b']} {input_variables['team_b_name']}
- 胜者：{input_variables['winner_name']}

其他信息：
- 调整系数：{input_variables['adjustment']:+.4f}
- 基础胜率：{input_variables['base_win_prob']:.2%}

请先使用工具查询相关信息，然后生成 JSON 格式的解释报告。"""

        # 手动调用工具获取信息
        tactics_a = get_team_tactics.invoke({"team_name": input_variables["team_a_name"]})
        tactics_b = get_team_tactics.invoke({"team_name": input_variables["team_b_name"]})
        history = get_historical_record.invoke({
            "team_a": input_variables["team_a_name"],
            "team_b": input_variables["team_b_name"]
        })
        
        # 将工具结果添加到用户消息中
        user_message += f"\n\n【战术数据库查询结果】\n\nA队战术信息：\n{tactics_a}\n\nB队战术信息：\n{tactics_b}\n\n历史交锋记录：\n{history}"

        try:
            print(f" [Zhipu] Calling Zhipu API (model: {self.model_name})...")
            
            # 调用智谱 API
            response = self.zhipu_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.1,
                max_tokens=1000
            )
            
            # 提取响应内容
            content = response.choices[0].message.content
            print(f"✅ [Zhipu] Received response from API")
            print(f"📝 [Zhipu] Response preview: {content[:200]}...")
            
            # 尝试解析 JSON
            # 首先尝试直接解析
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                # 如果直接解析失败，尝试提取 JSON 部分
                json_start = content.find('{')
                json_end = content.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = content[json_start:json_end]
                    data = json.loads(json_str)
                else:
                    raise ValueError("无法从响应中提取 JSON")
            
            # 构建 MatchExplanation 对象
            return MatchExplanation(
                tactical_analysis=data.get("tactical_analysis", "战术分析暂缺"),
                key_player_impact=data.get("key_player_impact", "关键球员分析暂缺"),
                historical_context=data.get("historical_context", "历史背景暂缺"),
                confidence_score=float(data.get("confidence_score", 0.7)),
                prediction_summary=data.get("prediction_summary", f"{input_variables['team_a_name']} {input_variables['score_a']}:{input_variables['score_b']} {input_variables['team_b_name']}")
            )
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f" [Zhipu] API call failed: {e}")
            print(f"📋 [Zhipu] Error details:\n{error_details}")
            raise
    
    def _explain_with_template(self, input_variables: dict) -> MatchExplanation:
        """
        使用模板方法的回退方案
        
        当结构化输出不可用时使用。
        """
        # 手动调用工具获取信息
        tactics_a = get_team_tactics.invoke({"team_name": input_variables["team_a_name"]})
        tactics_b = get_team_tactics.invoke({"team_name": input_variables["team_b_name"]})
        history = get_historical_record.invoke({
            "team_a": input_variables["team_a_name"],
            "team_b": input_variables["team_b_name"]
        })
        
        # 构建简化的 prompt
        simple_prompt = f"""
基于以下信息解释比赛结果：

{tactics_a}

{tactics_b}

{history}

比赛结果：{input_variables['team_a_name']} {input_variables['score_a']}:{input_variables['score_b']} {input_variables['team_b_name']}
胜者：{input_variables['winner_name']}

请生成 JSON 格式的解释报告，包含以下字段：
- tactical_analysis: 战术分析
- key_player_impact: 关键球员影响
- historical_context: 历史背景
- confidence_score: 置信度（0-1）
- prediction_summary: 预测摘要

注意：只能解释结果，不能修改比分！
"""
        
        # 调用 LLM（智谱原生SDK）
        import json
        import re
        response = self.zhipu_client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": simple_prompt}],
            temperature=0.1,
            max_tokens=1000
        )
        content = response.choices[0].message.content
        
        # 尝试解析 JSON
        import json
        try:
            # 提取 JSON 部分
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                data = json.loads(json_str)
                
                return MatchExplanation(
                    tactical_analysis=data.get("tactical_analysis", "战术分析暂缺"),
                    key_player_impact=data.get("key_player_impact", "关键球员分析暂缺"),
                    historical_context=data.get("historical_context", "历史背景暂缺"),
                    confidence_score=float(data.get("confidence_score", 0.7)),
                    prediction_summary=data.get("prediction_summary", f"{input_variables['team_a_name']} {input_variables['score_a']}:{input_variables['score_b']} {input_variables['team_b_name']}")
                )
        except Exception as e:
            print(f"JSON 解析失败: {e}")
        
        # 最后的回退方案：返回默认解释
        return MatchExplanation(
            tactical_analysis=f"{input_variables['team_a_name']}凭借战术优势战胜了{input_variables['team_b_name']}",
            key_player_impact="关键球员的出色发挥决定了比赛走向",
            historical_context="根据历史交锋记录，本场比赛结果符合预期",
            confidence_score=0.7,
            prediction_summary=f"{input_variables['team_a_name']} {input_variables['score_a']}:{input_variables['score_b']} {input_variables['team_b_name']}"
        )
    
    def batch_explain(
        self,
        matches: List[dict]
    ) -> List[MatchExplanation]:
        """
        批量解释多场比赛
        
        Args:
            matches: 比赛列表，每个元素包含比赛信息字典
            
        Returns:
            解释报告列表
        """
        explanations = []
        
        for match in matches:
            explanation = self.explain_match(**match)
            explanations.append(explanation)
        
        return explanations


# ==================== 测试代码 ====================

if __name__ == "__main__":
    print("=" * 70)
    print("MatchExplainerAgent 测试")
    print("=" * 70)
    
    # 测试 1: 初始化工具
    print("\n【测试 1】工具函数测试")
    print("-" * 70)
    
    # 测试战术查询工具
    tactics = get_team_tactics.invoke({"team_name": "Brazil"})
    print(tactics)
    
    print("\n")
    
    # 测试历史查询工具
    history = get_historical_record.invoke({
        "team_a": "Brazil",
        "team_b": "Germany"
    })
    print(history)
    
    print("\n")
    
    # 测试搜索工具
    search_result = search_tactical_database.invoke({
        "query": "Brazil tactics"
    })
    print(search_result)
    
    # 测试 2: 初始化 Agent
    print("\n\n【测试 2】Agent 初始化")
    print("-" * 70)
    
    agent = MatchExplainerAgent(
        model_name="glm-4-flash",
        api_key="test-key",  # 占位符
        use_local_model=False
    )
    
    print("Agent 初始化成功")
    print(f"工具数量: {len(agent.tools)}")
    print(f"工具列表: {[tool.name for tool in agent.tools]}")
    
    # 测试 3: 生成解释（使用回退方法）
    print("\n\n【测试 3】生成比赛解释（回退方法）")
    print("-" * 70)
    
    explanation = agent.explain_match(
        team_a_name="Brazil",
        team_a_elo=2100.0,
        team_b_name="Germany",
        team_b_elo=1950.0,
        score_a=2,
        score_b=1,
        winner_name="Brazil",
        adjustment=0.05,
        base_win_prob=0.65
    )
    
    print("\n生成的解释报告:")
    print("=" * 70)
    print(f"\n【战术分析】\n{explanation.tactical_analysis}")
    print(f"\n【关键球员影响】\n{explanation.key_player_impact}")
    print(f"\n【历史背景】\n{explanation.historical_context}")
    print(f"\n【置信度】{explanation.confidence_score:.2f}")
    print(f"\n【预测摘要】\n{explanation.prediction_summary}")
    print("=" * 70)
    
    # 测试 4: 批量解释
    print("\n\n【测试 4】批量解释测试")
    print("-" * 70)
    
    test_matches = [
        {
            "team_a_name": "Argentina",
            "team_a_elo": 2050.0,
            "team_b_name": "France",
            "team_b_elo": 2000.0,
            "score_a": 3,
            "score_b": 2,
            "winner_name": "Argentina",
            "adjustment": 0.03,
            "base_win_prob": 0.58
        },
        {
            "team_a_name": "Spain",
            "team_a_elo": 1980.0,
            "team_b_name": "England",
            "team_b_elo": 1950.0,
            "score_a": 1,
            "score_b": 0,
            "winner_name": "Spain",
            "adjustment": -0.02,
            "base_win_prob": 0.52
        }
    ]
    
    explanations = agent.batch_explain(test_matches)
    
    print(f"批量生成了 {len(explanations)} 份解释报告")
    for i, exp in enumerate(explanations, 1):
        print(f"\n报告 {i}: {exp.prediction_summary}")
        print(f"  置信度: {exp.confidence_score:.2f}")
    
    print("\n" + "=" * 70)
    print("所有测试完成！")
    print("=" * 70)
