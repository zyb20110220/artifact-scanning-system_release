# ============================================================
# quality.py —— 质量过滤（阶段 1.2）
# 规则：必须有 id 与 title（非空）
# ============================================================
"""质量过滤：去除无效 / 低质量记录。"""


def is_valid(record):
    """判断记录是否通过质量过滤。

    当前规则：
    - 必须有 id
    - 必须有非空 title
    """
    if not record.get("id"):
        return False
    title = record.get("title")
    if not title or not str(title).strip():
        return False
    return True
