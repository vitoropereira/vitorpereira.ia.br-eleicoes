// Home do 2º turno (issue 205): véspera → apuração → resultado. Servido em /home.js (build_site.py copia este arquivo).
// As funções puras (fase, faltam, placar, ancoraAntiga) não tocam DOM nem rede; testes em home_test.js (deno test home/).
// O HTML publicado sai na Véspera, sem números: o pré-render (Chrome headless) roda este módulo, mas /vivo/ dá 404 no
// build e a contagem não é escrita sob webdriver, então o DOM gravado não carrega nem placar nem "faltam…" velhos.
import { criarVivo } from "./hud/dados.js";
import { linha } from "./hud/calc.js";

/** 25/10/2026 17:00 em Brasília (UTC-3) */
export const INICIO_APURACAO = Date.UTC(2026, 9, 25, 20, 0);

/** "vespera" | "apuracao" | "resultado". Nunca antes das 17h de 25/10, mesmo que já haja dado (ensaio); depois das 17h
 *  sem agora.json válido continua na véspera. */
export function fase(agoraMs, vivo) {
  if (agoraMs < INICIO_APURACAO || !vivo) return "vespera";
  return vivo.eleito ? "resultado" : "apuracao";
}

/** "faltam 3h 12min" até as 17h de 25/10; "" quando já passou */
export function faltam(agoraMs) {
  const ms = INICIO_APURACAO - agoraMs;
  if (ms <= 0) return "";
  const min = Math.floor(ms / 60000), h = Math.floor(min / 60), m = min % 60;
  return h > 0 ? `faltam ${h}h ${m}min` : `faltam ${m}min`;
}

const LADO = { 22: "F", 13: "L" };

/** {pst, cands:[{nome, sg, n, v, p, lado}]}: p em % dos válidos, na ordem dos votos (agora.cand; sem ela, `reserva`) */
export function placar(vivo, reserva) {
  const votos = vivo?.br?.[5] || [];
  const lista = Array.isArray(vivo?.cand) ? vivo.cand : (reserva || []).slice(0, votos.length || 2);
  if (!lista.length) return { pst: vivo?.pst ?? 0, cands: [] };
  const r = linha("presidente", vivo.br, lista.map((c, i) => ({ ...c, _i: i })));
  const cands = r.cands.sort((a, b) => a._i - b._i)
    .map((c) => ({ nome: c.nome, sg: c.sg, n: c.n, v: c.v, p: c.p * 100, lado: LADO[c.n] || "C" }));
  return { pst: vivo.pst ?? 0, cands };
}

/** Linha da projeção ao vivo (/vivo/projecao.json, gravado pelo watch_2turno.sh a cada ~2 min): "" se o arquivo
 *  é inválido. `pj` = {t, pst, f, l, pf, pl, nf, nl, sf, sl}: % final projetado e chance de vencer de cada um. */
export function textoProjecao(pj) {
  const n = (x) => typeof x === "number" && Number.isFinite(x);
  if (!pj || ![pj.f, pj.l, pj.pf, pj.pl].every(n) || !/^\d\d:\d\d$/.test(pj.t || "")) return "";
  const p1 = (x) => x.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const p0 = (x) => Math.round(x).toLocaleString("pt-BR");
  return `Projeção para o fim da apuração: ${pj.nf} (${pj.sf}) ${p1(pj.f)}% × ${pj.nl} (${pj.sl}) ${p1(pj.l)}% · ` +
    `chance de vencer ${p0(pj.pf)}% × ${p0(pj.pl)}% · calculada às ${pj.t}. É modelo, não resultado.`;
}

const ANCORAS = new Set(["destaques", "presidente", "governadores", "senado", "camara", "assembleias", "apuracao",
  "perguntas", "metodo", "hl", "reg", "outros", "cmp22", "traj"]);

/** link antigo da home (#presidente…) → "/1-turno/#presidente"; null se a âncora não é do relatório */
export function ancoraAntiga(hash) {
  const id = String(hash || "").replace(/^#/, "");
  return ANCORAS.has(id) ? `/1-turno/#${id}` : null;
}

// ---------------- página
const pct2 = (x) => x.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const COR = { F: "var(--flavio)", L: "var(--lula)", C: "var(--outros)" };

function el(doc, tag, cls, txt) {
  const e = doc.createElement(tag);
  if (cls) e.className = cls;
  if (txt != null) e.textContent = txt;
  return e;
}

function pintarPlacar(doc, raiz, p) {
  raiz.replaceChildren(...p.cands.map((c) => {
    const box = el(doc, "div", "cand");
    box.append(el(doc, "span", "nome", `${c.nome} (${c.sg})`), el(doc, "b", "pct", `${pct2(c.p)}%`));
    const barra = el(doc, "span", "barra");
    const i = el(doc, "i");
    i.style.width = `${Math.max(0, Math.min(100, c.p))}%`;
    i.style.background = COR[c.lado];
    barra.append(i);
    box.append(barra);
    return box;
  }));
}

/** relógio de teste (?agora=2026-10-25T21:00-03:00): só em localhost */
export function relogio(loc, agora = () => Date.now()) {
  const local = loc.hostname === "127.0.0.1" || loc.hostname === "localhost";
  const t = local ? Date.parse(new URLSearchParams(loc.search).get("agora") || "") : NaN;
  if (!Number.isFinite(t)) return agora;
  const d0 = t - agora();
  return () => agora() + d0;
}

export function iniciar(doc = document, loc = location, nav = navigator) {
  const destino = ancoraAntiga(loc.hash);
  if (destino) { loc.replace(destino); return; }
  const agora = relogio(loc);
  const sec = (f) => doc.querySelector(`[data-fase="${f}"]`);
  const secoes = { vespera: sec("vespera"), apuracao: sec("apuracao"), resultado: sec("resultado") };
  if (!secoes.vespera) return;
  const reserva = (() => { try { return JSON.parse(secoes.apuracao?.dataset.cand || "[]"); } catch { return []; } })();
  // resultado = manchete do eleito + o placar final logo acima (a seção da apuração continua à mostra)
  const mostrar = (f) => { for (const k in secoes) if (secoes[k]) secoes[k].hidden = !(k === f || (f === "resultado" && k === "apuracao")); };
  const q = (s) => doc.querySelector(s);

  function contagem() {
    const t = q("[data-faltam]");
    if (!t || nav.webdriver) return;
    const txt = faltam(agora());
    t.textContent = txt ? ` · ${txt}` : "";
  }

  function aplicar(vivo) {
    const f = fase(agora(), vivo);
    if (f === "vespera") return;
    const p = placar(vivo, reserva);
    if (!p.cands.length) return;
    mostrar(f);
    pintarPlacar(doc, q('[data-fase="apuracao"] [data-placar]'), p);
    const ap = q("[data-apurado]");
    if (ap) {
      const hora = /^\d\d:\d\d$/.test(vivo.t || "") ? vivo.t : ""; // hora da leitura do TSE, já em Brasília
      ap.textContent = `${pct2(p.pst)}% das urnas apuradas${hora ? ` · atualizado às ${hora}` : ""}`;
    }
    if (f === "resultado") {
      encerrada = true;
      const lp = q("[data-projecao]");
      if (lp) lp.hidden = true;
      const ganhou = p.cands.find((c) => String(c.n) === String(vivo.eleito));
      const t = q("[data-eleito]");
      if (ganhou && t) t.textContent = `${ganhou.nome} (${ganhou.sg}) é eleito presidente`;
      const v = q("[data-eleito-pct]");
      if (ganhou && v) v.textContent = `${pct2(ganhou.p)}% dos votos válidos`;
    }
  }

  // projeção ao vivo: só na apuração; sem arquivo (404) ou inválido, a linha fica escondida
  // com o resultado oficial, a projeção não tem mais o que dizer: a linha some e para de buscar
  let encerrada = false;
  async function projecao() {
    const linhaP = q("[data-projecao]");
    if (!linhaP || encerrada || fase(agora(), {}) === "vespera") return;
    try {
      const r = await fetch(`/vivo/projecao.json?t=${Math.floor(Date.now() / 60000)}`);
      const txt = r.ok ? textoProjecao(await r.json()) : "";
      linhaP.replaceChildren();
      if (txt) {
        const a = el(doc, "a", null, "como calculamos");
        a.href = "/apuracao/";
        linhaP.append(`${txt} `, a);
      }
      linhaP.hidden = !txt;
    } catch { /* rede: tenta no próximo minuto */ }
  }

  const vivo = criarVivo((est) => {
    if (est.dados) aplicar(est.dados);
    else if (est.status === "vazio" || est.status === "erro") {
      const w = q("[data-aguardando]");
      if (w && agora() >= INICIO_APURACAO) w.hidden = false;
    }
  });
  let ligado = false;
  function tick() {
    contagem();
    if (!ligado && agora() >= INICIO_APURACAO) { ligado = true; vivo.ativar(); }
    if (ligado && !nav.webdriver) projecao();
  }
  tick();
  setInterval(tick, 60000);
}

if (typeof document !== "undefined") iniciar();
