# ============================================================
# prompts.py —— 考古 Prompt 模板库（阶段 5.2）
# 定义 10+ 考古场景的 LLM Prompt 模板，含占位符，供 5.4 报告/5.1 LLM 调用。
# ============================================================
"""考古 LLM Prompt 模板库。"""

# 场景模板：每个模板含 {说明}，供 LLM 生成对应内容
PROMPTS = {
    # 断代分析（核心）
    "dating_analysis": (
        "你是一位资深考古断代专家。请根据以下文物信息进行断代分析：\n"
        "文物：{title}（来源：{source}）\n"
        "视觉特征：{visual}\n"
        "候选年代：{periods}\n"
        "相似文物：{similar}\n"
        "请给出断代结论、依据与置信度（0-1）。"
    ),
    # 文化来源
    "culture_provenance": (
        "根据以下信息，判断该文物的文化来源：\n"
        "文物：{title}\n"
        "文化候选：{cultures}\n"
        "地域线索：{geo}\n"
        "请给出文化归属与推理。"
    ),
    # 材质鉴定
    "material_analysis": (
        "根据以下线索分析文物材质：\n"
        "{materials}\n"
        "请指出材质并说明依据。"
    ),
    # 器型与用途
    "form_usage": (
        "分析该文物的器型与可能用途：\n"
        "{form}\n{description}"
    ),
    # 纹饰与象征
    "decoration_symbolism": (
        "解读该文物纹饰的象征意涵：\n{decorations}\n{description}"
    ),
    # 真伪鉴定
    "authenticity": (
        "请根据以下证据初步评估文物真伪风险：\n"
        "{evidence}\n"
        "指出可疑点与需进一步检测项。"
    ),
    # 工艺特征
    "craft_analysis": (
        "分析该文物的工艺特征：\n{dimensions}\n{medium}\n{description}"
    ),
    # 断代报告汇总（5.4 报告生成）
    "report_summary": (
        "请将以下证据链整理为结构化断代报告（JSON）：\n"
        "{evidence_chain}"
    ),
    # 检索解释
    "retrieval_explain": (
        "解释为何以下相似文物被检索到：\n{similar}\n与查询 {title} 的关联。"
    ),
    # 图谱证据解读
    "graph_evidence": (
        "解读知识图谱证据：\n{culture_trace}\n{period_infer}\n"
        "说明其对断代的支撑。"
    ),
}
