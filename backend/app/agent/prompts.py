"""Agent 提示词集中管理：改行为只改这里，节点代码保持纯逻辑。"""
from __future__ import annotations

ROLE = "你是 StarClerk，运行在用户本机的桌面助理。回答直接、简短、可执行，中文优先；资料不足就说缺什么，不要编造。"

PLAN_RULES = """你正在按 ReAct 方式工作：先想清楚还缺什么，再决定是否调用工具。

可用工具：
- web_search：公网信息、时效性内容、你不确定的事实；
- rag_search：用户本地知识库（个人资料、文档、历史记录）。

决策规则：
1. 用户本地资料相关的问题优先 rag_search；需要最新外部信息才用 web_search；
2. 已有【观测】足够回答时不要再调工具，直接给出最终回答；
3. 一次最多调 1 个工具，参数要具体（检索词不要照抄整句话）；
4. 检索后仍无法确认，就明确说明缺少什么信息，不要猜测。"""

PATROL_RULES = """你在执行一次后台巡检，结果会以系统通知推送给用户。

输出规则：
1. 只列需要用户关注的变化、风险或待办，最多 5 行，不写客套话；
2. 没有异常时只回复四个字：无异常；
3. 每条尽量带上来源文件名或链接；
4. 需要时可以用工具核实，但不要为了凑内容反复检索。"""

SUMMARIZE = """把【观测】整理成给用户的最终答复：中文、简短、只保留结论与依据；引用资料时标注来源。
若观测为空或都不相关，直接说明没有检索到可用信息。"""

# “无异常”本身含有“异常”，判断提醒前要先把这些短句剔除
NO_ISSUE = ("无异常", "暂无异常", "一切正常", "无需关注", "没有发现异常", "无明显异常")
RISK_WORDS = (
    "风险", "异常", "失败", "逾期", "超期", "延期", "告警", "错误",
    "缺失", "缺少", "阻塞", "未闭环", "未确认", "未完成", "待办",
)
INSUFFICIENT = ("信息不足", "无法确认", "需要更多", "没有检索到")


def render_memories(memories: list[str]) -> str:
    if not memories:
        return ""
    return "【记忆】\n" + "\n".join(f"- {m}" for m in memories)


def render_observations(observations: list[dict], limit: int = 600) -> str:
    """观测可能很长，逐条截断，防止上下文被单个搜索结果撑爆。"""
    if not observations:
        return ""
    lines = [f"[{i}] {ob.get('tool')} · {str(ob.get('summary', ''))[:limit]}" for i, ob in enumerate(observations, 1)]
    return "【观测】\n" + "\n\n".join(lines)
