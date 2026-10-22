// Página /analise/: seções com manchete, número-chave, gráfico, "Entenda", fonte e compartilhamento.
// O seletor de UF recalcula todas as seções (recorte em calc.js). Pré-renderizada no build (Chrome headless).
import { html, render, useState, useEffect, useMemo, useErrorBoundary } from "/vendor/preact-htm.module.js";
import {
  recorte, SECOES, LADOS, SIGLA, CAND, LADO_NOME, LADO_MIN, LADO_CURTO, LADO_COR, UF_NOME, UFS, CARGO_NOME, CARGO_LONGO, CASA_NOME, CARGOS_DIV,
  pct, pp, int, num, mi, nomeRecorte, ufDoCodigo, ladoDe,
} from "./calc.js";
import { Dica, Empilhadas, Barras, Halteres, Pequenos, Dispersao, LegendaLados, TabelaSR, Dk } from "./graficos.js";
import { MapaMun, corLado, corApagada } from "./mapas.js";
import { ENTENDA, FONTE, METODO } from "./textos.js";
import { carregar } from "./dados.js";

const BASE = "https://eleicoes2026.vitorpereira.ia.br";
const TITULO_SEC = Object.fromEntries(SECOES);

// ---------------- peças
function Seguro({ children }) {
  const [erro] = useErrorBoundary((e) => console.error("[analise]", e));
  return erro ? html`<p class="vazio-txt">Não deu para mostrar este gráfico.</p>` : children;
}

const Ic = {
  link: html`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/></svg>`,
  zap: html`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11.5a8.5 8.5 0 0 1-12.6 7.4L3 20l1.2-4.2A8.5 8.5 0 1 1 20 11.5z"/></svg>`,
  x: html`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4l16 16M20 4 4 20"/></svg>`,
  copiar: html`<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/></svg>`,
  img: html`<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="m4 16 5-5 4 4 2-2 5 5"/><circle cx="15.5" cy="8.5" r="1.5"/></svg>`,
};

function Compartilhar({ id, titulo, uf }) {
  const [ok, setOk] = useState(false);
  const url = uf === "BR" ? `${BASE}/analise/${id}/` : `${BASE}/analise/?uf=${uf}#${id}`;
  const copiar = async () => {
    try { await navigator.clipboard.writeText(url); } catch { const t = document.createElement("textarea"); t.value = url; document.body.append(t); t.select(); document.execCommand("copy"); t.remove(); }
    setOk(true); setTimeout(() => setOk(false), 2200);
  };
  return html`<div class="share" role="group" aria-label="Compartilhar esta análise">
    <a class="bt ic" href=${`#${id}`} aria-label="Link desta seção" title="Link desta seção">${Ic.link}</a>
    <a class="bt" href=${`https://wa.me/?text=${encodeURIComponent(`${titulo} ${url}`)}`} target="_blank" rel="noopener">${Ic.zap}<span>WhatsApp</span></a>
    <a class="bt" href=${`https://x.com/intent/post?text=${encodeURIComponent(titulo)}&url=${encodeURIComponent(url)}`} target="_blank" rel="noopener">${Ic.x}<span>X</span></a>
    <button type="button" class="bt" onClick=${copiar}>${Ic.copiar}<span>${ok ? "Link copiado" : "Copiar link"}</span></button>
    ${uf === "BR" && html`<a class="bt" href=${`/og/social/analise-${id}.png`} download=${`analise-${id}.png`} title="Imagem 1080×1350 para redes sociais">${Ic.img}<span>Imagem</span></a>`}
    <span class="sr-only" aria-live="polite">${ok ? "Link copiado" : ""}</span>
  </div>`;
}

const Selo = ({ txt = "estimativa" }) => html`<span class="badge">${txt}</span>`;

function Secao({ id, s, est, selo, uf, children, nota }) {
  const ok = s?.ok !== false;
  return html`<section id=${id} class="sec" aria-labelledby=${id + "-h"} data-titulo=${ok ? s?.titulo || "" : ""} data-numero=${ok ? s?.numero || "" : ""} data-rotulo=${ok ? s?.rotulo || "" : ""}>
    <p class="kicker">${TITULO_SEC[id]} · ${uf === "BR" || !uf ? "Brasil" : nomeRecorte(uf)}${(est || selo) && html` <${Selo} txt=${selo || "estimativa"} />`}</p>
    ${ok ? html`
      <h2 id=${id + "-h"}>${s.titulo}</h2>
      ${s.numero && s.numero !== "–" && html`<p class="kpi"><b>${s.numero}</b><span>${s.rotulo}</span></p>`}
      ${nota && html`<p class="nota">${nota}</p>`}
      <${Seguro}>${children}<//>` : html`<h2 id=${id + "-h"}>${TITULO_SEC[id]}</h2><p class="vazio-txt">Sem dados ${uf && uf !== "BR" ? "para " + nomeRecorte(uf) : "ainda"} nesta seção.</p>`}
    ${ENTENDA[id] && html`<details class="entenda"><summary>Entenda</summary>${ENTENDA[id]}</details>`}
    ${FONTE[id] && html`<p class="fonte">${FONTE[id]}</p>`}
    ${ok && s?.titulo && html`<${Compartilhar} id=${id} titulo=${s.titulo} uf=${uf} />`}
  </section>`;
}

function Seg({ opcoes, valor, onTroca, rotulo }) {
  return html`<div class="seg" role="group" aria-label=${rotulo}>${opcoes.map(([k, t]) => html`<button type="button" aria-pressed=${valor === k} onClick=${() => onTroca(k)}>${t}</button>`)}</div>`;
}

const corL = (l) => LADO_COR[l] || LADO_COR.C;

// ---------------- seções
function Destaques({ D, uf }) {
  const it = D.destaques || [];
  return html`<section id="destaques" class="sec destaques" aria-labelledby="destaques-h" data-titulo="Destaques da análise do 1º turno de 2026" data-numero=${it[0]?.numero || ""} data-rotulo=${it[0]?.titulo || ""}>
    <h2 id="destaques-h" class="sr-only">Destaques</h2>
    ${uf !== "BR" && it.length > 0 && html`<p class="nota">Destaques nacionais. As seções abaixo mostram ${nomeRecorte(uf)}.</p>`}
    ${it.length ? html`<ul class="cards">${it.map((c) => html`<li><a class="card" href=${c.ancora || "#"}>
      <span class="c-n">${c.numero}</span><span class="c-t">${c.titulo}</span>${c.texto && html`<span class="c-x">${c.texto}</span>`}
      ${c.est && html`<${Selo} />`}</a></li>`)}</ul>` : html`<p class="vazio-txt">Os destaques aparecem quando os dados da análise forem publicados.</p>`}
  </section>`;
}

function Campos({ s }) {
  const linhas = (s.linhas || []).map((l) => ({
    rotulo: l.nome, sub: l.porEleitor > 1 ? "(2 votos)" : null,
    partes: LADOS.map((k) => ({ k, p: l.p[k], cor: corL(k), nome: LADO_NOME[k], dica: html`<${Dk} t=${`${l.nome} · ${LADO_NOME[k]}`} linhas=${[[corL(k), "Votos", int(l.votos[k])], [null, "Fatia", pct(l.p[k])]]} />` })),
  }));
  return html`<${LegendaLados} itens=${LADOS.map((k) => [corL(k), LADO_NOME[k]])} />
    <${Empilhadas} linhas=${linhas} titulo="Fatia de cada campo nos votos de cada cargo" />
    <${TabelaSR} cap="Votos por campo e cargo" cab=${["Cargo", ...LADOS.map((k) => LADO_NOME[k])]} linhas=${(s.linhas || []).map((l) => [l.nome, ...LADOS.map((k) => `${int(l.votos[k])} (${pct(l.p[k])})`)])} />`;
}

function Dividido({ s, cargo, setCargo, D, uf }) {
  const itens = (s.grupos || []).flatMap((g) => g.itens.map((it) => ({
    rotulo: `${g.quem === "lula" ? CAND.L : CAND.F} → ${LADO_MIN[it.dst]}`, v: it.p, int: it.int, cor: corL(it.dst),
    dica: html`<${Dk} t=${`${g.nome} que votaram no ${LADO_MIN[it.dst]} (${CARGO_LONGO[cargo]})`} linhas=${[[corL(it.dst), "Estimativa", `${pct(it.p)} · ${mi(it.v)}`], [null, "Faixa (90%)", it.int ? `${pct(it.int[0])} a ${pct(it.int[1])}` : "–"]]} />`,
  })));
  const pts = useMemo(() => {
    const mu = D.comparacao2022?.mu; if (!mu) return null;
    const cds = Object.keys(mu).filter((cd) => mu[cd].depfed26 && Number.isFinite(mu[cd].pres26_validos_lula));
    const x = new Float32Array(cds.length), y = new Float32Array(cds.length), lado = [];
    cds.forEach((cd, i) => { const m = mu[cd], d = m.depfed26, t = (d.L + d.F + d.C) || 1; x[i] = m.pres26_validos_lula; y[i] = d.L / t; lado.push(m.pres26 === "F" ? "F" : "L"); });
    return { x, y, lado, cds, on: uf === "BR" ? null : (i) => ufDoCodigo(cds[i]) === uf };
  }, [D.comparacao2022, uf]);
  return html`<${Seg} rotulo="Cargo da estimativa" valor=${cargo} onTroca=${setCargo} opcoes=${["depfed", "depest", "senador", "governador"].map((k) => [k, CARGO_NOME[k]])} />
    ${s.poucos ? html`<p class="vazio-txt">${s.nota}</p>` : s.ok ? html`<${Barras} itens=${itens} max=${1} titulo="Para onde foram os votos de cada candidato (estimativa)" rotW=${210} />
      <p class="nota">Barra = estimativa central; faixa clara com traço = intervalo de 90%.</p>` : html`<p class="vazio-txt">Sem estimativa para ${CARGO_LONGO[cargo]} neste recorte.</p>`}
    ${pts && html`<h3 class="h3">Cada ponto é um município: voto em ${CAND.L} × voto no ${LADO_MIN.L} para deputado federal</h3>
      <${Dispersao} pts=${pts} rotX=${`% de ${CAND.L} nos votos válidos (presidente)`} rotY=${`% do ${LADO_MIN.L} nos votos válidos (dep. federal)`} titulo="Dispersão por município"
        resumo=${`Pontos abaixo da diagonal: ${CAND.L} teve mais votos que o campo dele para deputado federal.`}
        dica=${(i) => { const cd = pts.cds[i]; return html`<${Dk} t=${`${D.mun?.[cd]?.[0] || cd} · ${ufDoCodigo(cd)}`} linhas=${[[corL("L"), `${CAND.L} · % dos válidos (presidente)`, pct(pts.x[i])], [corL("L"), `${LADO_NOME.L} · % dos válidos (dep. federal)`, pct(pts.y[i])]]} />`; }} />`}
    ${s.ok && !s.poucos && html`<${TabelaSR} cap=${`Voto dividido estimado, ${CARGO_LONGO[cargo]}`} cab=${["Fluxo", "Estimativa", "Faixa de 90%", "Eleitores"]} linhas=${(s.grupos || []).flatMap((g) => g.itens.map((it) => [`${g.nome} → ${LADO_NOME[it.dst]}`, pct(it.p), it.int ? `${pct(it.int[0])} a ${pct(it.int[1])}` : "–", int(it.v)]))} />`}
`;
}

function Cadeiras({ s }) {
  const linhas = (s.casas || []).flatMap((c) => LADOS.map((l) => ({
    rotulo: `${c.casa === "depfed" ? "Câmara" : c.casa === "depest" ? "Assembleias" : "Senado"} · ${LADO_CURTO[l]}`, a: c.votos[l], b: c.pc[l], cor: corL(l),
    dica: html`<${Dk} t=${`${c.nome} · ${LADO_NOME[l]}`} linhas=${[[corL(l), "Votos", pct(c.votos[l])], [corL(l), "Cadeiras", `${pct(c.pc[l])} (${int(c.cadeiras[l])} de ${int(c.total)})`], [null, "Diferença", pp(c.pc[l] - c.votos[l])]]} />`,
  })));
  return html`<${Halteres} linhas=${linhas} rotA="% dos votos" rotB="% das cadeiras" titulo="Votos e cadeiras por campo" />
    <${TabelaSR} cap="Votos e cadeiras por campo" cab=${["Casa e campo", "% dos votos", "Cadeiras"]} linhas=${(s.casas || []).flatMap((c) => LADOS.map((l) => [`${c.nome} · ${LADO_NOME[l]}`, pct(c.votos[l]), `${int(c.cadeiras[l])} de ${int(c.total)}`]))} />`;
}

function Divergencias({ s, D, uf, cargo, setCargo }) {
  const mu = D.divergencias?.mu || {};
  const [mais, setMais] = useState(false);
  // divergente = presidente com Lula ou Flávio e o cargo com outro lado (inclusive centro); empate para presidente (C) fica fora
  const diverge = (m) => m.pres !== "C" && m[cargo] !== m.pres;
  const corDe = (cd) => { const m = mu[cd]; if (!m || !m[cargo]) return null; return diverge(m) ? corLado(m[cargo]) : corApagada(); };
  const dica = (cd) => {
    const m = mu[cd]; const nome = D.mun?.[cd]?.[0] || s.ranking.find((x) => x.cd === cd)?.nome || cd;
    if (!m) return html`<${Dk} t=${nome} linhas=${[[null, "Sem dados", ""]]} />`;
    return html`<${Dk} t=${`${nome} · ${ufDoCodigo(cd)}`} linhas=${[[corL(m.pres), "Presidente", m.pres === "C" ? `empate ${CAND.L} × ${CAND.F}` : LADO_NOME[m.pres]], [corL(m[cargo]), CARGO_NOME[cargo], LADO_NOME[m[cargo]] || "–"], [null, m.pres === "C" ? "Fora da contagem" : diverge(m) ? "Divergente" : "Mesmo lado", ""]]} />`;
  };
  const rk = s.ranking.slice(0, mais ? 50 : 10);
  const porUF = [...s.porUF].sort((a, b) => b.p - a.p);
  return html`<${Seg} rotulo="Cargo comparado com presidente" valor=${cargo} onTroca=${setCargo} opcoes=${CARGOS_DIV.map((k) => [k, CARGO_NOME[k]])} />
    <ul class="chips">${[["LF", `${CAND.L} → ${CAND.F}`], ["LC", `${CAND.L} → centro`], ["FL", `${CAND.F} → ${CAND.L}`], ["FC", `${CAND.F} → centro`]].map(([k, t]) => html`<li><i class="sw" style=${{ "--c": corL(k[1]) }}></i>${t}: <b>${int(s.dir[k] || 0)}</b></li>`)}</ul>
    <p class="nota">Presidente → ${CARGO_LONGO[cargo]}: lado que venceu em cada um, em número de municípios.</p>
    <${MapaMun} corDe=${corDe} dica=${dica} chave=${cargo + Object.keys(mu).length} uf=${uf} rotulo=${`Mapa dos municípios onde presidente e ${CARGO_LONGO[cargo]} foram para lados diferentes.`} />
    <${LegendaLados} itens=${[[corL("L"), `divergente, ${CARGO_LONGO[cargo]} com ${CAND.L}`], [corL("F"), `… com ${CAND.F}`], [corL("C"), "… com o centro"], ["var(--neutral)", "mesmo lado"]]} />
    ${rk.length > 0 && html`<h3 class="h3">Maiores municípios divergentes entre ${CAND.L} e ${CAND.F} (sem os casos com centro) ${uf === "BR" ? "" : "· " + nomeRecorte(uf)}</h3>
      <div class="tab-w"><table class="tab"><thead><tr><th scope="col">Município</th><th scope="col">Presidente</th><th scope="col">${CARGO_NOME[cargo]}</th><th scope="col" class="n">Eleitores</th></tr></thead>
      <tbody>${rk.map((x) => html`<tr><th scope="row">${x.nome} <small>${x.uf}</small></th><td><i class="sw" style=${{ "--c": corL(x.pres) }}></i>${LADO_CURTO[x.pres]} ${pct(x.pres_pct, 0)}</td><td><i class="sw" style=${{ "--c": corL(x.leg) }}></i>${LADO_CURTO[x.leg]} ${pct(x.leg_pct, 0)}</td><td class="n">${int(x.eleitores)}</td></tr>`)}</tbody></table></div>
      ${s.ranking.length > 10 && html`<button type="button" class="link" onClick=${() => setMais(!mais)}>${mais ? "Mostrar menos" : `Mostrar ${Math.min(50, s.ranking.length)}`}</button>`}`}
    <h3 class="h3">% de municípios divergentes por estado</h3>
    <${Barras} itens=${porUF.map((x) => ({ rotulo: x.uf, v: x.p, cor: x.uf === uf || uf === "BR" ? "var(--ink2)" : "var(--line)", dica: html`<${Dk} t=${UF_NOME[x.uf]} linhas=${[[null, "Divergentes", `${int(x.div)} de ${int(x.total)}`], [null, "%", pct(x.p)]]} />` }))} rotW=${44} titulo="Municípios divergentes por estado" />
    <${TabelaSR} cap=${`Municípios divergentes por estado (presidente × ${CARGO_LONGO[cargo]})`} cab=${["Estado", "Divergentes", "Total", "%"]} linhas=${porUF.map((x) => [UF_NOME[x.uf], int(x.div), int(x.total), pct(x.p)])} />`;
}

function Comparacao({ s, D, uf }) {
  const mu = D.comparacao2022?.mu || {};
  const corDe = (cd) => {
    const m = mu[cd]; if (!m) return null;
    if (m.pres22 === "E" || m.pres26 === "E") return corApagada(); // empate: fora das viradas, cor neutra
    if (m.pres22 === "L" && m.pres26 === "F") return corLado("F", 0.95);
    if (m.pres22 === "B" && m.pres26 === "L") return corLado("L", 0.95);
    return corApagada();
  };
  const dica = (cd) => {
    const m = mu[cd]; const nome = D.mun?.[cd]?.[0] || s.ranking.find((x) => x.cd === cd)?.nome || cd;
    if (!m) return html`<${Dk} t=${nome} linhas=${[[null, "Sem dados", ""]]} />`;
    return html`<${Dk} t=${`${nome} · ${ufDoCodigo(cd)}`} linhas=${[[corL("L"), `${CAND.L} entre Lula e Bolsonaro (${SIGLA.F}) (2022)`, pct(m.pres22_pct_lula)], [corL("L"), `${CAND.L} entre Lula e ${CAND.F} (2026)`, pct(m.pres26_pct_lula)], [null, "Vencedor", `${{ L: CAND.L, B: `Bolsonaro (${SIGLA.F})`, E: "empate" }[m.pres22]} → ${{ L: CAND.L, F: CAND.F, E: "empate" }[m.pres26]}`]]} />`;
  };
  const pts = useMemo(() => {
    const cds = Object.keys(mu).filter((cd) => Number.isFinite(mu[cd].pres22_pct_lula) && Number.isFinite(mu[cd].pres26_pct_lula));
    if (!cds.length) return null;
    const x = new Float32Array(cds.length), y = new Float32Array(cds.length), lado = [];
    cds.forEach((cd, i) => { x[i] = mu[cd].pres22_pct_lula; y[i] = mu[cd].pres26_pct_lula; lado.push({ F: "F", L: "L" }[mu[cd].pres26] || "C"); });
    return { x, y, lado, cds, on: uf === "BR" ? null : (i) => ufDoCodigo(cds[i]) === uf };
  }, [mu, uf]);
  const rk = s.ranking.slice(0, 10);
  return html`<ul class="chips"><li><i class="sw" style=${{ "--c": corL("F") }}></i>${CAND.L} (2022) → ${CAND.F} (2026): <b>${int(s.lf)}</b></li><li><i class="sw" style=${{ "--c": corL("L") }}></i>Bolsonaro (${SIGLA.F}) (2022) → ${CAND.L} (2026): <b>${int(s.bl)}</b></li></ul>
    <${MapaMun} corDe=${corDe} dica=${dica} chave=${"v" + Object.keys(mu).length} uf=${uf} rotulo="Mapa das viradas entre 2022 e 2026 por município." />
    <${LegendaLados} itens=${[[corL("F"), `virou para ${CAND.F}`], [corL("L"), `virou para ${CAND.L}`], ["var(--neutral)", "mesmo lado ou empate"]]} />
    ${(s.leg || s.pres) && html`<h3 class="h3">Mudança por campo ${uf === "BR" ? "no Brasil" : "· " + nomeRecorte(uf)}</h3>
      <${Halteres} rotA="2022" rotB="2026" titulo="Campos em 2022 e 2026" linhas=${[
        ...(s.pres ? [{ rotulo: `Presidente · ${CAND.L} (entre os 2 primeiros)`, a: s.pres.a, b: s.pres.b, cor: corL("L"), dica: html`<${Dk} t=${`${CAND.L} para presidente`} linhas=${[[corL("L"), "2022", pct(s.pres.a)], [corL("L"), "2026", pct(s.pres.b)], [null, "Variação", pp(s.pres.b - s.pres.a)]]} />` }] : []),
        ...(s.leg || []).map((x) => ({ rotulo: `Dep. federal · ${LADO_CURTO[x.lado]}`, a: x.a, b: x.b, cor: corL(x.lado), dica: html`<${Dk} t=${`Deputado federal · ${LADO_NOME[x.lado]}`} linhas=${[[corL(x.lado), "2022", pct(x.a)], [corL(x.lado), "2026", pct(x.b)], [null, "Variação", pp(x.b - x.a)]]} />` })),
      ]} />`}
    ${pts && html`<h3 class="h3">Cada ponto é um município: ${CAND.L} em 2022 × em 2026</h3>
      <${Dispersao} pts=${pts} rotX=${`% de ${CAND.L} entre Lula e Bolsonaro (${SIGLA.F}) (2022)`} rotY=${`% de ${CAND.L} entre Lula e ${CAND.F} (2026)`} titulo=${`${CAND.L} por município em 2022 e 2026`} resumo=${`Pontos abaixo da diagonal: ${CAND.L} perdeu votos em relação a 2022.`}
        dica=${(i) => dica(pts.cds[i])} />`}
    ${rk.length > 0 && html`<h3 class="h3">Maiores variações</h3>
      <div class="tab-w"><table class="tab"><thead><tr><th scope="col">Município</th><th scope="col" class="n">${CAND.L} 2022</th><th scope="col" class="n">${CAND.L} 2026</th><th scope="col" class="n">Variação</th></tr></thead>
      <tbody>${rk.map((x) => html`<tr><th scope="row">${x.nome} <small>${x.uf || ufDoCodigo(x.cd)}</small></th><td class="n">${pct(x.pres22_pct_lula)}</td><td class="n">${pct(x.pres26_pct_lula)}</td><td class="n">${pp(x.pres26_pct_lula - x.pres22_pct_lula)}</td></tr>`)}</tbody></table></div>
      <p class="nota">${CAND.L} 2022 e 2026: fatia de Lula entre Lula e o adversário (Bolsonaro em 2022, Flávio em 2026, os dois do ${SIGLA.F}), não % dos votos válidos.</p>`}`;
}

function TerraGente({ s, D, uf }) {
  const mu = D["terra-gente"]?.mu || {}, g = s.g, v = g.venc;
  const nome = (cd) => D.mun?.[cd]?.[0] || cd;
  const VENC = { L: CAND.L, F: CAND.F, E: "empate" };
  const corDe = (cd) => { const m = mu[cd]; if (!m) return null; return m[1] === "E" ? corApagada() : corLado(m[1], 0.95); };
  const dica = (cd) => {
    const m = mu[cd];
    if (!m) return html`<${Dk} t=${nome(cd)} linhas=${[[null, "Sem dados", ""]]} />`;
    return html`<${Dk} t=${`${nome(cd)} · ${ufDoCodigo(cd)}`} linhas=${[[m[1] === "E" ? null : corL(m[1]), "Mais votado", VENC[m[1]]], [null, "Área", m[0] == null ? "sem geometria" : `${num(m[0], 0)} km²`], [null, "Votos válidos", int(m[2])]]} />`;
  };
  const fat = (k, campo) => ({ k, p: v[k][campo], cor: k === "E" ? "var(--neutral)" : corL(k), nome: VENC[k],
    dica: html`<${Dk} t=${`Municípios: ${VENC[k]}`} linhas=${[[k === "E" ? null : corL(k), "Municípios", int(v[k].mun)], [null, "Área", `${pct(v[k].area_pct)} · ${int(v[k].area)} km²`], [null, "Votos válidos", `${pct(v[k].validos_pct)} · ${int(v[k].validos)}`]]} />` });
  const ordem = ["L", "E", "F"].filter((k) => v[k]?.mun > 0);
  const outros = Math.max(0, 1 - g.lula_pct - g.flavio_pct);
  const linhas = [
    { rotulo: "Área", partes: ordem.map((k) => fat(k, "area_pct")) },
    { rotulo: "Votos válidos", sub: "(dos municípios)", partes: ordem.map((k) => fat(k, "validos_pct")) },
    { rotulo: "Votos válidos", sub: "(de cada um)", partes: [
      { k: "L", p: g.lula_pct, cor: corL("L"), nome: CAND.L, dica: html`<${Dk} t=${CAND.L} linhas=${[[corL("L"), "Votos válidos", `${pct(g.lula_pct)} · ${int(g.lula)}`]]} />` },
      { k: "C", p: outros, cor: corL("C"), nome: "Demais candidatos", dica: html`<${Dk} t="Demais candidatos" linhas=${[[corL("C"), "Votos válidos", pct(outros)]]} />` },
      { k: "F", p: g.flavio_pct, cor: corL("F"), nome: CAND.F, dica: html`<${Dk} t=${CAND.F} linhas=${[[corL("F"), "Votos válidos", `${pct(g.flavio_pct)} · ${int(g.flavio)}`]]} />` }] },
  ];
  return html`<ul class="frases">${s.frases.map((f) => html`<li>${f}</li>`)}</ul>
    <div class="lado-a-lado">
      <div><h3 class="h3">Por área: cada município com a cor de quem teve mais votos</h3>
        <${MapaMun} corDe=${corDe} dica=${dica} chave=${"tg" + Object.keys(mu).length} uf=${uf} rotulo="Mapa dos municípios pela cor do mais votado para presidente no 1º turno." />
        <${LegendaLados} itens=${[[corL("L"), CAND.L], [corL("F"), CAND.F], ["var(--neutral)", "empate"]]} /></div>
      <div><h3 class="h3">Por votos: a mesma divisão pesada pelos votos válidos</h3>
        <${Empilhadas} linhas=${linhas} rotW=${150} titulo="Área e votos válidos dos municípios ganhos por cada um, e votos válidos de cada candidato" />
        <${LegendaLados} itens=${[[corL("L"), CAND.L], [corL("F"), CAND.F], [corL("C"), "demais candidatos"], ["var(--neutral)", "empate"]]} /></div>
    </div>
    ${s.semGeo.length > 0 && html`<p class="nota">Sem geometria na malha do IBGE (votos contam, área fica fora): ${s.semGeo.map((x) => `${x.nome}-${x.uf} (${x.cd})`).join(", ")}.</p>`}
    <${TabelaSR} cap=${`Área e votos válidos dos municípios ganhos ${uf === "BR" ? "no Brasil" : "· " + nomeRecorte(uf)}`} cab=${["Mais votado", "Municípios", "Área (km²)", "% da área", "Votos válidos", "% dos válidos"]}
      linhas=${ordem.map((k) => [VENC[k], int(v[k].mun), int(v[k].area), pct(v[k].area_pct), int(v[k].validos), pct(v[k].validos_pct)])} />`;
}

function Cenarios({ s, D }) {
  const lados = D.lados;
  return html`${Number.isFinite(s.pl) && html`<${Barras} titulo="Quanto cada um precisa dos votos dos eliminados" max=${1} rotW=${120} itens=${[
      { rotulo: `${CAND.L} precisa`, v: s.pl, cor: corL("L"), dica: html`<${Dk} t=${CAND.L} linhas=${[[corL("L"), "Precisa dos eliminados", pct(s.pl)]]} />` },
      { rotulo: `${CAND.F} precisa`, v: s.pf, cor: corL("F"), dica: html`<${Dk} t=${CAND.F} linhas=${[[corL("F"), "Precisa dos eliminados", pct(s.pf)]]} />` }]} />`}
    ${s.eliminados.length > 0 && html`<h3 class="h3">Votos dos eliminados no 1º turno (${mi(s.totalElim)})</h3>
      <${LegendaLados} itens=${[[corL("F"), `apoio declarado do candidato a ${CAND.F}`], [corL("L"), `… a ${CAND.L}`], [corL("C"), "neutro ou sem declaração"]]} />
      <${Barras} titulo="Votos dos candidatos eliminados, pela cor do apoio declarado do candidato" rotW="auto" fmt=${(v) => mi(v)}
        itens=${s.eliminados.map((e) => { const ap = e.apoio_candidato || "C", lp = e.lado_partido || ladoDe({ lados }, e.partido);
          const varios = e.partido === "vários", n = varios ? (e.nome.match(/\d+/) || [""])[0] : "";
          return { rotulo: varios ? `Outros ${n} candidatos` : `${e.nome} (${e.partido})`, v: e.votos, cor: corL(ap), dica: html`<${Dk} t=${varios ? e.nome.replace(/^Demais/, "Outros") : `${e.nome} · ${e.partido}`} linhas=${[[null, "Votos", int(e.votos)], [corL(ap), "Apoio declarado do candidato", e.apoio_candidato ? LADO_NOME[ap] : "sem declaração verificada"], [corL(lp), "Partido em 2026", LADO_NOME[lp]]]} />` }; })} />
      <p class="nota">A cor é o apoio declarado do próprio candidato, não o do partido: o PSD de Caiado, por exemplo, ficou neutro. Apoio de candidato não garante o voto do eleitor.</p>`}
    ${s.cenarios.length > 0 && html`<h3 class="h3">Cenários (não são previsão)</h3>
      <${Empilhadas} titulo="Cenários do 2º turno" rotW="auto" linhas=${s.cenarios.map((c) => ({ rotulo: c.nome, partes: [
        { k: "L", p: c.lula / (c.lula + c.flavio), cor: corL("L"), nome: CAND.L, dica: html`<${Dk} t=${c.nome} linhas=${[[corL("L"), CAND.L, pct(c.lula)], [corL("F"), CAND.F, pct(c.flavio)]]} />` },
        { k: "F", p: c.flavio / (c.lula + c.flavio), cor: corL("F"), nome: CAND.F, dica: html`<${Dk} t=${c.nome} linhas=${[[corL("L"), CAND.L, pct(c.lula)], [corL("F"), CAND.F, pct(c.flavio)]]} />` }] }))} />
      <${TabelaSR} cap="Cenários do 2º turno (votos válidos)" cab=${["Cenário", CAND.L, CAND.F, `${CAND.F} leva dos eliminados`]} linhas=${s.cenarios.map((c) => [c.nome, pct(c.lula, 2), pct(c.flavio, 2), pct(c.flavio_pct_eliminados)])} />`}
    ${s.pesquisas.length > 0 && html`<h3 class="h3">Pesquisas de 2º turno publicadas</h3>
      <div class="tab-w"><table class="tab"><thead><tr><th scope="col">Instituto</th><th scope="col">Data</th><th scope="col" class="n">${CAND.L}</th><th scope="col" class="n">${CAND.F}</th><th scope="col">Registro</th></tr></thead>
      <tbody>${s.pesquisas.map((p) => html`<tr class=${p.antes_1t ? "antes" : ""}><th scope="row"><a href=${p.url} rel="noopener" target="_blank">${p.instituto}</a></th><td>${p.data}${p.antes_1t && html` <small class="antes-t">antes do 1º turno</small>`}</td><td class="n">${pct(p.lula, 0)}</td><td class="n">${pct(p.flavio, 0)}</td><td><small>${p.registro_tse || "–"}</small></td></tr>`)}</tbody></table></div>`}`;
}

function Brancos({ s }) {
  const max = Math.max(...s.itens.map((i) => i.p), 1e-9);
  return html`<${LegendaLados} itens=${[["var(--outros)", "brancos"], ["var(--neutral)", "nulos"]]} />
    <${Pequenos} titulo="Brancos e nulos por cargo" max=${max * 1.1} itens=${s.itens.map((i) => ({ titulo: i.nome, valor: pct(i.p), partes: [{ v: i.pb, cor: "var(--outros)" }, { v: i.pn, cor: "var(--neutral)" }],
      dica: html`<${Dk} t=${i.nome} linhas=${[["var(--outros)", "Brancos", `${pct(i.pb)} · ${int(i.brancos)}`], ["var(--neutral)", "Nulos", `${pct(i.pn)} · ${int(i.nulos)}`], [null, i.porEleitor > 1 ? "Votos possíveis (2 por eleitor)" : "Comparecimento", int(i.base)]]} />` }))} />
    <p class="nota">Base: comparecimento; no Senado, o dobro (2 votos por eleitor).</p>
    <${TabelaSR} cap="Brancos e nulos por cargo" cab=${["Cargo", "Brancos", "Nulos", "% dos votos possíveis"]} linhas=${s.itens.map((i) => [i.nome, int(i.brancos), int(i.nulos), pct(i.p)])} />`;
}

function Fragmentacao({ s }) {
  return html`<${Barras} titulo="Número efetivo de partidos" max=${Math.ceil(Math.max(...s.casas.map((c) => c.nep), 1) + 1)} rotW=${200} fmt=${(v) => num(v, 1)}
      itens=${s.casas.map((c) => ({ rotulo: c.nome, v: c.nep, cor: "var(--outros)", dica: html`<${Dk} t=${c.nome} linhas=${[[null, "Partidos efetivos", num(c.nep, 2)], [null, "Partidos com cadeira", int(c.partidos_com_cadeira)]]} />` }))} />
    <h3 class="h3">Peso do centro: votos × cadeiras</h3>
    <${Halteres} rotA="% dos votos" rotB="% das cadeiras" titulo="Centro: votos e cadeiras" linhas=${s.casas.map((c) => ({ rotulo: c.nome, a: c.centro_pct_votos, b: c.centro_pct_cadeiras, cor: corL("C"),
      dica: html`<${Dk} t=${`Centro · ${c.nome}`} linhas=${[[corL("C"), "Votos", pct(c.centro_pct_votos)], [corL("C"), "Cadeiras", pct(c.centro_pct_cadeiras)]]} />` }))} />
    <${TabelaSR} cap="Fragmentação" cab=${["Casa", "Partidos efetivos", "Partidos com cadeira", "Centro: % votos", "Centro: % cadeiras"]} linhas=${s.casas.map((c) => [c.nome, num(c.nep, 2), int(c.partidos_com_cadeira), pct(c.centro_pct_votos), pct(c.centro_pct_cadeiras)])} />`;
}

function Legenda({ s }) {
  const itens = s.casas.flatMap((c) => LADOS.map((l) => ({ rotulo: `${c.nome} · ${LADO_CURTO[l]}`, v: c[l], cor: corL(l), dica: html`<${Dk} t=${`${c.nome} · ${LADO_NOME[l]}`} linhas=${[[corL(l), "Voto de legenda", pct(c[l])], [null, "Média de todos", pct(c.total)]]} />` })));
  return html`<${Barras} titulo="Voto de legenda por campo" itens=${itens} rotW=${170} />
    <${TabelaSR} cap="Voto de legenda por campo" cab=${["Cargo", ...LADOS.map((l) => LADO_NOME[l]), "Total"]} linhas=${s.casas.map((c) => [c.nome, ...LADOS.map((l) => pct(c[l])), pct(c.total)])} />`;
}

function Puxadores({ s, D, cargo, setCargo, uf }) {
  const top = s.itens.slice(0, 15);
  return html`<${Seg} rotulo="Cargo" valor=${cargo} onTroca=${setCargo} opcoes=${[["depfed", "Dep. federal"], ["depest", "Dep. estadual"]]} />
    ${s.vazioUF ? html`<p class="vazio-txt">Nenhum dos 30 mais votados do país para ${CARGO_LONGO[cargo]} é ${uf === "BR" ? "" : "de " + uf}.</p>` : html`
    <${LegendaLados} itens=${LADOS.map((k) => [corL(k), LADO_NOME[k]])} />
    <p class="nota">O traço sobre cada barra marca o quociente eleitoral do estado do candidato: cada quociente atingido vale uma vaga para o partido.</p>
    <${Barras} titulo="Mais votados e quociente eleitoral" rotW=${210} fmt=${(v) => mi(v)}
      itens=${top.map((p) => { const l = ladoDe(D, p.partido, p.uf); return { rotulo: `${p.nome} (${p.partido}-${p.uf})`, v: p.votos, cor: corL(l), marca: { v: p.quociente },
        dica: html`<${Dk} t=${`${p.nome} · ${p.partido}-${p.uf}`} linhas=${[[corL(l), "Votos", int(p.votos)], [null, "Quociente eleitoral", int(p.quociente)], [null, "Cadeiras do partido", int(p.cadeiras_partido)], [null, "Puxados (estimativa)", int(p.puxados_estimados)]]} />` }; })} />`}
    <${TabelaSR} cap=${`Puxadores de voto, ${CARGO_LONGO[cargo]}`} cab=${["Candidato", "Votos", "Quociente", "Puxados (estimativa)"]} linhas=${s.itens.map((p) => [`${p.nome} (${p.partido}-${p.uf})`, int(p.votos), int(p.quociente), int(p.puxados_estimados)])} />`;
}

function Faq({ D }) {
  const qa = D.faq || [];
  return html`<section id="faq" class="sec faq" aria-labelledby="faq-h" data-titulo="Perguntas frequentes sobre o voto dividido em 2026" data-numero="" data-rotulo=${qa[0]?.q || ""}>
    <p class="kicker">${TITULO_SEC.faq}</p><h2 id="faq-h">Perguntas frequentes</h2>
    ${qa.length ? qa.map((x, i) => html`<details open=${i < 2}><summary>${x.q}</summary><p>${x.a}</p></details>`) : html`<p class="vazio-txt">Em preparação.</p>`}
    <${Compartilhar} id="faq" titulo="Perguntas frequentes sobre o voto dividido em 2026" uf="BR" />
  </section>`;
}

const TIPO_PROVA = { nota: "nota oficial", coligacao: "coligação no TSE", imprensa: "imprensa", declaracao: "declaração pública" };
function Metodo({ D, uf }) {
  const L = D.lados || {}, l26 = L["2026"] || {}, l22 = L["2022"] || {};
  const partidos = Object.keys(l26).sort((a, b) => LADOS.indexOf(l26[a].lado) - LADOS.indexOf(l26[b].lado) || a.localeCompare(b));
  return html`<section id="metodo" class="sec" aria-labelledby="metodo-h" data-titulo="Como os partidos foram classificados em campos" data-numero="" data-rotulo="">
    <p class="kicker">${TITULO_SEC.metodo}</p><h2 id="metodo-h">Método e classificação dos partidos</h2>
    ${METODO}
    ${D.dividido?.metodo && html`<p><b>Estimativa de voto dividido:</b> ${D.dividido.metodo}</p>`}
    ${partidos.length ? html`<p class="nota">Posição em ${L.posicao_em || "–"}${uf !== "BR" ? `; exceções de ${nomeRecorte(uf)} destacadas` : ""}.</p>
      <div class="tab-w"><table class="tab lados"><thead><tr><th scope="col">Partido</th><th scope="col">Campo em 2026</th><th scope="col">Exceções por UF</th><th scope="col">Provas</th><th scope="col">2º turno de 2022</th></tr></thead>
      <tbody>${partidos.map((sg) => {
        const x = l26[sg], exc = Object.entries(x.uf || {}), y = l22[sg];
        const aqui = uf !== "BR" && x.uf?.[uf];
        return html`<tr class=${aqui ? "realce" : ""}><th scope="row">${sg}</th>
          <td><i class="sw" style=${{ "--c": corL(x.lado) }}></i>${LADO_NOME[x.lado] || "–"}</td>
          <td>${exc.length ? exc.map(([u, l]) => html`<span class="exc">${u}: ${LADO_CURTO[l]}</span> `) : "–"}</td>
          <td>${(x.provas || []).map((p) => html`<a href=${p.url} rel="noopener" target="_blank"><cite>${p.titulo || TIPO_PROVA[p.tipo] || "prova"}</cite></a> <small>(${TIPO_PROVA[p.tipo] || p.tipo}, ${p.data})</small><br />`)}${!(x.provas || []).length && "sem declaração com prova"}</td>
          <td>${y ? (y.lado === "F" ? `Bolsonaro (${SIGLA.F})` : y.lado === "L" ? CAND.L : "Centro/sem lado") : "–"}</td></tr>`;
      })}</tbody></table></div>` : html`<p class="vazio-txt">A tabela de classificação aparece quando os dados forem publicados.</p>`}
    <${Compartilhar} id="metodo" titulo="Como os partidos foram classificados em campos" uf="BR" />
  </section>`;
}

// ---------------- barra do recorte (UF) + índice
function BarraUF({ uf, setUF, ufs }) {
  return html`<div class="barra"><div class="in">
    <label class="uf-sel"><span>Recorte</span><select value=${uf} onChange=${(e) => setUF(e.currentTarget.value)} aria-label="Escolher estado: todas as seções recalculam">
      <option value="BR">Brasil</option>${ufs.map((u) => html`<option value=${u}>${UF_NOME[u]}</option>`)}</select></label>
    <nav class="indice" aria-label="Seções">${SECOES.filter(([id]) => id !== "destaques").map(([id, t]) => html`<a href=${"#" + id}>${t}</a>`)}</nav>
  </div></div>`;
}

// ---------------- app
function App({ D0 }) {
  const ini = new URLSearchParams(location.search).get("uf");
  const [D, setD] = useState(D0);
  const [uf, setUFs] = useState(ini && UF_NOME[ini] ? ini : "BR");
  const [cargoDiv, setCargoDiv] = useState("depfed"), [cargoDividido, setCargoDividido] = useState("depfed"), [cargoPux, setCargoPux] = useState("depfed");
  useEffect(() => { setDFora = setD; if (ultimo !== D0) setD(ultimo); return () => { setDFora = null; }; }, []);
  const R = useMemo(() => recorte(D, uf, { cargoDiv, cargoDividido, cargoPux }), [D, uf, cargoDiv, cargoDividido, cargoPux]);
  const setUF = (u) => {
    setUFs(u);
    const q = u === "BR" ? location.pathname : `${location.pathname}?uf=${u}`;
    history.replaceState(null, "", q + location.hash);
  };
  const ufs = UFS;
  const nada = !D.campos && !D.destaques;
  return html`
    <${BarraUF} uf=${uf} setUF=${setUF} ufs=${ufs} />
    <div class="corpo">
      <header class="abre">
        <p class="kicker">Análise · 1º turno de 2026</p>
        <h1>Voto dividido em 2026: por que ${CAND.L} tem tantos votos e o campo dele elege poucos deputados</h1>
        <p class="lead">Os números do TSE por campo político, cargo e município. Contagens oficiais e estimativas aparecem juntas, e toda estimativa vem marcada. Escolha um estado no alto para recalcular tudo.</p>
        ${nada && html`<p class="vazio-txt">Os dados da análise ainda não foram publicados. Volte em breve.</p>`}
      </header>
      <${Destaques} D=${D} uf=${uf} />
      <${Secao} id="campos" s=${R.campos} uf=${uf}><${Campos} s=${R.campos} /><//>
      <${Secao} id="voto-dividido" s=${R.dividido.ok ? R.dividido : { ...R.dividido, ok: true, titulo: `Voto dividido estimado ${uf === "BR" ? "no Brasil" : "· " + nomeRecorte(uf)}`, numero: "–" }} est=${true} uf=${uf}>
        <${Dividido} s=${R.dividido} cargo=${cargoDividido} setCargo=${setCargoDividido} D=${D} uf=${uf} /><//>
      <${Secao} id="votos-cadeiras" s=${R.cadeiras} uf=${uf}><${Cadeiras} s=${R.cadeiras} /><//>
      <${Secao} id="divergencias" s=${R.divergencias} uf=${uf}><${Divergencias} s=${R.divergencias} D=${D} uf=${uf} cargo=${cargoDiv} setCargo=${setCargoDiv} /><//>
      <${Secao} id="comparacao-2022" s=${R.comparacao} uf=${uf}><${Comparacao} s=${R.comparacao} D=${D} uf=${uf} /><//>
      <${Secao} id="terra-gente" s=${R.terraGente} uf=${uf}><${TerraGente} s=${R.terraGente} D=${D} uf=${uf} /><//>
      <${Secao} id="cenarios-2-turno" s=${R.cenarios} selo="cenário" uf="BR" nota=${uf !== "BR" ? "Cenários são nacionais: a eleição para presidente é decidida pelo total do país." : null}><${Cenarios} s=${R.cenarios} D=${D} /><//>
      <${Secao} id="brancos-nulos" s=${R.brancos} uf=${uf}><${Brancos} s=${R.brancos} /><//>
      <${Secao} id="fragmentacao" s=${R.fragmentacao} uf=${uf}><${Fragmentacao} s=${R.fragmentacao} /><//>
      <${Secao} id="legenda" s=${R.legenda} uf=${uf}><${Legenda} s=${R.legenda} /><//>
      <${Secao} id="puxadores" s=${R.puxadores} est=${true} uf=${uf}><${Puxadores} s=${R.puxadores} D=${D} cargo=${cargoPux} setCargo=${setCargoPux} uf=${uf} /><//>
      <${Faq} D=${D} />
      <${Metodo} D=${D} uf=${uf} />
    </div>
    <${Dica} />`;
}

// pré-render: espera os dados pequenos antes de trocar o HTML pronto (sem piscar a página em branco);
// os grandes (um registro por município) chegam depois e atualizam a página
let setDFora = null, ultimo = null, montado = false;
const raiz = document.getElementById("analise");
carregar((D) => {
  ultimo = D;
  if (setDFora) { setDFora(D); return; }
  if (montado) return;
  montado = true;
  const alvo = location.hash ? decodeURIComponent(location.hash.slice(1)) : null;
  raiz.textContent = "";
  render(html`<${App} D0=${D} />`, raiz);
  if (alvo) requestAnimationFrame(() => document.getElementById(alvo)?.scrollIntoView());
});
