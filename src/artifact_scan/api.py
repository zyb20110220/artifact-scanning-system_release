# ============================================================
# api.py —— 阶段 6 后端 API（FastAPI）
# 提供：
#   GET  /api/health           服务健康状态
#   POST /api/analyze          上传文物图 -> LLM 断代分析 + 相似检索 + 图谱证据
# 前端：frontend/（文博典藏风格）。启动：uvicorn artifact_scan.api:app
# 说明：各服务用懒加载 + try/except，不可用时降级并在 services/degraded 中标注。
# ============================================================
"""阶段 6 后端 API。"""
import io
import json
import logging
import os
import re
import tempfile
from collections import Counter

import numpy as np
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

_OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11435")
_MILVUS = os.environ.get("MILVUS_URL", "http://127.0.0.1:19530")
_NEO4J = os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687")
_NEO4J_USER = "neo4j"
_NEO4J_PASS = os.environ.get("NEO4J_PASSWORD", "graph2026")
_FRONTEND = os.path.normpath(os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend"))

app = FastAPI(title="文物断代与鉴定系统 API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# 特征模型缓存（懒加载，CPU）
_models = {}


def get_model(name):
    if name not in _models:
        from .feature.model import FeatureModel
        _models[name] = FeatureModel(name, device="cpu")
    return _models[name]


def _l2(v):
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    n = np.linalg.norm(v)
    return (v / n) if n else v


def _query_views(image_path):
    """对上传图提取各视图特征（dinov2/siglip/registers），fused 用均值近似。"""
    from PIL import Image
    img = Image.open(image_path).convert("RGB")
    # 视图名 -> FeatureModel 注册名
    view_to_model = {
        "dinov2": "dinov2-base",
        "siglip": "siglip-base",
        "registers": "dinov2-registers-base",
    }
    views = {}
    for view, model_name in view_to_model.items():
        model = get_model(model_name)
        views[view] = model.extract_one(img)
    # fused: 三视图归一化均值作为查询（近似融合，配合 IP/cosine 检索）
    fused = _l2(
        np.mean([views["dinov2"], views["siglip"], views["registers"]], axis=0))
    views["fused"] = fused
    return views


def _ollama_analyze(image_path, model="qwen2.5-vl:3b"):
    """调用 Ollama 对图片做断代鉴定，返回文本分析。"""
    import base64
    import requests
    with open(image_path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    prompt = (
        "你是一位资深文物鉴定专家。请根据这幅文物图片出具一份完整、详实的鉴定报告，"
        "全文不少于 400 字，用中文撰写，按下述结构分段：\n"
        "一、年代判断：给出年代区间，并说明推断依据（器型演变、纹饰特征、工艺水平等可见细节）。\n"
        "二、文化归属：说明所属文化/风格，并解释判断理由。\n"
        "三、材质与工艺：描述可见的材质特征与制作工艺痕迹。\n"
        "四、器型与纹饰：详细描述器型、纹饰图案及其风格来源。\n"
        "五、真伪与保存状况：评估真伪并描述保存状况。\n"
        "请在正文中穿插说明你从图像细节到结论的推理步骤。"
        "报告最后单独一行输出 JSON："
        '{"period":"...","culture":"...","confidence":0.0}。'
    )
    body = {"model": model, "prompt": prompt, "images": [b64],
            "stream": False,
            "options": {"num_ctx": 4096, "num_predict": 1400, "temperature": 0.3}}
    r = requests.post(f"{_OLLAMA}/api/generate", json=body, timeout=900)
    r.raise_for_status()
    return r.json().get("response", "")


def _extract_llm_json(text):
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return {}
    return {}


_REPORT_FIELDS = [
    ("period", "年代"),
    ("culture", "文化归属"),
    ("type", "类型"),
    ("material", "材质"),
    ("pattern", "纹饰与风格"),
    ("authenticity", "真伪"),
    ("conservation", "保存状况"),
    ("confidence", "置信度"),
]


def _strip_code_fence(text):
    """去掉 markdown 代码围栏标记（```json 与结尾 ```），保留内部内容。"""
    t = re.sub(r"^```[a-zA-Z]*\s*", "", (text or "").strip())
    t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _expand_llm_report(text):
    """LLM 仅返回 JSON（含围栏包裹）时，展开为可读的鉴定报告文本。"""
    t = _strip_code_fence(text)
    if not (t.startswith("{") and t.endswith("}")):
        return text
    try:
        obj = json.loads(t)
    except Exception:
        return text
    lines = []
    for key, label in _REPORT_FIELDS:
        v = obj.get(key)
        if v is None or v == "":
            continue
        if key == "confidence":
            try:
                n = float(v)
                v = f"{n * 100:.1f}%" if 0 <= n <= 1 else str(v)
            except Exception:
                pass
        lines.append(f"【{label}】{v}")
    return "\n".join(lines) if lines else text


def _ensure_report_depth(image_path, text, model="qwen2.5-vl:3b", min_chars=200):
    """模型输出过短（如仅 JSON）时，追加一次调用生成详细文字报告。"""
    import base64
    import requests
    compact = re.sub(r"\s+", "", _strip_code_fence(text))
    if len(compact) >= min_chars:
        return text
    with open(image_path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    prompt = (
        "你是一位资深文物鉴定专家。请针对这幅文物写一份不少于 500 字的详细鉴定报告，"
        "用中文撰写，依次论述：1) 年代判断及其依据（器型演变、纹饰风格、工艺特征等可见细节）；"
        "2) 文化归属及其理由；3) 材质与工艺痕迹；4) 器型与纹饰的详细描述；"
        "5) 真伪与保存状况。每一部分都要描述你观察到的图像细节，"
        "并说明从细节到结论的推断过程。直接输出报告正文，不要输出 JSON。"
    )
    body = {"model": model, "prompt": prompt, "images": [b64],
            "stream": False,
            "options": {"num_ctx": 4096, "num_predict": 1200, "temperature": 0.3}}
    try:
        r = requests.post(f"{_OLLAMA}/api/generate", json=body, timeout=900)
        r.raise_for_status()
        detailed = r.json().get("response", "")
        return detailed if detailed else text
    except Exception:
        return text


def _evidence_summary(similar, graph):
    """用真实检索与图谱结果生成数据驱动的比对与证据链摘要。"""
    parts = []
    sims = similar or []
    if sims:
        items = "；".join(
            f"{s.get('title') or s.get('id')}（检索得分 {s.get('score', 0):.3f}）"
            for s in sims[:5])
        parts.append(
            f"【相似比对】在馆藏数据库中检索到 {len(sims)} 件高度相似文物：{items}。")
    nodes = (graph or {}).get("nodes", [])
    edges = (graph or {}).get("edges", [])
    if nodes:
        arts = [n for n in nodes if n.get("type") == "artifact"]
        ents = [n for n in nodes if n.get("type") != "artifact"]
        ent_txt = "、".join(n.get("label") or n.get("id", "") for n in ents[:8])
        rel_names = {"HAS_CULTURE": "文化", "HAS_PERIOD": "时期", "HAS_MATERIAL": "材料",
                     "HAS_FORM": "器型", "HAS_DECORATION": "纹饰"}
        rel_counts = Counter(e.get("type") for e in edges)
        rel_txt = "、".join(
            f"{rel_names.get(k, k)} {v} 条" for k, v in rel_counts.items())
        parts.append(
            f"【证据链】相似文物共 {len(arts)} 件，图谱证据 {len(edges)} 条"
            f"（{rel_txt}），关联要素：{ent_txt}。这些要素支撑上述断代判断。")
    return "\n\n".join(parts)


def _milvus_recall(query_views, topk=5, cand=20):
    """多路召回：对每个视图查询 Milvus，RRF 融合返回 Top-K 相似 id。"""
    from pymilvus import MilvusClient
    from .feature.recall import VIEWS
    from .feature.recall import _load_meta as load_meta

    client = MilvusClient(uri=_MILVUS)
    metas = load_meta()
    id2title = {str(m["id"]): m.get("title", "") for m in metas}
    id2source = {str(m["id"]): m.get("source", "") for m in metas}

    K = 60
    scores = {}
    for name, collection, _path in VIEWS:
        q = query_views.get(name)
        if q is None:
            continue
        res = client.search(collection, data=[q.tolist()], limit=cand,
                            output_fields=["id"], search_params={"metric_type": "IP"})
        for rank, hit in enumerate(res[0]):
            cid = str(hit["id"])
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (K + rank)

    ranked = sorted(scores.items(), key=lambda t: -t[1])[:topk]
    out = []
    for cid, sc in ranked:
        out.append({"id": cid, "title": id2title.get(cid, ""),
                    "source": id2source.get(cid, ""), "score": round(sc, 4)})
    return out


def _graph_evidence(artifact_ids):
    """从 Neo4j 查询相似文物的文化/时期/材料/器型/纹饰线索，构建证据链图。"""
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(_NEO4J, auth=(_NEO4J_USER, _NEO4J_PASS),
                                  connection_timeout=5)
    nodes, edges, seen = [], [], set()

    def add_node(nid, label, ntype):
        if nid in seen:
            return
        seen.add(nid)
        nodes.append({"id": nid, "label": label, "type": ntype})

    def link(src, names, prefix, ntype, rel):
        for name in (names or []):
            add_node(prefix + name, name, ntype)
            edges.append({"source": src, "target": prefix + name, "type": rel})

    try:
        with driver.session() as sess:
            rows = sess.run(
                "MATCH (a:Artifact) WHERE a.id IN $ids "
                "OPTIONAL MATCH (a)-[:HAS_CULTURE]->(c:Culture) "
                "OPTIONAL MATCH (a)-[:HAS_PERIOD]->(p:Period) "
                "OPTIONAL MATCH (a)-[:HAS_MATERIAL]->(m:Material) "
                "OPTIONAL MATCH (a)-[:HAS_FORM]->(f:Form) "
                "OPTIONAL MATCH (a)-[:HAS_DECORATION]->(d:Decoration) "
                "RETURN a.id AS id, a.title AS title, "
                "collect(DISTINCT c.name) AS cultures, "
                "collect(DISTINCT p.name) AS periods, "
                "collect(DISTINCT m.name) AS materials, "
                "collect(DISTINCT f.name) AS forms, "
                "collect(DISTINCT d.name) AS decorations",
                ids=[str(i) for i in artifact_ids]).data()
            for r in rows:
                aid = r["id"]
                add_node(aid, r.get("title") or aid, "artifact")
                link(aid, r["cultures"], "cul_", "culture", "HAS_CULTURE")
                link(aid, r["periods"], "per_", "period", "HAS_PERIOD")
                link(aid, r["materials"], "mat_", "material", "HAS_MATERIAL")
                link(aid, r["forms"], "frm_", "form", "HAS_FORM")
                link(aid, r["decorations"], "dec_",
                     "decoration", "HAS_DECORATION")
    finally:
        driver.close()
    return {"nodes": nodes, "edges": edges}


@app.get("/api/health")
def health():
    checks = {}
    try:
        import requests
        requests.get(f"{_OLLAMA}/api/tags", timeout=3)
        checks["ollama"] = "up"
    except Exception:
        checks["ollama"] = "down"
    try:
        from pymilvus import MilvusClient
        MilvusClient(uri=_MILVUS, timeout=3).close()
        checks["milvus"] = "up"
    except Exception:
        checks["milvus"] = "down"
    try:
        from neo4j import GraphDatabase
        d = GraphDatabase.driver(_NEO4J, auth=(
            _NEO4J_USER, _NEO4J_PASS), connection_timeout=5)
        d.verify_connectivity()
        d.close()
        checks["neo4j"] = "up"
    except Exception:
        checks["neo4j"] = "down"
    return {"services": checks}


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "未收到图片")
    suffix = os.path.splitext(file.filename or "image.jpg")[1] or ".jpg"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    services = {}
    result = {"image": file.filename, "services": services, "degraded": False}

    # 1) LLM 断代分析（核心，线程池执行避免阻塞事件循环）
    try:
        text = await run_in_threadpool(_ollama_analyze, tmp_path)
        via_llm = _extract_llm_json(text)  # 先提取结论（第一遍输出含 JSON）
        text = await run_in_threadpool(_ensure_report_depth, tmp_path, text)
        result["llm_analysis"] = _expand_llm_report(text)
        if not via_llm:  # 兜底：从最终文本再尝试一次
            via_llm = _extract_llm_json(text)
        result["conclusion"] = {
            "period": via_llm.get("period"),
            "culture": via_llm.get("culture"),
            "confidence": via_llm.get("confidence"),
        }
        services["llm"] = "up"
    except Exception as exc:
        result["llm_analysis"] = ""
        result["degraded"] = True
        services["llm"] = "down"
        logger.warning("LLM 分析失败：%s", exc)

    # 2) 相似文物检索（Milvus + 特征）
    try:
        qv = await run_in_threadpool(_query_views, tmp_path)
        result["similar"] = await run_in_threadpool(_milvus_recall, qv)
        services["milvus"] = "up"
    except Exception as exc:
        result["similar"] = []
        result["degraded"] = True
        services["milvus"] = "down"
        logger.warning("检索失败：%s", exc)

    # 3) 图谱证据（Neo4j）
    sim_ids = [s["id"] for s in result.get("similar", [])]
    if sim_ids:
        try:
            result["graph"] = await run_in_threadpool(_graph_evidence, sim_ids[:5])
            services["neo4j"] = "up"
        except Exception as exc:
            result["graph"] = {"nodes": [], "edges": []}
            services["neo4j"] = "down"
            logger.warning("图谱失败：%s", exc)
    else:
        result["graph"] = {"nodes": [], "edges": []}

    # 4) 追加数据驱动的比对与证据链摘要
    summary = _evidence_summary(result.get(
        "similar", []), result.get("graph", {}))
    if summary:
        base = result.get("llm_analysis") or ""
        result["llm_analysis"] = (
            base + "\n\n" + summary).strip() if base else summary

    os.unlink(tmp_path)
    return result


# 挂载前端静态资源（若存在）
if os.path.isdir(_FRONTEND):
    app.mount("/", StaticFiles(directory=_FRONTEND, html=True), name="frontend")
