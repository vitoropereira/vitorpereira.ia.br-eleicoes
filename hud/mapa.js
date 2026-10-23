// Mapa em canvas: camada-base pré-desenhada (offscreen) + destaque por quadro + rótulos de UF em DOM.
// Arrastar/zoom só redesenha a imagem pronta (drawImage); a camada nítida do recorte é refeita quando o gesto para.
import { token } from "./partidos.js";

const reduzMovimento = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const CALLOUT_NE = ["RN", "PB", "PE", "AL", "SE"], CALLOUT_SE = ["ES", "RJ"];
const rgb = (c, a = 1) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;

export class Mapa {
  constructor(el, geo, cb = {}) {
    this.el = el; this.geo = geo; this.cb = cb;
    this.cv = document.createElement("canvas");
    this.cv.className = "mapa-cv";
    this.cv.tabIndex = 0;
    this.cv.setAttribute("role", "img");
    this.cv.setAttribute("aria-label", "Mapa do Brasil por município. Setas movem, + e − aproximam, 0 volta ao Brasil inteiro. A tabela por estado está logo abaixo para leitores de tela.");
    this.rot = document.createElement("div");
    this.rot.className = "rotulos";
    el.append(this.cv, this.rot);
    this.ctx = this.cv.getContext("2d");
    this.cores = null; this.rotulos = []; this.rotEls = new Map();
    this.hover = -1; this.sel = -1; this.ufSel = null;
    this.insets = { t: 0, r: 0, b: 0, l: 0 };
    this.W = 0; this.H = 0; this.k = 1; this.ox = 0; this.oy = 0; this.k0 = 1;
    this.mundo = null; this.vista = null; this.agendado = false; this.tVista = 0;
    this.ponteiros = new Map(); this.gesto = null;
    const [x0, y0, x1, y1] = geo.bbox;
    this.bw = x1 - x0; this.bh = y1 - y0;
    // resolução da camada-base: menor em aparelho fraco/celular
    const fraco = (navigator.deviceMemory && navigator.deviceMemory < 4) || Math.min(screen.width, screen.height) < 600;
    this.resMax = fraco ? 2048 : 3584;
    this._eventos();
    this.ro = new ResizeObserver(() => this._resize());
    this.ro.observe(el);
    this._resize();
  }

  // ---------- API
  /** troca a malha (UFs → municípios) sem perder o enquadramento do usuário */
  setGeo(geo) {
    const antes = { k: this.k, ox: this.ox, oy: this.oy, z: this.zoom };
    this.geo = geo;
    const [x0, y0, x1, y1] = geo.bbox;
    this.bw = x1 - x0; this.bh = y1 - y0;
    this.contornoUF = null; this.hover = -1; this.sel = -1; this.mundo = null; this.vista = null;
    this.ajustar(false);
    if (antes.z > 1.02) { this.k = antes.k; this.ox = antes.ox; this.oy = antes.oy; this._movido(); }
  }
  setCores(cores) { this.cores = cores; this.mundo = null; this.vista = null; this._pintarMundo(); this.pedir(); this._agendarVista(); }
  setInsets(i) { this.insets = i; this.ajustar(); }
  setRotulos(lista) {
    this.rotulos = lista;
    const vistos = new Set();
    for (const r of lista) {
      vistos.add(r.uf);
      let b = this.rotEls.get(r.uf);
      if (!b) {
        b = document.createElement("button");
        b.type = "button"; b.className = "uf-rot";
        this.rot.append(b); this.rotEls.set(r.uf, b);
      }
      b.style.setProperty("--c", r.cor);
      const n = document.createElement("b"); n.textContent = r.uf;
      const s = document.createElement("span"); s.textContent = r.txt || "";
      b.replaceChildren(n, ...(r.txt ? [s] : []));
      b.setAttribute("aria-label", r.aria || r.uf);
      b.onclick = (e) => { e.stopPropagation(); this.cb.onUF?.(r.uf); };
    }
    for (const [uf, b] of this.rotEls) if (!vistos.has(uf)) { b.remove(); this.rotEls.delete(uf); }
    this.pedir();
  }
  setSelecao(i) { this.sel = i; this.pedir(); }
  setUF(uf) { this.ufSel = uf; this.pedir(); }
  setHover(i) { if (i !== this.hover) { this.hover = i; this.pedir(); } }
  get zoom() { return this.k / this.k0; }

  ajustar(animar = false) {
    const { t, r, b, l } = this.insets;
    const aw = Math.max(50, this.W - l - r), ah = Math.max(50, this.H - t - b);
    const k = Math.min(aw / this.bw, ah / this.bh) * 0.96;
    this.k0 = k;
    const [x0, y0] = this.geo.bbox;
    const alvo = { k, ox: l + (aw - this.bw * k) / 2 - x0 * k, oy: t + (ah - this.bh * k) / 2 - y0 * k };
    this._ir(alvo, animar);
  }

  /** aproxima numa caixa [x0,y0,x1,y1] do mundo */
  enquadrar(bb, animar = true, folga = 1.25) {
    const { t, r, b, l } = this.insets;
    const aw = Math.max(50, this.W - l - r), ah = Math.max(50, this.H - t - b);
    const w = Math.max(bb[2] - bb[0], 0.05), h = Math.max(bb[3] - bb[1], 0.05);
    let k = Math.min(aw / (w * folga), ah / (h * folga));
    k = Math.min(Math.max(k, this.k0), this.k0 * 80);
    const cx = (bb[0] + bb[2]) / 2, cy = (bb[1] + bb[3]) / 2;
    this._ir({ k, ox: l + aw / 2 - cx * k, oy: t + ah / 2 - cy * k }, animar);
  }
  enquadrarUF(uf) { const u = this.geo.ufs[uf]; if (u) this.enquadrar(u.bbox); }
  enquadrarMun(i) { const m = this.geo.muns[i]; if (m) this.enquadrar(m.bbox, true, 6); }

  zoomEm(sx, sy, f) {
    const k = Math.min(Math.max(this.k * f, this.k0 * 0.8), this.k0 * 80);
    const wx = (sx - this.ox) / this.k, wy = (sy - this.oy) / this.k;
    this.k = k; this.ox = sx - wx * k; this.oy = sy - wy * k;
    this._movido();
  }
  zoomCentro(f) {
    const { t, r, b, l } = this.insets;
    this.zoomEm(l + (this.W - l - r) / 2, t + (this.H - t - b) / 2, f);
  }

  // ---------- desenho
  pedir() {
    if (this.agendado) return;
    this.agendado = true;
    requestAnimationFrame(() => { this.agendado = false; this._quadro(); });
  }

  _pintar(ctx, idx, px) {
    // px = pixels de tela por unidade do mundo
    const grupos = new Map();
    const vazio = rgb(token("--g0"));
    for (const i of idx) {
      const c = (this.cores && this.cores[i]) || vazio;
      let g = grupos.get(c); if (!g) grupos.set(c, (g = [])); g.push(i);
    }
    const muns = this.geo.muns;
    if (this.geo.fundo) { // modo Pessoas: o contorno dos estados fica por baixo dos círculos
      ctx.lineJoin = "round";
      ctx.fillStyle = rgb(token("--muted"), 0.12);
      ctx.strokeStyle = rgb(token("--muted"), 0.35);
      ctx.lineWidth = 0.8 / px;
      ctx.stroke(this.geo.fundo);
    }
    for (const [c, g] of grupos) {
      ctx.fillStyle = c;
      for (const i of g) ctx.fill(muns[i].path, "evenodd");
    }
    const bg = token("--bg");
    ctx.lineJoin = "round";
    if (px > 30) { // bordas de município só quando há espaço para elas
      ctx.strokeStyle = rgb(bg, Math.min(0.55, 0.15 + px / 400));
      ctx.lineWidth = 0.6 / px;
      ctx.stroke(this.geo.bordasMun);
    }
    ctx.strokeStyle = rgb(bg, 0.95);
    ctx.lineWidth = Math.min(2.2, 0.9 + px / 200) / px;
    ctx.stroke(this.geo.bordasUF);
  }

  _pintarMundo() {
    const r = this.resMax / Math.max(this.bw, this.bh);
    const w = Math.ceil(this.bw * r), h = Math.ceil(this.bh * r);
    const c = this.mundo?.cv || document.createElement("canvas");
    c.width = w; c.height = h;
    const ctx = c.getContext("2d");
    ctx.setTransform(r, 0, 0, r, -this.geo.bbox[0] * r, -this.geo.bbox[1] * r);
    const t0 = performance.now();
    this._pintar(ctx, this.geo.muns.map((_, i) => i), r);
    this.mundo = { cv: c, r };
    this.mediu = performance.now() - t0;
  }

  _agendarVista() {
    clearTimeout(this.tVista);
    this.tVista = setTimeout(() => this._pintarVista(), 140);
  }

  _pintarVista() {
    const dpr = this.dpr;
    if (!this.mundo || this.k * dpr <= this.mundo.r * 1.05) { this.vista = null; return; } // a base já é nítida
    const c = this.vista?.cv || document.createElement("canvas");
    c.width = this.cv.width; c.height = this.cv.height;
    const ctx = c.getContext("2d");
    ctx.setTransform(this.k * dpr, 0, 0, this.k * dpr, this.ox * dpr, this.oy * dpr);
    const x0 = -this.ox / this.k, y0 = -this.oy / this.k, x1 = (this.W - this.ox) / this.k, y1 = (this.H - this.oy) / this.k;
    this._pintar(ctx, this.geo.visiveis(x0, y0, x1, y1), this.k * dpr);
    this.vista = { cv: c, k: this.k, ox: this.ox, oy: this.oy };
    this.pedir();
  }

  _quadro() {
    const t0 = performance.now();
    const ctx = this.ctx, dpr = this.dpr;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, this.cv.width, this.cv.height);
    if (!this.mundo) return;
    const v = this.vista;
    if (v && v.k === this.k && v.ox === this.ox && v.oy === this.oy) ctx.drawImage(v.cv, 0, 0);
    else {
      const [x0, y0] = this.geo.bbox, s = this.k * dpr;
      ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = "medium";
      ctx.drawImage(this.mundo.cv, (x0 * this.k + this.ox) * dpr, (y0 * this.k + this.oy) * dpr, this.bw * s, this.bh * s);
    }
    ctx.setTransform(this.k * dpr, 0, 0, this.k * dpr, this.ox * dpr, this.oy * dpr);
    ctx.lineJoin = "round";
    const ink = token("--ink");
    if (this.ufSel && this.geo.ufs[this.ufSel]) {
      if (!this.contornoUF || this.contornoUF.uf !== this.ufSel) {
        const p = new Path2D();
        for (const i of this.geo.ufs[this.ufSel].lista) p.addPath(this.geo.muns[i].path);
        this.contornoUF = { uf: this.ufSel, p };
      }
      ctx.strokeStyle = rgb(ink, 0.55); ctx.lineWidth = 0.8 / this.k;
      ctx.stroke(this.contornoUF.p);
    }
    if (this.hover >= 0 && this.hover !== this.sel) {
      ctx.strokeStyle = rgb(ink, 0.85); ctx.lineWidth = 1.5 / this.k;
      ctx.stroke(this.geo.muns[this.hover].path);
    }
    if (this.sel >= 0) {
      ctx.strokeStyle = rgb(token("--bg"), 0.9); ctx.lineWidth = 4 / this.k; ctx.stroke(this.geo.muns[this.sel].path);
      ctx.strokeStyle = rgb(ink); ctx.lineWidth = 2 / this.k; ctx.stroke(this.geo.muns[this.sel].path);
    }
    this._posicionarRotulos(ctx);
    this.ultimoQuadro = performance.now() - t0;
  }

  _posicionarRotulos(ctx) {
    const z = this.zoom, pos = new Map();
    const tela = (x, y) => [x * this.k + this.ox, y * this.k + this.oy];
    for (const r of this.rotulos) {
      const u = this.geo.ufs[r.uf]; if (!u) continue;
      pos.set(r.uf, { a: tela(u.cx, u.cy), p: tela(u.cx, u.cy), lado: false });
    }
    if (pos.has("GO") && pos.has("DF")) { const g = pos.get("GO"); g.p = [g.p[0] - 6, g.p[1] + 16]; }
    if (z < 2.4) {
      const grupo = (lista, xRef) => {
        const its = lista.filter((u) => pos.has(u)).map((u) => pos.get(u)).sort((a, b) => a.a[1] - b.a[1]);
        let ult = -Infinity;
        for (const it of its) {
          it.lado = true;
          const y = Math.max(it.a[1], ult + 26);
          it.p = [xRef, y]; ult = y;
        }
      };
      const leste = this.geo.bbox[2] * this.k + this.ox;
      const cabe = (x) => x + 56 < this.W - this.insets.r + 8; // rótulo "RN 60%" ~56px
      const esconder = (lista) => lista.forEach((u) => { if (pos.has(u)) pos.get(u).oculto = true; });
      if (cabe(leste + 12)) grupo(CALLOUT_NE, leste + 12); else esconder(CALLOUT_NE);
      const es = this.geo.ufs.ES;
      const xse = es ? Math.max(es.bbox[2], this.geo.ufs.RJ?.bbox[2] || 0) * this.k + this.ox + 34 : 0;
      if (es && cabe(xse)) grupo(CALLOUT_SE, xse); else esconder(CALLOUT_SE);
    }
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.strokeStyle = rgb(token("--muted"), 0.7); ctx.lineWidth = 1;
    ctx.beginPath();
    for (const it of pos.values()) if (it.lado) { ctx.moveTo(it.a[0], it.a[1]); ctx.lineTo(it.p[0], it.p[1]); }
    ctx.stroke();
    const mostrar = z < 7;
    for (const [uf, b] of this.rotEls) {
      const it = pos.get(uf);
      if (!it || !mostrar || it.oculto) { b.hidden = true; continue; }
      b.hidden = false;
      b.style.transform = `translate(${Math.round(it.p[0])}px,${Math.round(it.p[1])}px) translate(${it.lado ? "0" : "-50%"},-50%)`;
      b.classList.toggle("ativo", uf === this.ufSel);
    }
  }

  // ---------- tamanho, transformação
  _resize() {
    const r = this.el.getBoundingClientRect();
    const W = Math.round(r.width), H = Math.round(r.height);
    if (!W || !H || (W === this.W && H === this.H)) return;
    this.W = W; this.H = H;
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.cv.width = W * this.dpr; this.cv.height = H * this.dpr;
    this.cv.style.width = W + "px"; this.cv.style.height = H + "px";
    this.vista = null;
    this.ajustar(false);
  }

  _ir(alvo, animar) {
    cancelAnimationFrame(this.anim);
    if (!animar || reduzMovimento() || !this.W) {
      Object.assign(this, alvo); this._movido(); return;
    }
    const de = { k: this.k, ox: this.ox, oy: this.oy }, t0 = performance.now(), D = 380;
    // interpola em espaço do mundo: centro e escala (log) para não "derrapar"
    const cx = (s) => ((this.W / 2 - s.ox) / s.k), cy = (s) => ((this.H / 2 - s.oy) / s.k);
    const a = { x: cx(de), y: cy(de), k: Math.log(de.k) }, b = { x: cx(alvo), y: cy(alvo), k: Math.log(alvo.k) };
    const passo = (t) => {
      const p = Math.min(1, (t - t0) / D), e = 1 - Math.pow(1 - p, 3);
      const k = Math.exp(a.k + (b.k - a.k) * e), x = a.x + (b.x - a.x) * e, y = a.y + (b.y - a.y) * e;
      this.k = k; this.ox = this.W / 2 - x * k; this.oy = this.H / 2 - y * k;
      if (p >= 1) Object.assign(this, alvo);
      this._movido();
      if (p < 1) this.anim = requestAnimationFrame(passo);
    };
    this.anim = requestAnimationFrame(passo);
  }

  _movido() {
    this.cv.style.touchAction = this.zoom > 1.02 ? "none" : "pan-y";
    this.pedir();
    this._agendarVista();
    this.cb.onZoom?.(this.zoom);
  }

  // ---------- eventos
  _ponto(e) { const r = this.cv.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; }
  _mundo(sx, sy) { return [(sx - this.ox) / this.k, (sy - this.oy) / this.k]; }
  hitTela(sx, sy) { const [x, y] = this._mundo(sx, sy); return this.geo.hit(x, y); }

  _eventos() {
    const cv = this.cv;
    cv.style.touchAction = "pan-y";
    cv.addEventListener("pointerdown", (e) => {
      cv.setPointerCapture(e.pointerId);
      this.ponteiros.set(e.pointerId, this._ponto(e));
      if (this.ponteiros.size === 1) this.gesto = { ini: this._ponto(e), t: performance.now(), moveu: false };
      else this.gesto = { ...this.gesto, moveu: true, pinca: this._pinca() };
    });
    cv.addEventListener("pointermove", (e) => {
      const p = this._ponto(e);
      if (!this.ponteiros.has(e.pointerId)) { // passando o mouse
        if (e.pointerType === "mouse") this._hoverEm(p, e);
        return;
      }
      const ant = this.ponteiros.get(e.pointerId);
      this.ponteiros.set(e.pointerId, p);
      if (this.ponteiros.size >= 2 && this.gesto?.pinca) {
        const n = this._pinca(), a = this.gesto.pinca;
        const f = n.d / a.d;
        this.zoomEm(n.c[0], n.c[1], f);
        this.ox += n.c[0] - a.c[0]; this.oy += n.c[1] - a.c[1];
        this.gesto.pinca = n; this._movido();
        return;
      }
      const g = this.gesto; if (!g) return;
      if (!g.moveu && Math.hypot(p[0] - g.ini[0], p[1] - g.ini[1]) < 5) return;
      if (!g.moveu && e.pointerType !== "mouse" && this.zoom <= 1.02) return; // no celular, sem zoom: deixa a página rolar
      g.moveu = true;
      this.ox += p[0] - ant[0]; this.oy += p[1] - ant[1];
      cv.classList.add("arrastando");
      this.cb.onHover?.(-1);
      this._movido();
    });
    const fim = (e) => {
      const g = this.gesto;
      this.ponteiros.delete(e.pointerId);
      if (this.ponteiros.size === 1 && g?.pinca) { g.pinca = null; return; }
      if (this.ponteiros.size) return;
      cv.classList.remove("arrastando");
      if (g && !g.moveu && e.type === "pointerup" && performance.now() - g.t < 600) {
        const p = this._ponto(e);
        const i = this.hitTela(p[0], p[1]);
        this.cb.onClick?.(i, e.clientX, e.clientY, e.pointerType);
      }
      this.gesto = null;
    };
    cv.addEventListener("pointerup", fim);
    cv.addEventListener("pointercancel", fim);
    cv.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse" && !this.ponteiros.size) { this.setHover(-1); this.cb.onHover?.(-1); } });
    cv.addEventListener("wheel", (e) => {
      // mapa dentro de página rolável (/analise/): a roda rola a página; zoom só com Ctrl/⌘ (ou pinça no trackpad)
      if (this.cb.rolagemLivre && !e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      const p = this._ponto(e);
      const f = Math.exp(-e.deltaY * (e.ctrlKey ? 0.012 : 0.0018));
      this.zoomEm(p[0], p[1], f);
    }, { passive: false });
    cv.addEventListener("dblclick", (e) => { const p = this._ponto(e); this.zoomEm(p[0], p[1], 2); });
    cv.addEventListener("keydown", (e) => {
      const passo = 60;
      const acoes = {
        ArrowLeft: () => { this.ox += passo; }, ArrowRight: () => { this.ox -= passo; },
        ArrowUp: () => { this.oy += passo; }, ArrowDown: () => { this.oy -= passo; },
        "+": () => this.zoomCentro(1.5), "=": () => this.zoomCentro(1.5), "-": () => this.zoomCentro(1 / 1.5),
        "0": () => this.ajustar(true),
      };
      if (acoes[e.key]) { e.preventDefault(); acoes[e.key](); this._movido(); }
    });
  }

  _pinca() {
    const [a, b] = [...this.ponteiros.values()];
    return { d: Math.max(1, Math.hypot(a[0] - b[0], a[1] - b[1])), c: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2] };
  }

  _hoverEm(p, e) {
    this._hp = [p, e.clientX, e.clientY];
    if (this._hr) return;
    this._hr = requestAnimationFrame(() => {
      this._hr = 0;
      const [q, cx, cy] = this._hp;
      const i = this.hitTela(q[0], q[1]);
      this.setHover(i);
      this.cb.onHover?.(i, cx, cy);
    });
  }
}
