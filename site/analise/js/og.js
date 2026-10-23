// Cartões de compartilhamento da Análise, desenhados pelo Chrome no build (build_site.py tira o print):
// /analise/og.html?s=<id>&f=og (1200×630) ou f=social (1080×1350). Sempre Brasil, tema escuro.
import { html, render } from "/vendor/preact-htm.module.js";
import { recorte, SECOES, LADOS, CAND, LADO_NOME, LADO_MIN, LADO_CURTO, LADO_COR, CARGO_NOME, pct, int, num, mi, ladoDe } from "./calc.js";
import { Empilhadas, Barras, Halteres, Pequenos, LegendaLados } from "./graficos.js";
import { carregar } from "./dados.js";

const q = new URLSearchParams(location.search);
const id = q.get("s") || "destaques", formato = q.get("f") === "social" ? "social" : "og";
const TITULO = Object.fromEntries(SECOES);
const S = formato === "social", RW = (n) => (S ? Math.round(n * 1.35) : n);
const cor = (l) => LADO_COR[l] || LADO_COR.C;
const SECAO_DO_ID = { campos: "campos", "voto-dividido": "dividido", "votos-cadeiras": "cadeiras", divergencias: "divergencias", "comparacao-2022": "comparacao", "terra-gente": "terraGente", "cenarios-2-turno": "cenarios", "brancos-nulos": "brancos", fragmentacao: "fragmentacao", legenda: "legenda", puxadores: "puxadores" };

function grafico(D, R) {
  const s = R[SECAO_DO_ID[id]];
  switch (id) {
    case "campos": return html`<${LegendaLados} itens=${LADOS.map((k) => [cor(k), LADO_NOME[k]])} /><${Empilhadas} titulo="" rotW=${S ? 210 : 170} bh=${S ? 44 : 26} linhas=${s.linhas.map((l) => ({ rotulo: l.nome, partes: LADOS.map((k) => ({ k, p: l.p[k], cor: cor(k), nome: k })) }))} />`;
    case "voto-dividido": return html`<${Barras} bh=${S ? 40 : 22} max=${1} rotW=${RW(230)} eixo=${false} titulo="" itens=${s.grupos[0].itens.map((it) => ({ rotulo: `${CAND.L} → ${LADO_MIN[it.dst]}`, v: it.p, int: it.int, cor: cor(it.dst) }))} />`;
    case "votos-cadeiras": return html`<${Halteres} rotA="% dos votos" rotB="% das cadeiras" titulo="" linhas=${s.casas.filter((c) => c.casa === "depfed").flatMap((c) => LADOS.map((l) => ({ rotulo: `Câmara · ${LADO_CURTO[l]}`, a: c.votos[l], b: c.pc[l], cor: cor(l) })))} />`;
    case "divergencias": return html`<${Barras} bh=${S ? 40 : 22} rotW=${RW(60)} eixo=${false} titulo="" itens=${[...s.porUF].sort((a, b) => b.p - a.p).slice(0, formato === "social" ? 10 : 6).map((x) => ({ rotulo: x.uf, v: x.p, cor: "var(--ink2)" }))} />`;
    case "comparacao-2022": return s.leg ? html`<${Halteres} rotA="2022" rotB="2026" titulo="" linhas=${s.leg.map((x) => ({ rotulo: `Dep. federal · ${LADO_CURTO[x.lado]}`, a: x.a, b: x.b, cor: cor(x.lado) }))} />` : null;
    case "terra-gente": return s.ok ? html`<${Empilhadas} titulo="" rotW=${S ? 210 : 170} bh=${S ? 44 : 26} linhas=${[["Área", "area_pct"], ["Votos válidos", "validos_pct"]].map(([rotulo, c]) => ({ rotulo, partes: ["L", "E", "F"].filter((k) => s.g.venc[k]?.mun > 0).map((k) => ({ k, p: s.g.venc[k][c], cor: k === "E" ? "var(--neutral)" : cor(k), nome: k === "E" ? "empate" : CAND[k] })) }))} />` : null;
    case "cenarios-2-turno": return html`<${Barras} bh=${S ? 40 : 22} max=${1} rotW=${RW(160)} eixo=${false} titulo="" itens=${[{ rotulo: `${CAND.L} precisa`, v: s.pl, cor: cor("L") }, { rotulo: `${CAND.F} precisa`, v: s.pf, cor: cor("F") }]} />`;
    case "brancos-nulos": return html`<${Pequenos} titulo="" itens=${s.itens.map((i) => ({ titulo: i.nome, valor: pct(i.p), partes: [{ v: i.pb, cor: "var(--outros)" }, { v: i.pn, cor: "var(--neutral)" }] }))} />`;
    case "fragmentacao": return html`<${Halteres} rotA="centro: % dos votos" rotB="centro: % das cadeiras" titulo="" linhas=${s.casas.map((c) => ({ rotulo: c.nome, a: c.centro_pct_votos, b: c.centro_pct_cadeiras, cor: cor("C") }))} />`;
    case "legenda": return html`<${Barras} bh=${S ? 40 : 22} rotW=${RW(200)} eixo=${false} titulo="" itens=${s.casas.slice(0, 1).flatMap((c) => LADOS.map((l) => ({ rotulo: `${c.nome} · ${LADO_CURTO[l]}`, v: c[l], cor: cor(l) })))} />`;
    case "puxadores": return html`<${Barras} bh=${S ? 40 : 22} rotW=${RW(260)} eixo=${false} titulo="" fmt=${(v) => mi(v)} itens=${s.itens.slice(0, formato === "social" ? 8 : 4).map((p) => ({ rotulo: `${p.nome} (${p.partido}-${p.uf})`, v: p.votos, marca: { v: p.quociente }, cor: cor(ladoDe(D, p.partido, p.uf)) }))} />`;
    case "destaques": return html`<ul class="og-cards">${(D.destaques || []).slice(0, formato === "social" ? 4 : 3).map((c) => html`<li><b>${c.numero}</b><span>${c.titulo}</span></li>`)}</ul>`;
    case "metodo": {
      const l26 = D.lados?.["2026"] || {}, n = { L: 0, C: 0, F: 0 };
      Object.values(l26).forEach((x) => { n[x.lado] = (n[x.lado] || 0) + 1; });
      return html`<ul class="og-cards">${LADOS.map((l) => html`<li><b style=${{ color: cor(l) }}>${int(n[l])}</b><span>partidos no ${LADO_MIN[l]}</span></li>`)}</ul>`;
    }
    case "faq": return html`<ul class="og-faq">${(D.faq || []).slice(0, 3).map((x) => html`<li>${x.q}</li>`)}</ul>`;
    default: return null;
  }
}

function Cartao({ D }) {
  const R = recorte(D, "BR");
  const s = R[SECAO_DO_ID[id]];
  const est = ["voto-dividido", "puxadores"].includes(id), cen = id === "cenarios-2-turno";
  const titulo = s?.titulo || { destaques: "Os números mais curiosos do 1º turno de 2026", faq: "Perguntas frequentes sobre o voto dividido em 2026", metodo: "Como os partidos foram classificados em campos" }[id] || TITULO[id];
  return html`<div class=${"og " + formato}>
    <p class="og-k">Análise · Eleições 2026 · ${TITULO[id]}${(est || cen) && html` <span class="badge">${cen ? "cenário" : "estimativa"}</span>`}</p>
    <h1>${titulo}</h1>
    ${s?.numero && s.numero !== "–" && html`<p class="og-n"><b>${s.numero}</b><span>${s.rotulo}</span></p>`}
    <div class="og-g">${grafico(D, R)}</div>
    <p class="og-pe"><span>Fonte: TSE${est ? " · estimativa própria" : ""}</span><span class="og-m">eleicoes2026.vitorpereira.ia.br · @vitorpereirasaas</span><b>vitor pereira<i></i></b></p>
  </div>`;
}

carregar(() => {}).then((D) => {
  render(html`<${Cartao} D=${D} />`, document.getElementById("og"));
  // o build espera este sinal antes do print
  setTimeout(() => document.body.setAttribute("data-pronto", "1"), 300);
});
