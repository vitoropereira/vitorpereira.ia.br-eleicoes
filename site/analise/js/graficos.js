// Gráficos da Análise em SVG feito à mão (+ canvas para a dispersão de ~5.570 municípios).
// Cor de dado só por token de campo (var(--lula), var(--flavio), var(--outros)); nenhuma cor literal aqui.
import { html, useState, useEffect, useRef } from "/vendor/preact-htm.module.js";
import { escala, marcas, teto, pct, LADO_TOKEN } from "./calc.js";
import { token, limparCache } from "/hud/partidos.js";

// ---------------- dica (uma só na página; leve, sem re-render da página a cada movimento)
const subs = new Set();
let atual = null;
export const mostrarDica = (x, y, conteudo) => { atual = { x, y, conteudo }; subs.forEach((f) => f(atual)); };
export const esconderDica = () => { if (!atual) return; atual = null; subs.forEach((f) => f(null)); };

export function Dica() {
  const [d, setD] = useState(null);
  const ref = useRef();
  useEffect(() => { subs.add(setD); const esc = (e) => { if (e.key === "Escape") esconderDica(); }; addEventListener("keydown", esc); return () => { subs.delete(setD); removeEventListener("keydown", esc); }; }, []);
  useEffect(() => {
    const el = ref.current; if (!el || !d) return;
    const w = el.offsetWidth, h = el.offsetHeight;
    let x = d.x + 14, y = d.y + 14;
    if (x + w > innerWidth - 8) x = d.x - w - 14;
    if (y + h > innerHeight - 8) y = d.y - h - 14;
    el.style.transform = `translate(${Math.max(8, x)}px,${Math.max(8, y)}px)`;
  });
  if (!d) return null;
  return html`<div class="dica" ref=${ref} role="tooltip">${d.conteudo}</div>`;
}

/** props de uma marca interativa: hover, foco por teclado (Tab) e rótulo para leitor de tela */
export function marca(conteudo, rotulo) {
  return {
    tabIndex: 0, role: "img", "aria-label": rotulo, class: "mk",
    onMouseMove: (e) => mostrarDica(e.clientX, e.clientY, conteudo),
    onMouseLeave: esconderDica,
    onFocus: (e) => { const r = e.currentTarget.getBoundingClientRect(); mostrarDica(r.left + r.width / 2, r.top, conteudo); },
    onBlur: esconderDica,
  };
}

/** largura do contêiner (redesenha no resize); 640 antes de medir */
export function useLargura(inicial = 640) {
  const ref = useRef(); const [w, setW] = useState(inicial);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const f = () => { const x = Math.round(el.getBoundingClientRect().width); if (x > 0) setW(x); };
    f();
    const ro = new ResizeObserver(f); ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

const Dk = ({ t, linhas }) => html`<p class="dk-t">${t}</p>${linhas.map(([sw, a, b]) => html`<p class="dk-r">${sw && html`<i class="sw" style=${{ "--c": sw }}></i>`}<span>${a}</span><b>${b}</b></p>`)}`;
export { Dk };

// ---------------- barras empilhadas 100% (uma linha por categoria)
/** largura da coluna de rótulos: rotW fixo, ou "auto" = cabe o rótulo mais longo (12,5px; ~7px por caractere), até 45% */
export function larguraRot(rotW, rotulos, w) {
  if (rotW !== "auto") return rotW;
  const n = Math.max(0, ...rotulos.map((r) => String(r ?? "").length));
  return Math.min(Math.round(w * 0.45), Math.ceil(n * 7 + 18));
}

export function Empilhadas({ linhas, titulo, rotW = 128, bh = 26 }) {
  const [ref, w] = useLargura();
  const estreito = w < 520, lw = estreito ? 0 : larguraRot(rotW, linhas.map((l) => l.rotulo), w), gap = estreito ? 34 : 12;
  const x = escala([0, 1], [lw, w - 4]);
  const alt = linhas.length * (bh + gap) + (estreito ? 0 : 4) + 18;
  let y = estreito ? 18 : 4;
  return html`<div class="ch" ref=${ref}><svg width=${w} height=${alt} role="group" aria-label=${titulo}>
    ${linhas.map((l) => {
      const y0 = y; y += bh + gap; let acc = 0;
      return html`<g>
        <text class="rl" x=${estreito ? 0 : lw - 10} y=${estreito ? y0 - 6 : y0 + bh / 2 + 4} text-anchor=${estreito ? "start" : "end"}>${l.rotulo}${l.sub && html`<tspan class="sub"> ${l.sub}</tspan>`}</text>
        ${l.partes.map((p) => {
          const x0 = x(acc); acc += p.p; const ww = Math.max(0, x(acc) - x0);
          return html`<g ...${marca(p.dica, `${l.rotulo}: ${p.nome} ${pct(p.p)}`)}>
            <rect x=${x0} y=${y0} width=${ww} height=${bh} fill=${p.cor} rx="2" />
            ${ww > 44 && html`<text class="vl" x=${x0 + 6} y=${y0 + bh / 2 + 4}>${pct(p.p, 0)}</text>`}</g>`;
        })}</g>`;
    })}
    <line class="ref" x1=${x(0.5)} x2=${x(0.5)} y1="0" y2=${alt - 14} />
    <text class="ax" x=${x(0.5)} y=${alt - 2} text-anchor="middle">50%</text>
  </svg></div>`;
}

// ---------------- barras horizontais (com faixa de incerteza e marca opcional)
export function Barras({ itens, max, fmt: fmt0, fmtEixo, titulo, rotW = 150, eixo = true, bh = 18 }) {
  const fmt = fmt0 || ((v) => pct(v)), fe = fmtEixo || (fmt0 ? (v) => fmt0(v, true) : (v) => pct(v, 0));
  const [ref, w] = useLargura();
  const estreito = w < 520, lw = estreito ? 0 : larguraRot(rotW, itens.map((i) => i.rotulo), w), gap = estreito ? 30 : Math.round(bh * 0.55);
  const m = max ?? teto(Math.max(...itens.map((i) => Math.max(i.v || 0, i.int?.[1] || 0, i.marca?.v || 0)), 1e-9), 4);
  const vw = 64;
  const x = escala([0, m], [lw, w - vw]);
  const alt = itens.length * (bh + gap) + (estreito ? 16 : 0) + (eixo ? 20 : 4);
  let y = estreito ? 16 : 2;
  return html`<div class="ch" ref=${ref}><svg width=${w} height=${alt} role="group" aria-label=${titulo}>
    ${eixo && marcas(m, estreito ? 3 : 4).map((t) => html`<line class="gr" x1=${x(t)} x2=${x(t)} y1="0" y2=${alt - 18} /><text class="ax" x=${x(t)} y=${alt - 4} text-anchor="middle">${fe(t)}</text>`)}
    ${itens.map((it) => {
      const y0 = y; y += bh + gap;
      return html`<g ...${marca(it.dica, `${it.rotulo}: ${fmt(it.v)}${it.int ? `, faixa de ${fmt(it.int[0])} a ${fmt(it.int[1])}` : ""}`)}>
        <text class="rl" x=${estreito ? 0 : lw - 10} y=${estreito ? y0 - 5 : y0 + bh / 2 + 4} text-anchor=${estreito ? "start" : "end"}>${it.rotulo}</text>
        ${it.int && html`<rect class="faixa" x=${x(it.int[0])} y=${y0 - 4} width=${Math.max(2, x(it.int[1]) - x(it.int[0]))} height=${bh + 8} rx="3" />`}
        <rect x=${x(0)} y=${y0} width=${Math.max(1, x(it.v || 0) - x(0))} height=${bh} fill=${it.cor} rx="2" />
        ${it.int && html`<line class="ic" x1=${x(it.int[0])} x2=${x(it.int[1])} y1=${y0 + bh / 2} y2=${y0 + bh / 2} />`}
        ${it.marca && html`<line class="mq" x1=${x(it.marca.v)} x2=${x(it.marca.v)} y1=${y0 - 4} y2=${y0 + bh + 4} />`}
        <text class="vl2" x=${x(Math.max(it.v || 0, it.int?.[1] || 0)) + 6} y=${y0 + bh / 2 + 4}>${fmt(it.v)}</text></g>`;
    })}
  </svg></div>`;
}

// ---------------- halteres (dumbbell): de A (vazado) para B (cheio)
export function Halteres({ linhas, rotA, rotB, max = 1, fmt = (v) => pct(v), fmtEixo = (v) => pct(v, 0), titulo }) {
  const [ref, w] = useLargura();
  const estreito = w < 520, lw = estreito ? 0 : 150, rh = estreito ? 44 : 30;
  const m = max === "auto" ? teto(Math.max(...linhas.flatMap((l) => [l.a, l.b]), 1e-9), 4) : max;
  const x = escala([0, m], [lw + 8, w - 12]);
  const alt = linhas.length * rh + 46;
  return html`<div class="ch" ref=${ref}>
    <p class="leg-h"><span><i class="o"></i>${rotA}</span><span><i class="f"></i>${rotB}</span></p>
    <svg width=${w} height=${alt} role="group" aria-label=${titulo}>
    ${marcas(m, estreito ? 3 : 5).map((t) => html`<line class="gr" x1=${x(t)} x2=${x(t)} y1="0" y2=${alt - 20} /><text class="ax" x=${x(t)} y=${alt - 6} text-anchor="middle">${fmtEixo(t)}</text>`)}
    ${linhas.map((l, i) => {
      const yc = i * rh + (estreito ? 30 : rh / 2 + 4);
      return html`<g ...${marca(l.dica, `${l.rotulo}: ${rotA} ${fmt(l.a)}, ${rotB} ${fmt(l.b)}`)}>
        <text class="rl" x=${estreito ? 0 : lw - 6} y=${estreito ? yc - 12 : yc + 4} text-anchor=${estreito ? "start" : "end"}>${l.rotulo}</text>
        <line x1=${x(l.a)} x2=${x(l.b)} y1=${yc} y2=${yc} stroke=${l.cor} stroke-width="3" opacity=".55" />
        <circle cx=${x(l.a)} cy=${yc} r="6" fill="var(--card)" stroke=${l.cor} stroke-width="2.5" />
        <circle cx=${x(l.b)} cy=${yc} r="7" fill=${l.cor} /></g>`;
    })}
  </svg></div>`;
}

// ---------------- pequenos múltiplos: um mini gráfico por item, mesma escala
export function Pequenos({ itens, max, titulo }) {
  const m = max ?? teto(Math.max(...itens.map((i) => i.partes.reduce((s, p) => s + p.v, 0)), 1e-9), 4);
  return html`<ul class="pm" aria-label=${titulo}>${itens.map((it) => {
    let acc = 0; const tot = it.partes.reduce((s, p) => s + p.v, 0);
    return html`<li><p class="pm-t">${it.titulo}</p><p class="pm-n">${it.valor}</p>
      <svg viewBox="0 0 100 60" preserveAspectRatio="none" class="pm-g" ...${marca(it.dica, `${it.titulo}: ${it.valor}`)}>
        <rect x="0" y="0" width="100" height="60" fill="var(--soft)" />
        ${it.partes.map((p) => { const h = (p.v / m) * 60; acc += h; return html`<rect x="30" width="40" y=${60 - acc} height=${h} fill=${p.cor} />`; })}
        <line x1="0" x2="100" y1=${60 - (tot / m) * 60} y2=${60 - (tot / m) * 60} class="ref" vector-effect="non-scaling-stroke" />
      </svg></li>`;
  })}</ul>`;
}

// ---------------- dispersão em canvas: um ponto por município
// pts: {x: Float32Array, y: Float32Array, lado: string[] (L|F|C), nome(i), on: (i)=>bool destaque}
export function Dispersao({ pts, rotX, rotY, titulo, resumo, dica }) {
  const [ref, w] = useLargura();
  const cv = useRef(), grade = useRef(null);
  const h = Math.min(420, Math.max(280, Math.round(w * 0.62)));
  const pad = { l: 44, r: 10, t: 10, b: 36 };
  const x = escala([0, 1], [pad.l, w - pad.r]), y = escala([0, 1], [h - pad.b, pad.t]);
  const [tema, setTema] = useState(0);
  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: light)");
    const f = () => { limparCache(); setTema((t) => t + 1); };
    mq.addEventListener("change", f);
    const mo = new MutationObserver(f); // botão de tema (data-theme no <html>)
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => { mq.removeEventListener("change", f); mo.disconnect(); };
  }, []);
  useEffect(() => {
    const c = cv.current; if (!c || !pts) return;
    const dpr = devicePixelRatio || 1;
    c.width = w * dpr; c.height = h * dpr; c.style.width = w + "px"; c.style.height = h + "px";
    const ctx = c.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const rgb = (t, a) => { const v = token(t); return `rgba(${v[0]},${v[1]},${v[2]},${a})`; };
    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = rgb("--line", 1); ctx.fillStyle = rgb("--muted", 1); ctx.lineWidth = 1;
    ctx.font = "10px " + getComputedStyle(document.body).getPropertyValue("--font-mono");
    for (const t of [0, 0.25, 0.5, 0.75, 1]) {
      ctx.beginPath(); ctx.moveTo(x(t), y(0)); ctx.lineTo(x(t), y(1)); ctx.moveTo(x(0), y(t)); ctx.lineTo(x(1), y(t)); ctx.stroke();
      ctx.textAlign = "center"; ctx.fillText(pct(t, 0), x(t), h - pad.b + 14);
      ctx.textAlign = "right"; ctx.fillText(pct(t, 0), pad.l - 6, y(t) + 3);
    }
    ctx.strokeStyle = rgb("--ink2", 0.7); ctx.setLineDash([4, 4]); ctx.beginPath(); ctx.moveTo(x(0), y(0)); ctx.lineTo(x(1), y(1)); ctx.stroke(); ctx.setLineDash([]);
    const n = pts.x.length, temOn = !!pts.on;
    const r = w < 520 ? 1.6 : 2.1;
    for (const passo of temOn ? [0, 1] : [1]) {
      for (let i = 0; i < n; i++) {
        const on = !temOn || pts.on(i);
        if ((passo === 1) !== on) continue;
        ctx.fillStyle = on ? rgb(LADO_TOKEN[pts.lado[i]] || "--outros", 0.55) : rgb("--muted", 0.12);
        ctx.fillRect(x(pts.x[i]) - r, y(pts.y[i]) - r, r * 2, r * 2);
      }
    }
    // grade para achar o ponto sob o mouse
    const G = 40, g = new Map();
    for (let i = 0; i < n; i++) {
      if (temOn && !pts.on(i)) continue;
      const k = Math.floor(pts.x[i] * G) * 100 + Math.floor(pts.y[i] * G);
      (g.get(k) || g.set(k, []).get(k)).push(i);
    }
    grade.current = { g, G };
  }, [pts, w, h, tema]);
  const perto = (e) => {
    const b = cv.current.getBoundingClientRect(), mx = e.clientX - b.left, my = e.clientY - b.top;
    const gx = x.inv(mx), gy = y.inv(my), { g, G } = grade.current || {};
    if (!g) return -1;
    let best = -1, bd = 64;
    for (let a = -1; a <= 1; a++) for (let c = -1; c <= 1; c++) {
      for (const i of g.get((Math.floor(gx * G) + a) * 100 + Math.floor(gy * G) + c) || []) {
        const d = (x(pts.x[i]) - mx) ** 2 + (y(pts.y[i]) - my) ** 2;
        if (d < bd) { bd = d; best = i; }
      }
    }
    return best;
  };
  return html`<div class="ch disp" ref=${ref}>
    <canvas ref=${cv} tabindex="0" role="img" aria-label=${`${titulo}. ${resumo || ""}`}
      onMouseMove=${(e) => { const i = perto(e); if (i >= 0) mostrarDica(e.clientX, e.clientY, dica(i)); else esconderDica(); }}
      onMouseLeave=${esconderDica}></canvas>
    <p class="eixo-x">${rotX} →</p><p class="eixo-y">${rotY} →</p>
  </div>`;
}

// ---------------- legenda de campos
export const LegendaLados = ({ itens }) => html`<p class="leg-l">${itens.map(([cor, txt]) => html`<span><i class="sw" style=${{ "--c": cor }}></i>${txt}</span>`)}</p>`;

/** tabela de apoio (leitor de tela e buscadores: os números ficam no HTML) */
export const TabelaSR = ({ cap, cab, linhas }) => html`<table class="sr-only"><caption>${cap}</caption>
  <thead><tr>${cab.map((c) => html`<th scope="col">${c}</th>`)}</tr></thead>
  <tbody>${linhas.map((l) => html`<tr>${l.map((c, i) => (i ? html`<td>${c}</td>` : html`<th scope="row">${c}</th>`))}</tr>`)}</tbody></table>`;

