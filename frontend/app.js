// ============================================================
// app.js —— 阶段 6 前端交互（文博典藏风格全重写）
// 上传/拖拽 -> 骨架屏加载 -> POST /api/analyze ->
// 渲染结论/分析/相似/图谱 + 耗时显示
// ============================================================
(function () {
    "use strict";

    const dz = document.getElementById("dropzone");
    const fileInput = document.getElementById("fileInput");
    const preview = document.getElementById("preview");
    const dzIdle = document.getElementById("dzIdle");
    const dzBusy = document.getElementById("dzBusy");
    const results = document.getElementById("results");
    const skeleton = document.getElementById("skeleton");
    const content = document.getElementById("content");
    const elapsedEl = document.getElementById("elapsed");
    const conPeriod = document.getElementById("conPeriod");
    const conCulture = document.getElementById("conCulture");
    const conConf = document.getElementById("conConf");
    const llmEl = document.getElementById("llmAnalysis");
    const simList = document.getElementById("simList");
    const graphEl = document.getElementById("graph");
    const statusBtn = document.getElementById("statusBtn");
    const serviceNote = document.getElementById("serviceNote");

    // ---- 上传交互 ----
    dz.addEventListener("click", () => fileInput.click());
    dz.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            fileInput.click();
        }
    });
    fileInput.addEventListener("change", () => {
        if (fileInput.files.length) handle(fileInput.files[0]);
        fileInput.value = ""; // 允许重复选择同一文件
    });

    ["dragenter", "dragover"].forEach((ev) =>
        dz.addEventListener(ev, (e) => {
            e.preventDefault();
            dz.classList.add("dragover");
        })
    );
    ["dragleave", "drop"].forEach((ev) =>
        dz.addEventListener(ev, (e) => {
            e.preventDefault();
            dz.classList.remove("dragover");
        })
    );
    dz.addEventListener("drop", (e) => {
        const f = e.dataTransfer.files && e.dataTransfer.files[0];
        if (f) handle(f);
    });

    // ---- 剪贴板粘贴图片（Ctrl+V） ----
    document.addEventListener("paste", (e) => {
        const items = e.clipboardData && e.clipboardData.items;
        if (!items) return;
        for (const item of items) {
            if (item.type && item.type.startsWith("image/")) {
                const file = item.getAsFile();
                if (file) {
                    e.preventDefault();
                    handle(file);
                    return;
                }
            }
        }
    });

    // ---- 工具函数 ----
    function setState(mode) {
        // mode: "idle" | "busy"
        dzIdle.hidden = mode !== "idle";
        dzBusy.hidden = mode !== "busy";
        preview.hidden = mode === "busy" || !preview.src;
        // 已有预览图时，隐藏"将文物图片置于此处"占位文案
        if (mode === "idle" && preview.src) dzIdle.hidden = true;
    }

    function showPreview(file) {
        if (!preview) return;
        preview.src = URL.createObjectURL(file);
        preview.alt = file.name || "预览";
        preview.hidden = false;
        preview.onload = () => URL.revokeObjectURL(preview.src);
    }

    function showSkeleton(on) {
        skeleton.hidden = !on;
        content.hidden = on;
        if (on) elapsedEl.hidden = true;
    }

    // ---- 分析流程 ----
    async function handle(file) {
        if (!file) return;
        // 复位展示
        results.hidden = false;
        showPreview(file);
        setState("busy");
        showSkeleton(true);
        setConclusion("—", "—", "—");
        serviceNote.hidden = true;

        const fd = new FormData();
        fd.append("file", file);
        const t0 = performance.now();
        try {
            const res = await fetch("/api/analyze", { method: "POST", body: fd });
            if (!res.ok) throw new Error("HTTP " + res.status);
            const data = await res.json();
            const secs = ((performance.now() - t0) / 1000).toFixed(1);
            render(data, secs);
        } catch (err) {
            showSkeleton(false);
            setState("idle");
            llmEl.textContent =
                "分析失败：" + err.message + "\n请确认后端已启动（uvicorn artifact_scan.api:app）。";
            simList.innerHTML = "<li>—</li>";
            graphEl.textContent = "";
            serviceNote.hidden = false;
            serviceNote.textContent = "提示：后端需访问 Ollama / Milvus / Neo4j。";
        } finally {
            setState("idle");
        }
    }

    function setConclusion(p, c, conf) {
        conPeriod.textContent = p || "未知";
        conCulture.textContent = c || "未知";
        conConf.textContent = formatConf(conf);
    }

    // 置信度：0~1 转为百分比，其余原样展示
    function formatConf(v) {
        const n = parseFloat(v);
        if (isNaN(n)) return "—";
        if (n >= 0 && n <= 1) return (n * 100).toFixed(1) + "%";
        return String(n);
    }

    function render(data, secs) {
        data = data || {};
        const conclusion = data.conclusion || {};
        setConclusion(conclusion.period, conclusion.culture, conclusion.confidence);

        llmEl.innerHTML = formatAnalysis(data.llm_analysis);

        const similar = data.similar || [];
        simList.innerHTML = similar.length
            ? similar
                .map(
                    (s) =>
                        `<li><span>${esc(s.title || s.id)}</span><span class="sim-score">${Number(s.score).toFixed(3)}</span></li>`
                )
                .join("")
            : "<li>暂无相似文物</li>";

        const graph = data.graph || { nodes: [], edges: [] };
        graphEl.innerHTML = renderGraph(graph);

        const svc = data.services || {};
        const down = ["ollama", "milvus", "neo4j"].filter((k) => svc[k] === "down");
        if (down.length) {
            serviceNote.hidden = false;
            serviceNote.textContent = "部分服务不可用：" + down.join(", ") + "（结果可能不完整）";
        }

        // 显示内容 + 耗时（骨架屏 -> 内容）
        showSkeleton(false);
        elapsedEl.hidden = false;
        elapsedEl.textContent = "耗时 " + secs + " s";
    }

    // ---- 证据链图谱（SVG：待鉴定文物 → 相似文物 → 证据实体） ----
    const NODE_CLS = {
        artifact: "g-node-a",
        culture: "g-node-cul",
        period: "g-node-per",
        material: "g-node-mat",
        form: "g-node-frm",
        decoration: "g-node-dec"
    };
    const EDGE_CLS = {
        HAS_CULTURE: "g-e-culture",
        HAS_PERIOD: "g-e-period",
        HAS_MATERIAL: "g-e-material",
        HAS_FORM: "g-e-form",
        HAS_DECORATION: "g-e-decoration"
    };
    const LEGEND_TXT = {
        HAS_CULTURE: "文化",
        HAS_PERIOD: "时期",
        HAS_MATERIAL: "材料",
        HAS_FORM: "器型",
        HAS_DECORATION: "纹饰"
    };

    const MARKERS = `<defs>
    <marker id="m-HAS_CULTURE" viewBox="0 0 8 8" refX="6.5" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8 z" class="g-m-culture"/></marker>
    <marker id="m-HAS_PERIOD" viewBox="0 0 8 8" refX="6.5" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8 z" class="g-m-period"/></marker>
    <marker id="m-HAS_MATERIAL" viewBox="0 0 8 8" refX="6.5" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8 z" class="g-m-material"/></marker>
    <marker id="m-HAS_FORM" viewBox="0 0 8 8" refX="6.5" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8 z" class="g-m-form"/></marker>
    <marker id="m-HAS_DECORATION" viewBox="0 0 8 8" refX="6.5" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8 z" class="g-m-decoration"/></marker>
  </defs>`;

    function renderGraph(g) {
        const nodes = g.nodes || [];
        const edges = g.edges || [];
        const arts = nodes.filter((n) => n.type === "artifact").slice(0, 6);
        const entities = nodes.filter((n) => n.type !== "artifact").slice(0, 12);
        if (!arts.length) return '<p class="graph-empty">暂无图谱证据</p>';

        const W = 640,
            H = 470,
            cx = W / 2,
            cy = H / 2;
        const artNodes = arts.map((n, i) => {
            const ang = (i / arts.length) * Math.PI * 2 - Math.PI / 2;
            return { ...n, x: cx + Math.cos(ang) * 104, y: cy + Math.sin(ang) * 104 };
        });
        const entNodes = entities.map((n, i) => {
            const ang = (i / Math.max(entities.length, 1)) * Math.PI * 2 - Math.PI / 2;
            return { ...n, x: cx + Math.cos(ang) * 205, y: cy + Math.sin(ang) * 205 };
        });
        const pos = {};
        artNodes.forEach((n) => (pos[n.id] = n));
        entNodes.forEach((n) => (pos[n.id] = n));

        // 中心(待鉴定) → 相似文物 线索线
        let links = "";
        artNodes.forEach((n) => {
            links += `<line x1="${cx}" y1="${cy}" x2="${n.x}" y2="${n.y}" class="g-link"/>`;
        });
        // 相似文物 → 证据实体 弧形边
        let paths = "";
        const usedTypes = new Set();
        edges.forEach((e) => {
            const s = pos[e.source];
            const t = pos[e.target];
            if (!s || !t) return;
            usedTypes.add(e.type);
            const mx = (s.x + t.x) / 2,
                my = (s.y + t.y) / 2;
            const px = -(t.y - s.y),
                py = t.x - s.x;
            const pl = Math.hypot(px, py) || 1;
            const off = 16;
            const qx = mx + (px / pl) * off,
                qy = my + (py / pl) * off;
            paths += `<path d="M ${s.x} ${s.y} Q ${qx} ${qy} ${t.x} ${t.y}" class="${EDGE_CLS[e.type] || "g-e-other"}" marker-end="url(#m-${e.type || "other"})"/>`;
        });

        const artEls = artNodes.map((n) => nodeEl(n)).join("");
        const entEls = entNodes.map((n) => nodeEl(n)).join("");
        const center = `<rect x="${cx - 52}" y="${cy - 26}" width="104" height="52" rx="10" class="g-node-q"/><text x="${cx}" y="${cy + 5}" text-anchor="middle" font-size="14" class="g-node-q-t">待鉴定文物</text>`;

        // 图例（按实际出现的边类型）
        let legend =
            '<span><i class="lg-dot lg-q"></i>待鉴定</span><span><i class="lg-dot lg-a"></i>相似文物</span>';
        Object.keys(LEGEND_TXT).forEach((t) => {
            if (usedTypes.has(t)) {
                legend += `<span><i class="lg-line lg-${t.slice(4).toLowerCase()}"></i>${LEGEND_TXT[t]}</span>`;
            }
        });

        return `<div class="graph-wrap"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="证据链图谱">${MARKERS}<g>${links}${paths}</g><g>${artEls}${entEls}</g><g>${center}</g></svg><div class="graph-legend">${legend}</div></div>`;
    }

    function nodeEl(n) {
        const cls = NODE_CLS[n.type] || "g-node-a";
        const label = n.type === "artifact" ? labelOf(n, 6) : labelOf(n, 8);
        const tip = esc(n.label || n.id || "");
        if (n.type === "artifact") {
            return `<g class="${cls}"><title>${tip}</title><circle cx="${n.x}" cy="${n.y}" r="21"/><text x="${n.x}" y="${n.y + 47}" text-anchor="middle" font-size="11.5" class="g-node-lbl">${esc(label)}</text></g>`;
        }
        const w = Math.min(Math.max(label.length * 13.5 + 18, 52), 104);
        return `<g class="${cls}"><title>${tip}</title><rect x="${n.x - w / 2}" y="${n.y - 14}" width="${w}" height="28" rx="7"/><text x="${n.x}" y="${n.y + 4.5}" text-anchor="middle" font-size="11.5" class="g-node-lbl">${esc(label)}</text></g>`;
    }

    function labelOf(n, max) {
        let s = n.label || n.id || "";
        return s.length > max ? s.slice(0, max) + "…" : s;
    }

    // ---- LLM 文本展示：报告文本原样渲染（【标题】行高亮），JSON 兜底格式化 ----
    function formatAnalysis(text) {
        let t = String(text || "").trim();
        if (!t) return "（模型未返回文本分析）";
        // 去除 markdown 代码围栏标记（保留内部内容）
        if (t.startsWith("```")) {
            t = t.replace(/^```[a-zA-Z]*\s*/, "").replace(/\s*```$/, "").trim();
        }
        if (t.startsWith("{") && t.endsWith("}")) {
            try {
                const obj = JSON.parse(t);
                for (const k of ["description", "analysis", "reasoning", "summary", "text"]) {
                    if (obj[k] && typeof obj[k] === "string") return esc(obj[k]);
                }
                const items = Object.entries(obj)
                    .map(
                        ([k, v]) =>
                            `<div class="kv"><span class="kv-k">${esc(k)}</span><span class="kv-v">${esc(v)}</span></div>`
                    )
                    .join("");
                return items || esc(t);
            } catch (e) {
                /* 非严格 JSON，回退原样展示 */
            }
        }
        return t
            .split("\n")
            .map(fmtReportLine)
            .join("<br>");
    }

    function fmtReportLine(line) {
        const raw = String(line).trimEnd();
        if (!raw.trim()) return "&nbsp;";
        // markdown 标题行（### 等）
        if (/^#{1,4}\s+/.test(raw)) {
            return `<span class="rp-h">${esc(raw.replace(/^#{1,4}\s+/, "").trim())}</span>`;
        }
        // 中文序号标题行（一、二、三…）
        if (/^[一二三四五六七八九十]+[、.．]/.test(raw.trim())) {
            return `<span class="rp-h">${esc(raw.trim())}</span>`;
        }
        // **加粗** 与 【小标题】
        let s = esc(raw);
        s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
        s = s.replace(/(【[^】]+】)/g, '<strong class="rp-tag">$1</strong>');
        return s;
    }

    function esc(s) {
        return String(s).replace(/[&<>"']/g, (c) =>
            ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
        );
    }

    // ---- 服务状态 ----
    statusBtn.addEventListener("click", async () => {
        statusBtn.textContent = "检测中…";
        statusBtn.className = "pill";
        try {
            const r = await fetch("/api/health");
            const d = await r.json();
            const svc = d.services || {};
            const upCount = Object.values(svc).filter((v) => v === "up").length;
            const total = Object.keys(svc).length;
            statusBtn.textContent = `服务 ${upCount}/${total}`;
            statusBtn.className = "pill " + (upCount === total ? "up" : "down");
        } catch (e) {
            statusBtn.textContent = "服务不可达";
            statusBtn.className = "pill down";
        }
    });
})();
