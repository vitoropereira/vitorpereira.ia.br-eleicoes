// Painéis do HUD (Preact + htm): esquerdo (manchete, placar, totais, gráfico) e direito (regiões, feed).
import { html, useState } from "/vendor/preact-htm.module.js";
import { pct, int, linha, somar, oficial, duelo, senadoEleitos, REGIOES, UF_NOME, UFS, cor, ehDep, comSigla, cartao, cartaoCurto, textoComSigla, CARGO_NOME } from "./calc.js";

const CORES_MARCA = new Set(["PL", "PT"]);
/** nome com a cor do partido: PL/PT usam o token (contraste testado); os demais, sublinhado na cor */
export const Nome = ({ c, curto }) => html`<span class=${CORES_MARCA.has(c.sg) ? "nm-c" : "nm-u"} style=${{ "--c": cor(c.sg) }}>${comSigla(c, curto)}</span>`;
export const Sw = ({ sg }) => html`<i class="sw" style=${{ "--c": cor(sg) }} aria-hidden="true"></i>`;

function manchete(cargo, r, onde, turno, pst, parcial, of, eleito) {
  const [a, b] = r.cands;
  if (!a) return null;
  const lidera = html`<${Nome} c=${a} /> lidera com ${pct(a.p * 100, 1)}%${onde}`;
  if (parcial) return html`<${Nome} c=${a} /> lidera com ${pct(parcial.pst, 1)}% das seções`;
  // 2º turno: "eleito" SÓ quando o TSE marcou (agora.json `eleito`); senão, quem lidera e com quanto apurado
  if (turno === 2) return eleito ? html`<${Nome} c=${eleito} /> é eleito presidente` : html`<${Nome} c=${a} /> lidera com ${pct(pst ?? 0, 1)}% das seções${onde}`;
  // 1º turno: só a situação oficial diz quem foi eleito ou quem vai ao 2º turno
  // Senado: "eleito" só com a situação oficial E 100% apurado (senadoEleitos); leitura parcial nunca anuncia eleito
  const el = cargo === "senador" ? senadoEleitos(of, pst) : null;
  if (el) {
    return el.length > 1 ? html`<${Nome} c=${el[0]} /> e <${Nome} c=${el[1]} /> são eleitos para o Senado${onde}` : html`<${Nome} c=${el[0]} /> é eleito para o Senado${onde}`;
  }
  if (of?.status === "eleito" && of.a) return html`<${Nome} c=${of.a} /> é eleito no 1º turno${onde}`;
  if (of?.status === "2turno" && of.a && of.b) return html`<${Nome} c=${of.a} /> e <${Nome} c=${of.b} /> vão ao 2º turno${onde}`;
  return lidera;
}

export const TagSJ = ({ c }) => (c.sj ? html` · <span class="tag-sj">sub judice</span>` : null);

// ---------------- placar (presidente, governador, senador)
export function Placar({ cargo, r, kicker, selo, onVoltar, ponto, serie, idx, turno, pst, of, pend, eleito, atualizado }) {
  const [todos, setTodos] = useState(false);
  if (!r || !r.cands.length) return html`<p class="vazio-txt">Sem dados para este recorte.</p>`;
  if (r.vazio) return html`
    <div class="cab">
      <p class="kicker">${kicker}</p>
      ${onVoltar && html`<button type="button" class="link" onClick=${onVoltar}>← Brasil</button>`}
    </div>
    <h1 class="manchete pequena">${turno === 2 ? "A apuração começa domingo, 25/10, às 17h (Brasília)" : "Nenhuma seção apurada ainda"}</h1>
    ${pend?.length > 0 && html`<p class="mais pend">UFs atualizando: ${pend.join(", ")}</p>`}
    <p class="vazio-txt">O TSE já publicou ${turno === 2 ? "o 2º turno" : "a eleição"}, mas ainda sem votos totalizados${pst != null ? ` (${pct(pst, 1)}% das seções)` : ""}. Os números aparecem aqui assim que as primeiras urnas forem apuradas.</p>`;
  const [a, b] = r.cands;
  const outros = r.cands.slice(2);
  const visiveis = todos ? outros : outros.slice(0, 3);
  const resto = outros.slice(3);
  const somaResto = resto.reduce((s, c) => s + c.p, 0);
  const lado = (c, dir) => html`
    <div class=${"lado " + dir}>
      <div class="quem"><b>${c.nome}</b><small>${c.sg}${c.n ? " " + c.n : ""}<${TagSJ} c=${c} /></small></div>
      <div class=${"num " + (CORES_MARCA.has(c.sg) ? "nm-c" : "")} style=${{ "--c": cor(c.sg) }}>${pct(c.p * 100, 2)}<small>%</small></div>
      <div class="votos">${ponto ? "votos válidos" : int(c.v) + " votos"}</div>
    </div>`;
  const dif = (a.p - (b ? b.p : 0)) * 100;
  return html`
    <div class="cab">
      <p class="kicker">${kicker}</p>
      ${onVoltar && html`<button type="button" class="link" onClick=${onVoltar}>← Brasil</button>`}
      ${selo && html`<span class="selo">${selo}</span>`}
    </div>
    <h1 class="manchete">${manchete(cargo, r, "", turno, pst, ponto, of, eleito)}</h1>
    ${atualizado && html`<p class="mais">${atualizado}</p>`}
    ${pend?.length > 0 && html`<p class="mais pend">UFs atualizando: ${pend.join(", ")}</p>`}
    <div class="placar">${lado(a, "l1")}${b && lado(b, "l2")}</div>
    ${b && html`<div class="duelo" aria-hidden="true">
      <i style=${{ width: (a.p * 100).toFixed(2) + "%", "--c": cor(a.sg) }}></i>
      <i class="meio"></i>
      <i style=${{ width: (b.p * 100).toFixed(2) + "%", "--c": cor(b.sg) }}></i></div>`}
    <dl class="dif">
      <div><dt>Diferença</dt><dd>${pct(dif, 2)} pontos${ponto ? "" : " · " + int(a.v - (b ? b.v : 0)) + " votos"}</dd></div>
      ${ponto && html`<div><dt>Leitura</dt><dd>${ponto.d ? ponto.d + " " : ""}${ponto.ht} · ${pct(ponto.pst, 1)}% das seções</dd></div>`}
    </dl>
    ${!ponto && outros.length > 0 && html`
      <ul class="outros">
        ${visiveis.map((c) => html`<li><${Sw} sg=${c.sg} /><span class="nm">${c.nome}<small>${c.sg}${c.n ? " " + c.n : ""}<${TagSJ} c=${c} /></small></span><span class="p">${pct(c.p * 100, 2)}%</span></li>`)}
      </ul>
      ${!todos && resto.length > 0 && html`<p class="mais">Mais ${resto.length} ${resto.length === 1 ? "candidatura soma" : "candidaturas somam"} ${pct(somaResto * 100, 1)}%</p>`}
      ${outros.length > 3 && html`<button type="button" class="link" aria-expanded=${todos} onClick=${() => setTodos(!todos)}>${todos ? "Mostrar menos" : `Todos os ${r.cands.length} candidatos`}</button>`}`}
    ${!ponto && r.vansj > 0 && html`<p class="mais">Votos de candidatura sub judice contam no total até o julgamento (regra do TSE).</p>`}
    ${!ponto && r.validos != null && html`
      <dl class="totais">
        <div><dt>Votos válidos</dt><dd>${int(r.validos)}</dd></div>
        <div><dt>Comparecimento</dt><dd>${pct(r.pc * 100, 1)}%</dd></div>
        <div><dt>Brancos e nulos</dt><dd>${pct(r.pbn * 100, 1)}%</dd></div>
      </dl>`}
    ${serie && serie.length > 1 && html`<${GraficoNoite} serie=${serie} idx=${idx} cands=${r.cands} />`}
  `;
}

// ---------------- gráfico "Ao longo da apuração" (SVG, sem biblioteca)
export function GraficoNoite({ serie, idx, cands }) {
  const { F: cF, L: cL } = duelo(cands), nF = comSigla(cF, true), nL = comSigla(cL, true);
  const W = 300, H = 132, L = 30, R = 6, T = 8, B = 20;
  const vals = serie.flatMap((s) => [s.f, s.l]);
  const lo = Math.floor(Math.min(...vals) - 1), hi = Math.ceil(Math.max(...vals) + 1);
  const x = (p) => L + (p / 100) * (W - L - R), y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  const linhaD = (k) => serie.map((s, i) => `${i ? "L" : "M"}${x(s.pst).toFixed(1)},${y(s[k]).toFixed(1)}`).join("");
  const passo = hi - lo > 12 ? 4 : 2;
  const ticks = []; for (let v = Math.ceil(lo / passo) * passo; v <= hi; v += passo) ticks.push(v);
  const atual = idx == null ? serie[serie.length - 1] : serie[idx];
  const quando = (p) => `${p.d ? p.d + " " : ""}${p.ht}`;
  const F = serie[serie.length - 1];
  return html`
    <figure class="grafico">
      <figcaption><span class="kicker">Ao longo da apuração</span>
        <span class="leg"><i style=${{ "--c": cor(cF.sg) }}></i>${cartaoCurto(cF)} <i style=${{ "--c": cor(cL.sg) }}></i>${cartaoCurto(cL)}</span></figcaption>
      <svg viewBox=${`0 0 ${W} ${H}`} role="img" aria-label=${`Trajetória da apuração: ${nF} começou com ${pct(serie[0].f, 1)}% e terminou com ${pct(F.f, 1)}%; ${nL} foi de ${pct(serie[0].l, 1)}% a ${pct(F.l, 1)}%.`}>
        ${ticks.map((v) => html`<line class="gr" x1=${L} x2=${W - R} y1=${y(v)} y2=${y(v)} /><text class="ax" x=${L - 5} y=${y(v) + 3} text-anchor="end">${v}%</text>`)}
        ${[0, 50, 100].map((p) => html`<text class="ax" x=${x(p)} y=${H - 5} text-anchor=${p === 0 ? "start" : p === 100 ? "end" : "middle"}>${p}%${p === 0 ? " das seções" : ""}</text>`)}
        <line class="ref50" x1=${L} x2=${W - R} y1=${y(50)} y2=${y(50)} />
        <path d=${linhaD("f")} class="ln" style=${{ "--c": cor(cF.sg) }} />
        <path d=${linhaD("l")} class="ln" style=${{ "--c": cor(cL.sg) }} />
        <line class="cursor-t" x1=${x(atual.pst)} x2=${x(atual.pst)} y1=${T} y2=${H - B} />
        ${serie.map((p) => html`<circle class="pt" cx=${x(p.pst)} cy=${y(p.f)} r="2"><title>${quando(p)} · ${pct(p.pst, 1)}% das seções: ${nF} ${pct(p.f, 2)}%, ${nL} ${pct(p.l, 2)}%</title></circle>`)}
        <circle cx=${x(atual.pst)} cy=${y(atual.f)} r="3.2" style=${{ fill: cor(cF.sg) }} />
        <circle cx=${x(atual.pst)} cy=${y(atual.l)} r="3.2" style=${{ fill: cor(cL.sg) }} />
      </svg>
    </figure>`;
}

// ---------------- resumo por UF (governador, senador)
export function ResumoUFs({ cargo, res, meta, onUF, status, pst }) {
  if (!res) return html`<p class="vazio-txt">Carregando…</p>`;
  const linhas = UFS.map((uf) => ({ uf, r: linha(cargo, res.uf?.[uf], meta.cand[cargo]?.[uf]), of: oficial(status, cargo, uf, meta.cand[cargo]?.[uf]) })).filter((x) => x.r && x.r.lider);
  const cont = {};
  // senador: vagas pelos eleitos oficiais (sem situação oficial, pelos 2 mais votados); governador: 1º colocado
  const senadores = (x) => senadoEleitos(x.of, pst) || x.r.cands.slice(0, 2);
  if (cargo === "senador") linhas.forEach((x) => senadores(x).forEach((c) => { cont[c.sg] = (cont[c.sg] || 0) + 1; }));
  else linhas.forEach(({ r }) => { cont[r.lider.sg] = (cont[r.lider.sg] || 0) + 1; });
  const ranking = Object.entries(cont).sort((a, b) => b[1] - a[1]);
  const max = ranking[0]?.[1] || 1;
  const com = linhas.filter((x) => x.of?.status);
  const eleitos = com.filter((x) => x.of.status === "eleito").length, t2 = com.filter((x) => x.of.status === "2turno").length;
  const oficialSen = linhas.every((x) => senadoEleitos(x.of, pst));
  const titulo = cargo === "senador"
    ? html`${ranking[0]?.[0]} ${oficialSen ? "elegeu" : "lidera em"} ${ranking[0]?.[1]} das ${linhas.length * 2} vagas do Senado`
    : com.length === linhas.length
      ? html`${eleitos} estados definiram o governador no 1º turno; ${t2} vão ao 2º turno${linhas.length - eleitos - t2 ? `; ${linhas.length - eleitos - t2} indefinido` : ""}`
      : html`Governadores: quem lidera em cada estado`;
  return html`
    <div class="cab"><p class="kicker">${CARGO_NOME[cargo]} · 27 UFs</p></div>
    <h1 class="manchete pequena">${titulo}</h1>
    <p class="kicker sub">${cargo === "senador" ? "Vagas na frente, por partido" : "Estados com o partido na frente"}</p>
    <ul class="barras">
      ${ranking.slice(0, 8).map(([sg, n]) => html`<li><span class="sg">${sg}</span><span class="tr"><i style=${{ width: (n / max) * 100 + "%", "--c": cor(sg) }}></i></span><b>${n}</b></li>`)}
    </ul>
    <p class="kicker sub">Por estado <small>· toque para ver</small></p>
    <ul class="ufs">
      ${linhas.map(({ uf, r, of }) => html`<li><button type="button" onClick=${() => onUF(uf)}>
        <b>${uf}</b><${Sw} sg=${r.lider.sg} /><span class="nm">${cargo === "senador" ? senadores({ r, of }).map(cartao).join(" e ") : cartao(r.lider)}</span>
        <span class="p">${cargo === "senador" ? r.lider.sg : pct(r.p1 * 100, 1) + "%"}</span>
        ${cargo === "governador" && of?.status && html`<span class=${"st " + (of.status === "eleito" ? "ok" : "t2")}>${of.status === "eleito" ? "eleito" : of.status === "2turno" ? "2º t." : "indef."}</span>`}
      </button></li>`)}
    </ul>`;
}

// ---------------- deputados
export function ResumoDep({ cargo, res, uf, onUF, onVoltar, geo }) {
  if (!res) return html`<p class="vazio-txt">Carregando…</p>`;
  const nomeCasa = cargo === "depfed" ? "Câmara dos Deputados" : "Assembleias Legislativas";
  if (uf) {
    const r = linha(cargo, res.uf?.[uf]);
    if (!r) return html`<p class="vazio-txt">Sem dados para ${UF_NOME[uf]}.</p>`;
    const mus = (geo?.ufs[uf]?.lista || []).map((i) => res.mu?.[geo.muns[i].cod]).filter(Boolean);
    const cont = {}; mus.forEach((m) => { cont[m[1]] = (cont[m[1]] || 0) + 1; });
    const rk = Object.entries(cont).sort((a, b) => b[1] - a[1]); const max = rk[0]?.[1] || 1;
    return html`
      <div class="cab"><p class="kicker">${CARGO_NOME[cargo]} · ${UF_NOME[uf]}</p><button type="button" class="link" onClick=${onVoltar}>← Brasil</button></div>
      <h1 class="manchete pequena"><${Nome} c=${{ nome: r.sg, sg: r.sg }} /> é o partido mais votado ${uf === "DF" && cargo === "depest" ? "para a Câmara Legislativa" : "no estado"}</h1>
      <dl class="totais"><div><dt>Votos nominais do partido</dt><dd>${int(r.partidoV)}</dd></div><div><dt>Dos válidos</dt><dd>${pct(r.partidoP * 100, 1)}%</dd></div><div><dt>Votos válidos</dt><dd>${int(r.validos)}</dd></div></dl>
      <p class="kicker sub">Mais votados no estado</p>
      <ul class="outros">${r.cands.map((c) => html`<li><${Sw} sg=${c.sg} /><span class="nm">${c.nome}<small>${c.sg}</small></span><span class="p">${int(c.v)}</span></li>`)}</ul>
      <p class="kicker sub">Municípios com o partido na frente</p>
      <ul class="barras">${rk.slice(0, 6).map(([sg, n]) => html`<li><span class="sg">${sg}</span><span class="tr"><i style=${{ width: (n / max) * 100 + "%", "--c": cor(sg) }}></i></span><b>${int(n)}</b></li>`)}</ul>`;
  }
  const cont = {}; let tot = 0;
  for (const k in res.mu) { const sg = res.mu[k][1]; cont[sg] = (cont[sg] || 0) + 1; tot++; }
  const rk = Object.entries(cont).sort((a, b) => b[1] - a[1]); const max = rk[0]?.[1] || 1;
  const ufs = UFS.map((u) => ({ uf: u, r: linha(cargo, res.uf?.[u]) })).filter((x) => x.r);
  return html`
    <div class="cab"><p class="kicker">${CARGO_NOME[cargo]} · ${nomeCasa}</p></div>
    <h1 class="manchete pequena"><${Nome} c=${{ nome: rk[0]?.[0] || "", sg: rk[0]?.[0] }} /> é o partido mais votado em ${int(rk[0]?.[1])} dos ${int(tot)} municípios</h1>
    <p class="kicker sub">Municípios com o partido na frente</p>
    <ul class="barras">${rk.slice(0, 8).map(([sg, n]) => html`<li><span class="sg">${sg}</span><span class="tr"><i style=${{ width: (n / max) * 100 + "%", "--c": cor(sg) }}></i></span><b>${int(n)}</b></li>`)}</ul>
    <p class="kicker sub">Mais votado por estado <small>· toque para ver</small></p>
    <ul class="ufs">${ufs.map(({ uf: u, r }) => html`<li><button type="button" onClick=${() => onUF(u)}><b>${u}</b><${Sw} sg=${r.sg} /><span class="nm">${r.cands[0] ? cartao(r.cands[0]) : r.sg}</span><span class="p">${r.sg}</span></button></li>`)}</ul>`;
}

// ---------------- painel direito
export function PorRegiao({ cargo, res, meta, lista, ponto, geo, turno, msg }) {
  if (!res) return html`<p class="vazio-txt">${msg || (turno === 2 ? "Aparece quando o TSE publicar o 2º turno." : "Carregando…")}</p>`;
  let rows;
  if (cargo === "presidente") {
    rows = REGIOES.map(([nome, ufs]) => {
      let r = linha(cargo, somar(ufs.map((u) => res.uf?.[u])), lista);
      if (ponto?.uf) { // aproximação na linha do tempo: média das UFs ponderada pelos válidos finais
        let w = 0, f = 0, l = 0;
        ufs.forEach((u) => { const p = ponto.uf[u], vv = res.uf?.[u]?.[2] || 0; if (p) { w += vv; f += p[1] * vv; l += p[2] * vv; } });
        if (w) { const { F, L } = duelo(lista); const c2 = [{ ...F, p: f / w / 100 }, { ...L, p: l / w / 100 }].sort((a, b) => b.p - a.p); r = { ...r, cands: c2, val: c2 }; }
      }
      return { nome, r };
    });
    const zz = res.uf?.ZZ && linha(cargo, res.uf.ZZ, lista);
    if (zz) rows.push({ nome: "Exterior", r: zz });
    return html`<ul class="regioes">${rows.filter(({ r }) => r && r.lider && r.cands.length >= 2).map(({ nome, r }) => {
      const [a, b] = r.cands; const sald = (a.p - b.p) * 100;
      return html`<li><span class="rn">${nome}</span><span class="ld"><${Sw} sg=${a.sg} /><small>${a.sg}</small> <b>${pct(a.p * 100, 1)}%</b><small class="dv">+${pct(sald, 1)}</small></span>
        <span class="duelo mini" aria-hidden="true"><i style=${{ width: a.p * 100 + "%", "--c": cor(a.sg) }}></i><i class="meio"></i><i style=${{ width: b.p * 100 + "%", "--c": cor(b.sg) }}></i></span></li>`;
    })}</ul>`;
  }
  // demais cargos: partido que lidera mais estados (gov/sen) ou municípios (deputados) em cada região
  rows = REGIOES.map(([nome, ufs]) => {
    const cont = {}; let tot = 0;
    if (ehDep(cargo)) {
      ufs.forEach((u) => (geo?.ufs[u]?.lista || []).forEach((i) => { const m = res.mu?.[geo.muns[i].cod]; if (m) { cont[m[1]] = (cont[m[1]] || 0) + 1; tot++; } }));
    } else {
      ufs.forEach((u) => {
        const r = linha(cargo, res.uf?.[u], meta.cand[cargo]?.[u]); if (!r?.lider) return;
        (cargo === "senador" ? r.cands.slice(0, 2) : [r.lider]).forEach((c) => { cont[c.sg] = (cont[c.sg] || 0) + 1; tot++; });
      });
    }
    const [sg, n] = Object.entries(cont).sort((a, b) => b[1] - a[1])[0] || ["–", 0];
    return { nome, sg, n, tot };
  });
  const und = ehDep(cargo) ? "municípios" : cargo === "senador" ? "vagas" : "estados";
  return html`<ul class="regioes">${rows.map(({ nome, sg, n, tot }) => html`<li><span class="rn">${nome}</span><span class="ld"><${Sw} sg=${sg} /><b>${sg}</b> <small>${int(n)} de ${int(tot)} ${und}</small></span>
    <span class="duelo mini" aria-hidden="true"><i style=${{ width: (tot ? (n / tot) * 100 : 0) + "%", "--c": cor(sg) }}></i></span></li>`)}</ul>`;
}

export function Feed({ itens, onUF, lista }) {
  const [n, setN] = useState(10);
  if (!itens?.length) return html`<p class="vazio-txt">Sem atualizações por enquanto.</p>`;
  return html`<ol class="feed">${itens.slice(0, n).map((it) => html`<li class=${"t-" + it.t}>
    <time title=${it.d ? `${it.d}${it.h ? " " + it.h : ""}` : null}>${it.h || ""}</time><i aria-hidden="true"></i>
    <div>${!it.h && html`<small class="rf">${it.d ? it.d + " · " : ""}resultado final</small>`}
    ${it.uf ? html`<button type="button" class="link" onClick=${() => onUF(it.uf)}>${textoComSigla(it.txt, lista)}</button>` : html`<span>${textoComSigla(it.txt, lista)}</span>`}</div>
  </li>`)}</ol>
  ${itens.length > n && html`<button type="button" class="link" onClick=${() => setN(n + 20)}>Mostrar mais ${Math.min(20, itens.length - n)} atualizações</button>`}`;
}
