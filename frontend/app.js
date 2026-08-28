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
        const fastEl = document.getElementById("fastToggle");
        const fast = fastEl ? fastEl.checked : false;
        const t0 = performance.now();
        try {
            const res = await fetch("/api/analyze" + (fast ? "?fast=1" : ""), { method: "POST", body: fd });
            if (!res.ok) throw new Error("HTTP " + res.status);
            const data = await res.json();
            const secs = ((performance.now() - t0) / 1000).toFixed(1);
            render(data, secs);
        } catch (err) {
            showSkeleton(false);
            setState("idle");
            llmEl.textContent =
                "分析失败：" + err.message + "\n请确认后端已启动（uvicorn artifact_scan.api:app）。";
            const gGal = document.getElementById("simGallery");
            if (gGal) gGal.innerHTML = '<p class="sim-empty">—</p>';
            const gGr = document.getElementById("graph");
            if (gGr) gGr.innerHTML = "";
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
        renderGallery(similar);

        const graph = data.graph || { nodes: [], edges: [] };
        const gEl = document.getElementById("graph");
        if (gEl) {
            gEl.innerHTML = renderGraph(graph);
            bindGraph(gEl);
        }
        renderTimeline(data);

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

    let graphModel = null; // 交互图模型：{ pos:{id:{x,y,type,label}}, edges:[{s,t,type}], center }

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
            // 随机排布：基础圆环 + 角度/半径抖动，打破规整感（坐标夹取在画布内）
            const jitter = (v, range) => v + (Math.random() - 0.5) * 2 * range;
            const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
            const ang = (i / arts.length) * Math.PI * 2 - Math.PI / 2 + (Math.random() - 0.5) * 0.35;
            const r = 96 + (Math.random() - 0.5) * 40;
            return { ...n, x: clamp(jitter(cx + Math.cos(ang) * r, 18), 46, W - 46), y: clamp(jitter(cy + Math.sin(ang) * r, 18), 58, H - 46) };
        });
        const entNodes = entities.map((n, i) => {
            const jitter = (v, range) => v + (Math.random() - 0.5) * 2 * range;
            const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
            const ang = (i / Math.max(entities.length, 1)) * Math.PI * 2 - Math.PI / 2 + (Math.random() - 0.5) * 0.5;
            const r = 178 + (Math.random() - 0.5) * 70;
            return { ...n, x: clamp(jitter(cx + Math.cos(ang) * r, 20), 52, W - 52), y: clamp(jitter(cy + Math.sin(ang) * r, 20), 60, H - 46) };
        });

        // 碰撞避免：轻微推开重叠节点（中心节点固定），保持有机散布且不相交
        const halfW = {};
        artNodes.forEach((n) => (halfW[n.id] = 28)); // 相似文物圆点
        entNodes.forEach((n) => {
            const w = Math.min(Math.max(String(n.label || n.id || "").length * 13.5 + 18, 52), 104);
            halfW[n.id] = w / 2 + 4;
        });
        const centerFix = { x: cx, y: cy, half: 58 };
        const allNodes = [...artNodes, ...entNodes];
        for (let iter = 0; iter < 26; iter++) {
            let moved = false;
            for (let i = 0; i < allNodes.length; i++) {
                for (let j = i + 1; j < allNodes.length; j++) {
                    const a = allNodes[i],
                        b = allNodes[j];
                    const dx = b.x - a.x,
                        dy = b.y - a.y;
                    const minDist = halfW[a.id] + halfW[b.id] + 4;
                    let d = Math.hypot(dx, dy);
                    if (d < 1) {
                        a.x -= 3;
                        b.x += 3;
                        moved = true;
                        continue;
                    }
                    if (d < minDist) {
                        const push = (minDist - d) / 2;
                        a.x -= (dx / d) * push;
                        a.y -= (dy / d) * push;
                        b.x += (dx / d) * push;
                        b.y += (dy / d) * push;
                        moved = true;
                    }
                }
                // 与中心节点保持距离
                const node = allNodes[i];
                const cdx = node.x - centerFix.x,
                    cdy = node.y - centerFix.y;
                const cd = Math.hypot(cdx, cdy);
                const cmin = halfW[node.id] + centerFix.half;
                if (cd > 0 && cd < cmin) {
                    node.x += (cdx / cd) * (cmin - cd);
                    node.y += (cdy / cd) * (cmin - cd);
                    moved = true;
                }
            }
            if (!moved) break;
        }
        allNodes.forEach((n) => {
            n.x = Math.max(46, Math.min(W - 46, n.x));
            n.y = Math.max(58, Math.min(H - 46, n.y));
        });

        const pos = {};
        artNodes.forEach((n) => (pos[n.id] = n));
        entNodes.forEach((n) => (pos[n.id] = n));

        // 中心(待鉴定) → 相似文物 线索线
        let links = "";
        artNodes.forEach((n) => {
            links += `<line x1="${cx}" y1="${cy}" x2="${n.x}" y2="${n.y}" class="g-link" data-s="__center__" data-t="${n.id}"/>`;
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
            paths += `<path d="M ${s.x} ${s.y} Q ${qx} ${qy} ${t.x} ${t.y}" class="g-edge ${EDGE_CLS[e.type] || "g-e-other"}" data-s="${e.source}" data-t="${e.target}" marker-end="url(#m-${e.type || "other"})"/>`;
        });

        const artEls = artNodes.map((n) => nodeEl(n)).join("");
        const entEls = entNodes.map((n) => nodeEl(n)).join("");
        const center = `<g class="g-node-q g-node" data-id="__center__" data-label="待鉴定文物"><title>待鉴定文物</title><rect x="${cx - 52}" y="${cy - 26}" width="104" height="52" rx="10"/><text x="${cx}" y="${cy + 5}" text-anchor="middle" font-size="14" class="g-node-q-t">待鉴定文物</text></g>`;

        // 图例（按实际出现的边类型）
        let legend =
            '<span><i class="lg-dot lg-q"></i>待鉴定</span><span><i class="lg-dot lg-a"></i>相似文物</span>';
        Object.keys(LEGEND_TXT).forEach((t) => {
            if (usedTypes.has(t)) {
                legend += `<span><i class="lg-line lg-${t.slice(4).toLowerCase()}"></i>${LEGEND_TXT[t]}</span>`;
            }
        });

        graphModel = {
            pos,
            edges: edges.map((e) => ({ s: String(e.source), t: String(e.target), type: e.type })),
            center: { x: cx, y: cy },
        };

        return `<div class="graph-wrap"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="证据链图谱">${MARKERS}<g id="graphMain">${links}${paths}${artEls}${entEls}${center}</g></svg><div class="graph-legend">${legend}</div></div>`;
    }

    function nodeEl(n) {
        const cls = NODE_CLS[n.type] || "g-node-a";
        const label = n.type === "artifact" ? labelOf(n, 6) : labelOf(n, 8);
        const tip = esc(n.label || n.id || "");
        if (n.type === "artifact") {
            return `<g class="${cls} g-node" data-id="${n.id}" data-label="${tip}"><title>${tip}</title><circle cx="${n.x}" cy="${n.y}" r="21"/><text x="${n.x}" y="${n.y + 47}" text-anchor="middle" font-size="11.5" class="g-node-lbl">${esc(label)}</text></g>`;
        }
        const w = Math.min(Math.max(label.length * 13.5 + 18, 52), 104);
        return `<g class="${cls} g-node" data-id="${n.id}" data-label="${tip}"><title>${tip}</title><rect x="${n.x - w / 2}" y="${n.y - 14}" width="${w}" height="28" rx="7"/><text x="${n.x}" y="${n.y + 4.5}" text-anchor="middle" font-size="11.5" class="g-node-lbl">${esc(label)}</text></g>`;
    }

    // ---- 证据链图谱（静态；仅悬停高亮 + 提示） ----
    function bindGraph(container) {
        const svg = container.querySelector("svg");
        if (!svg) return;
        const main = svg.querySelector("#graphMain");
        if (!main) return;

        let tip = document.getElementById("graphTip");
        if (!tip) {
            tip = document.createElement("div");
            tip.id = "graphTip";
            document.body.appendChild(tip);
        }
        const showTip = (x, y, text) => {
            if (!text) return;
            tip.textContent = text;
            tip.style.left = x + 14 + "px";
            tip.style.top = y + 14 + "px";
            tip.classList.add("on");
        };
        const hideTip = () => tip.classList.remove("on");

        function highlight(id) {
            const conn = new Set([id]);
            graphModel.edges.forEach((e) => {
                if (e.s === id) conn.add(e.t);
                if (e.t === id) conn.add(e.s);
            });
            main.querySelectorAll(".g-edge").forEach((p) => {
                const s = p.getAttribute("data-s"),
                    t = p.getAttribute("data-t");
                p.classList.toggle("g-e-dim", !(s === id || t === id));
            });
            main.querySelectorAll(".g-link").forEach((l) => {
                l.classList.toggle("g-e-dim", l.getAttribute("data-t") !== id);
            });
            main.querySelectorAll(".g-node").forEach((n) => {
                const nid = n.getAttribute("data-id");
                n.classList.toggle("g-node-dim", nid !== id && !conn.has(nid));
            });
        }
        function clearHighlight() {
            main.querySelectorAll(".g-edge").forEach((p) => p.classList.remove("g-e-dim"));
            main.querySelectorAll(".g-link").forEach((l) => l.classList.remove("g-e-dim"));
            main.querySelectorAll(".g-node").forEach((n) => n.classList.remove("g-node-dim"));
        }

        // 仅悬停高亮 + 提示；图谱固定，禁止拖拽/平移/缩放
        svg.addEventListener("mousemove", (e) => {
            const target = e.target.closest ? e.target.closest(".g-node") : null;
            if (target && target.getAttribute("data-id") !== "__center__") {
                highlight(target.getAttribute("data-id"));
                showTip(e.clientX, e.clientY, target.getAttribute("data-label") || "");
            } else {
                clearHighlight();
                hideTip();
            }
        });
    }

    // ---- 6.3 相似文物画廊 + 详情弹窗 ----
    function renderGallery(sims) {
        const g = document.getElementById("simGallery");
        if (!g) return;
        if (!sims.length) {
            g.innerHTML = '<p class="sim-empty">暂无相似文物</p>';
            return;
        }
        g.innerHTML = sims
            .map((s) => {
                const t = s.title || s.id || "";
                const thumb = s.image_url
                    ? `<img loading="lazy" src="${esc(s.image_url)}" alt="${esc(t)}" onerror="this.style.display='none';this.nextElementSibling.style.display='flex';"><span class="sim-fallback" style="display:none">${esc(t.slice(0, 12))}</span>`
                    : `<span class="sim-fallback" style="display:flex">${esc(t.slice(0, 12))}</span>`;
                return `<div class="sim-card" data-id="${esc(s.id)}">
              <div class="sim-thumb">${thumb}<span class="sim-score">${Number(s.score).toFixed(3)}</span></div>
              <div class="sim-meta">
                <div class="sim-title">${esc(t)}</div>
                <div class="sim-src">${esc(s.source || "")}</div>
              </div>
            </div>`;
            })
            .join("");

        g.querySelectorAll(".sim-card").forEach((card) => {
            card.addEventListener("click", () => {
                const id = card.getAttribute("data-id");
                const item = sims.find((x) => String(x.id) === id);
                if (item) openDetail(item);
            });
        });
    }

    function openDetail(item) {
        const modal = document.getElementById("detailModal");
        if (!modal) return;
        const img = document.getElementById("detailImg");
        const title = document.getElementById("detailTitle");
        const meta = document.getElementById("detailMeta");
        const desc = document.getElementById("detailDesc");
        const url = document.getElementById("detailUrl");
        if (item.image_url) {
            img.src = item.image_url;
            img.hidden = false;
            img.onerror = () => (img.hidden = true);
        } else {
            img.hidden = true;
        }
        title.textContent = item.title || item.id || "";
        const rows = [];
        if (item.period) rows.push(`<span><b>时期</b> ${esc(item.period)}</span>`);
        if (item.culture) rows.push(`<span><b>文化</b> ${esc(item.culture)}</span>`);
        if (item.source) rows.push(`<span><b>来源</b> ${esc(item.source)}</span>`);
        if (item.score != null) rows.push(`<span><b>相似度</b> ${Number(item.score).toFixed(3)}</span>`);
        meta.innerHTML = rows.join("");
        desc.textContent = item.description || "（暂无馆藏描述）";
        if (item.url) {
            url.href = item.url;
            url.hidden = false;
        } else {
            url.hidden = true;
        }
        modal.hidden = false;
        document.body.style.overflow = "hidden";
    }

    function closeDetail() {
        const modal = document.getElementById("detailModal");
        if (modal) modal.hidden = true;
        document.body.style.overflow = "";
    }

    // ---- 6.6 时间轴 + 文化分布 ----
    const DYNASTY = [
        ["新石器", -4000], ["夏", -2070], ["商", -1600], ["西周", -1046], ["东周", -770],
        ["秦", -221], ["汉", -206], ["魏晋南北朝", 220], ["隋", 581], ["唐", 618],
        ["五代十国", 907], ["宋", 960], ["元", 1271], ["明", 1368], ["清", 1644],
        ["近代", 1840], ["现代", 1949]
    ];

    function yearOf(label) {
        if (label == null) return null;
        const s = String(label);
        for (const [name, y] of DYNASTY) {
            if (s.includes(name)) return y;
        }
        const m = s.match(/(-?\d{3,4})\s*年/);
        if (m) return parseInt(m[1], 10);
        return null;
    }

    function renderTimeline(data) {
        const t = document.getElementById("timeline");
        const cz = document.getElementById("cultureZone");
        if (!t) return;

        const points = [];
        if (data.conclusion && data.conclusion.period) {
            points.push({ label: data.conclusion.period, y: yearOf(data.conclusion.period), q: true });
        }
        (data.similar || []).slice(0, 10).forEach((s) => {
            if (s.period) points.push({ label: s.period, y: yearOf(s.period), q: false });
        });

        // 去重（保留首见）
        const seen = new Set();
        const uniq = points.filter((p) => {
            const k = (p.q ? "q" : "a") + p.label;
            if (seen.has(k)) return false;
            seen.add(k);
            return true;
        });

        const known = uniq.filter((p) => p.y != null);
        const unknown = uniq.filter((p) => p.y == null);

        if (!uniq.length) {
            t.innerHTML = '<p class="sim-empty">暂无时期信息</p>';
        } else {
            let html = '<div class="tl-track">';
            // 动态缩放跨度：按实际标签年份分布取 min/max，避免数据集中在固定区间造成堆叠
            if (known.length) {
                let ymin = Math.min(...known.map((p) => p.y));
                let ymax = Math.max(...known.map((p) => p.y));
                if (ymin === ymax) {
                    ymin -= 100;
                    ymax += 100;
                }
                const pad = Math.max(120, (ymax - ymin) * 0.12);
                ymin -= pad;
                ymax += pad;
                const span = ymax - ymin;
                known.forEach((p, idx) => {
                    const left = Math.max(2, Math.min(98, ((p.y - ymin) / span) * 100));
                    const below = idx % 2 === 1; // 上下交错，减少标签堆叠
                    html += `<span class="tl-dot ${p.q ? "query" : "art"}" style="left:${left}%" title="${esc(p.label)}"></span>`;
                    html += `<span class="tl-tag ${p.q ? "q" : ""}${below ? " below" : ""}" style="left:${left}%">${esc(p.label)}</span>`;
                });
            }
            // 未知时期统一归入右侧"未定"
            if (unknown.length) {
                html += `<span class="tl-dot unk" style="left:99%"></span>`;
                html += `<span class="tl-tag" style="left:99%">未定 × ${unknown.length}</span>`;
            }
            html += '</div>';
            html += '<div class="tl-legend"><span><i style="background:var(--seal)"></i>待鉴定文物</span><span><i style="background:var(--bronze)"></i>相似文物</span>';
            if (unknown.length) {
                html += '<span><i style="background:var(--ink-3)"></i>未定时期</span>';
            }
            html += '</div>';
            t.innerHTML = html;
        }

        // 文化分布
        const graph = data.graph || {};
        const ents = (graph.nodes || []).filter((n) => n.type !== "artifact");
        if (ents.length) {
            cz.innerHTML = ents.slice(0, 16)
                .map((n) => `<span class="chip ${esc(n.type)}">${esc(n.label)}</span>`)
                .join("");
        } else {
            cz.innerHTML = '<p class="sim-empty">暂无文化要素</p>';
        }
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

    // ---- 详情弹窗关闭 ----
    const modalClose = document.getElementById("modalClose");
    const modalBackdrop = document.getElementById("modalBackdrop");
    if (modalClose) modalClose.addEventListener("click", closeDetail);
    if (modalBackdrop) modalBackdrop.addEventListener("click", closeDetail);
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            const modal = document.getElementById("detailModal");
            if (modal && !modal.hidden) closeDetail();
        }
    });

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
