# ============================================================
# labels.py —— 5 级标签规则表（阶段 1.3）
# 时期(period) / 文化(culture) / 材质(material) / 器型(form) / 纹饰(decoration)
# 基于字段关键词映射；英文原文 → 标准中文标签
# ============================================================
"""5 级标签规则表与推断辅助函数。"""
import re

# ---- 文化：英文 culture → 中文标签 ----
CULTURE_MAP = {
    "china": "中国", "chinese": "中国",
    "america": "美国", "american": "美国",
    "france": "法国", "french": "法国",
    "netherlands": "荷兰", "dutch": "荷兰",
    "italy": "意大利", "italian": "意大利",
    "spain": "西班牙", "spanish": "西班牙",
    "flanders": "佛兰德斯", "flemish": "佛兰德斯",
    "germany": "德国", "german": "德国",
    "england": "英国", "britain": "英国", "british": "英国",
    "japan": "日本", "japanese": "日本",
    "korea": "韩国", "korean": "韩国",
    "india": "印度", "indian": "印度",
    "egypt": "埃及", "egyptian": "埃及",
    "greece": "希腊", "greek": "希腊",
    "rome": "罗马", "roman": "罗马",
    "byzantine": "拜占庭", "persian": "波斯", "ottoman": "奥斯曼",
}

# ---- 材质：medium 关键词 → 中文标签 ----
MATERIAL_MAP = [
    ("porcelain", "瓷"), ("ceramic", "陶"), ("earthenware", "陶"),
    ("stoneware", "炻器"), ("bronze", "青铜"), ("brass", "黄铜"),
    ("copper", "铜"), ("gold", "金"), ("silver", "银"), ("iron", "铁"),
    ("ivory", "象牙"), ("jade", "玉"), ("nephrite", "玉"),
    ("wood", "木"), ("bamboo", "竹"), ("silk", "丝"), ("lacquer", "漆"),
    ("metal", "金属"), ("stone", "石"), ("marble", "大理石"),
    ("ink", "墨"), ("watercolor", "水彩"), ("oil paint", "油画"),
    ("paper", "纸"), ("glass", "玻璃"), ("enamel", "珐琅"),
    ("mother-of-pearl", "螺钿"), ("textile", "织物"), ("tapestry", "挂毯"),
    ("painting", "绘画"),
]

# ---- 器型：title 关键词 → 中文标签 ----
FORM_MAP = [
    ("bowl", "碗"), ("vase", "瓶"), ("jar", "罐"), ("pot", "罐"),
    ("sword", "剑"), ("dagger", "匕首"), ("ring", "戒指"), ("coin", "钱币"),
    ("portrait", "肖像画"), ("painting", "绘画"), ("drawing", "素描"),
    ("statue", "雕塑"), ("figure", "人物雕塑"), ("statuette", "小雕塑"),
    ("plate", "盘"), ("dish", "盘"), ("cup", "杯"), ("teapot", "茶壶"),
    ("bottle", "瓶"), ("box", "盒"), ("mirror", "镜"), ("scroll", "卷轴"),
    ("album", "册页"), ("flask", "扁瓶"), ("goblet", "高脚杯"),
    ("candlestick", "烛台"), ("ax", "斧"), ("helmet", "盔"), ("armor", "甲"),
    ("shield", "盾"), ("sculpture", "雕塑"), ("mask", "面具"), ("tile", "瓦"),
]

# ---- 纹饰：title/description 关键词 → 中文标签 ----
DECORATION_MAP = [
    ("dragon", "龙纹"), ("phoenix", "凤纹"), ("lotus", "莲纹"),
    ("floral", "花卉纹"), ("flower", "花卉纹"), ("blossom", "花卉纹"),
    ("landscape", "山水"), ("mountain", "山水"),
    ("wave", "水波纹"), ("cloud", "云纹"), ("clouds", "云纹"),
    ("animal", "动物纹"), ("bird", "鸟纹"), ("fish", "鱼纹"),
    ("geometric", "几何纹"), ("vine", "缠枝纹"), ("scroll", "卷草纹"),
    ("figure", "人物纹"), ("portrait", "人物"), ("battle", "战争场景"),
    ("hunting", "狩猎纹"), ("grape", "葡萄纹"), ("bats", "蝠纹"),
]


def map_by_keywords(text, table):
    """在 text（小写）中匹配 table 关键词，返回所有命中标签（去重、保序）。"""
    if not text:
        return []
    lower = text.lower()
    hits = []
    for keyword, label in table:
        if keyword in lower and label not in hits:
            hits.append(label)
    return hits


def map_culture(culture):
    """culture 字段 → 中文标签（取首个匹配关键词）。"""
    if not culture:
        return None
    lower = culture.lower()
    for keyword, label in CULTURE_MAP.items():
        if keyword in lower:
            return label
    return culture.strip() or None


def date_to_period(date_str):
    """从 date 提取首个 4 位年份 → 时期标签。"""
    if not date_str:
        return None
    match = re.search(r"(?<!\d)(\d{4})(?!\d)", str(date_str))
    if not match:
        return None
    year = int(match.group(1))
    if year < 1000:
        return "古代"
    if year < 1300:
        return "中世纪"
    if year < 1500:
        return "中世纪末期"
    if year < 1800:
        return "近代早期"
    if year < 1945:
        return "近代"
    return "现代"


def map_materials(medium):
    """medium 字段 → 材质标签列表。"""
    return map_by_keywords(medium, MATERIAL_MAP)


def map_forms(title):
    """title 字段 → 器型标签列表。"""
    return map_by_keywords(title, FORM_MAP)


def map_decorations(title, description=""):
    """title + description → 纹饰标签列表。"""
    return map_by_keywords(f"{title} {description}", DECORATION_MAP)
