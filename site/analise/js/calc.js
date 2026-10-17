// Análise: contas, formatação, escalas e o recorte por UF (sem DOM; testado em calc_test.js).
// Lados: L = campo de Lula, F = campo de Flávio, C = centro/sem lado. Contrato: analise/dados/*.json.

export const LADOS = ["L", "C", "F"]; // ordem visual: esquerda → direita
// partido de Lula e de Flávio: o nome do candidato sempre sai com a sigla (issue #74; tests/test_partido_junto.py
// confere com relatorio/relatorio.json)
export const SIGLA = { L: "PT", F: "PL" };
export const CAND = { L: `Lula (${SIGLA.L})`, F: `Flávio (${SIGLA.F})` };
export const LADO_NOME = { L: `Campo de ${CAND.L}`, C: "Centro/sem lado", F: `Campo de ${CAND.F}` };
export const LADO_MIN = { L: `campo de ${CAND.L}`, C: "centro", F: `campo de ${CAND.F}` }; // no meio da frase
export const LADO_CURTO = { L: CAND.L, C: "Centro", F: CAND.F };
// cor de dado = só tokens de campo da brand (o ciano fica na moldura)
export const LADO_TOKEN = { L: "--lula", C: "--outros", F: "--flavio" };
export const LADO_COR = { L: "var(--lula)", C: "var(--outros)", F: "var(--flavio)" };

export const UF_NOME = {
  AC: "Acre", AL: "Alagoas", AP: "Amapá", AM: "Amazonas", BA: "Bahia", CE: "Ceará", DF: "Distrito Federal", ES: "Espírito Santo",
  GO: "Goiás", MA: "Maranhão", MT: "Mato Grosso", MS: "Mato Grosso do Sul", MG: "Minas Gerais", PA: "Pará", PB: "Paraíba",
  PR: "Paraná", PE: "Pernambuco", PI: "Piauí", RJ: "Rio de Janeiro", RN: "Rio Grande do Norte", RS: "Rio Grande do Sul",
  RO: "Rondônia", RR: "Roraima", SC: "Santa Catarina", SP: "São Paulo", SE: "Sergipe", TO: "Tocantins",
};
export const UFS = Object.keys(UF_NOME).sort();
const UF_COD = {
  11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO", 21: "MA", 22: "PI", 23: "CE", 24: "RN",
  25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR", 42: "SC",
  43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF",
};
/** UF de um código IBGE de 7 dígitos */
export const ufDoCodigo = (cd) => UF_COD[String(cd).slice(0, 2)] || null;
export const nomeRecorte = (uf) => (uf === "BR" ? "Brasil" : UF_NOME[uf] || uf);
/** "no Brasil", "em São Paulo", "no Paraná": preposição certa para manchete */
const ART_F = new Set(["BA", "PB"]), SEM_ART = new Set(["AL", "GO", "MG", "MT", "MS", "PE", "RO", "RR", "SC", "SE", "SP", "TO"]);
export function noRecorte(uf) {
  if (uf === "BR") return "no Brasil";
  const n = UF_NOME[uf] || uf;
  if (ART_F.has(uf)) return `na ${n}`;
  if (SEM_ART.has(uf)) return `em ${n}`;
  return `no ${n}`;
}
/** "do país", "de São Paulo", "da Bahia", "do Paraná" */
export function deRecorte(uf) {
  if (uf === "BR") return "do país";
  return noRecorte(uf).replace(/^no /, "do ").replace(/^na /, "da ").replace(/^em /, "de ");
}

export const CARGOS = [["presidente", "Presidente"], ["governador", "Governador"], ["senador", "Senado"], ["depfed", "Dep. federal"], ["depest", "Dep. estadual"]];
export const CARGO_NOME = Object.fromEntries(CARGOS);
export const CARGO_LONGO = { presidente: "presidente", governador: "governador", senador: "senador", depfed: "deputado federal", depest: "deputado estadual" };
export const CASA_NOME = { depfed: "Câmara dos Deputados", depest: "Assembleias Legislativas", senador: "Senado" };

// ---------------- formatação pt-BR
const nf = (d) => new Intl.NumberFormat("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d });
/** número com d casas */
export const num = (x, d = 0) => (Number.isFinite(x) ? nf(d).format(x) : "–");
/** inteiro com separador de milhar */
export const int = (x) => (Number.isFinite(x) ? nf(0).format(Math.round(x)) : "–");
/** proporção 0–1 → "45,2%" */
export const pct = (p, d = 1) => (Number.isFinite(p) ? `${nf(d).format(p * 100)}%` : "–");
/** diferença de proporções → "+3,1 p.p." */
export const pp = (x, d = 1) => (Number.isFinite(x) ? `${x > 0 ? "+" : x < 0 ? "−" : ""}${nf(d).format(Math.abs(x * 100))} p.p.` : "–");
/** quantidade de pessoas/votos em leitura rápida: "7,2 mi", "850 mil", "1.234" */
export function mi(x) {
  if (!Number.isFinite(x)) return "–";
  const a = Math.abs(x);
  if (a >= 1e6) return `${nf(a >= 1e8 ? 0 : 1).format(x / 1e6)} mi`;
  if (a >= 1e4) return `${nf(0).format(x / 1e3)} mil`;
  return int(x);
}

/** "1,2 milhão de votos", "850.000 votos" */
export function votosTxt(v) {
  if (!Number.isFinite(v)) return "–";
  if (v >= 1e6) { const m = Math.round(v / 1e5) / 10; return `${num(m, m % 1 ? 1 : 0)} ${m < 2 ? "milhão" : "milhões"} de votos`; }
  return `${int(v)} ${v === 1 ? "voto" : "votos"}`;
}

// ---------------- escalas
/** escala linear; .inv faz o caminho inverso */
export function escala(dom, ran) {
  const [d0, d1] = dom, [r0, r1] = ran;
  const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
  const f = (x) => r0 + (x - d0) * k;
  f.inv = (y) => (k ? d0 + (y - r0) / k : d0);
  f.dom = dom; f.ran = ran;
  return f;
}
/** passo "redondo" (1, 2, 2,5, 5 × 10^n) para cerca de n marcas */
export function passo(max, n = 5) {
  if (!(max > 0)) return 1;
  const bruto = max / n, e = Math.pow(10, Math.floor(Math.log10(bruto))), f = bruto / e;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * e;
}
/** marcas de 0 até cobrir max */
export function marcas(max, n = 5) {
  const s = passo(max, n), out = [];
  for (let v = 0; v <= max + s * 1e-9; v += s) out.push(+v.toPrecision(12));
  if (out[out.length - 1] < max) out.push(+(out[out.length - 1] + s).toPrecision(12));
  return out;
}
/** teto "redondo" para o eixo */
export const teto = (max, n = 5) => { const m = marcas(max, n); return m[m.length - 1] || 1; };

// ---------------- leitura tolerante do contrato
const soma = (o) => LADOS.reduce((s, k) => s + (+o?.[k] || 0), 0);
/** {L,F,C} absolutos → proporções que somam 1 */
export function partes(o) {
  const t = soma(o);
  return Object.fromEntries(LADOS.map((k) => [k, t ? (+o?.[k] || 0) / t : 0]));
}
/** intervalo de uma estimativa em proporção: o contrato traz [lo,hi]; se vier em votos, converte por v/pct */
export function intervaloPct(it) {
  if (!it || !Array.isArray(it.int)) return null;
  let [lo, hi] = it.int;
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return null;
  if (Math.max(Math.abs(lo), Math.abs(hi)) > 1.0001) {
    if (!(it.v > 0) || !(it.pct > 0)) return null;
    const base = it.v / it.pct; lo /= base; hi /= base;
  }
  return [Math.min(lo, hi), Math.max(lo, hi)];
}
/** intervalo em pessoas (para "entre 6,1 e 8,4 mi") */
export function intervaloV(it) {
  const p = intervaloPct(it);
  if (!p || !(it.v > 0) || !(it.pct > 0)) return null;
  const base = it.v / it.pct;
  return [p[0] * base, p[1] * base];
}
const lista = (x) => (Array.isArray(x) ? x : x && typeof x === "object" ? Object.values(x).find(Array.isArray) || [] : []);
const ufsDe = (obj) => (obj ? Object.keys(obj).filter((k) => UF_NOME[k]) : []);

// ---------------- seções (cada uma devolve o modelo já recortado para a UF, ou null sem dado)
const vazio = (uf) => ({ ok: false, uf });

export function secCampos(D, uf) {
  const c = D.campos?.[uf];
  if (!c) return vazio(uf);
  const linhas = CARGOS.filter(([k]) => c[k]).map(([k, nome]) => ({
    cargo: k, nome, votos: Object.fromEntries(LADOS.map((l) => [l, +c[k][l] || 0])), p: partes(c[k]),
    validos: c[k].validos, porEleitor: c[k].votos_por_eleitor || 1,
  }));
  const pres = linhas.find((l) => l.cargo === "presidente"), dep = linhas.find((l) => l.cargo === "depfed");
  const dif = pres && dep ? pres.p.L - dep.p.L : null;
  return {
    ok: linhas.length > 0, uf, linhas, dif,
    titulo: pres && dep
      ? `${LADO_NOME.L}: ${pct(pres.p.L)} dos votos para presidente e ${pct(dep.p.L)} para deputado federal ${noRecorte(uf)}`
      : `Votos por campo e cargo ${noRecorte(uf)}`,
    numero: dif != null ? pp(-dif) : "–",
    rotulo: `do voto em presidente para o voto em deputado federal, no ${LADO_MIN.L}`,
  };
}

const DESTINOS = { lula: ["F", "C", "L"], flavio: ["L", "C", "F"] };
export function secDividido(D, uf, cargo = "depfed") {
  const d = D.dividido?.[uf]?.[cargo];
  if (!d) return vazio(uf);
  if (d.poucos_municipios) {
    const n = d.n_mun ?? 1;
    return {
      ok: true, uf, cargo, grupos: [], est: true, poucos: true, metodo: D.dividido?.metodo || "",
      titulo: `Voto dividido não pode ser estimado ${uf === "DF" ? "no DF" : noRecorte(uf)} (${int(n)} ${n === 1 ? "município" : "municípios"})`,
      numero: "–", rotulo: "",
      nota: `A estimativa compara municípios entre si; com ${n === 1 ? "um município só" : "tão poucos municípios"} não há variação para medir. Os limites possíveis (Duncan-Davis) vão de quase nada a quase tudo, então o número não é mostrado.`,
    };
  }
  const grupos = ["lula", "flavio"].map((q) => ({
    quem: q, nome: q === "lula" ? `Eleitores de ${CAND.L}` : `Eleitores de ${CAND.F}`,
    itens: DESTINOS[q].map((dst) => {
      const it = d[`${q}_para_${dst}`];
      return it ? { dst, v: it.v, p: it.pct, int: intervaloPct(it), intV: intervaloV(it) } : null;
    }).filter(Boolean),
  }));
  const lf = grupos[0].itens.find((x) => x.dst === "F");
  const outro = grupos[0].itens.filter((x) => x.dst !== "L").reduce((s, x) => s + (x.p || 0), 0);
  return {
    ok: !!lf, uf, cargo, grupos, est: true, metodo: D.dividido?.metodo || "",
    titulo: lf ? `Estimativa: ${num(outro * 10, 0)} em cada 10 eleitores de ${CAND.L} votaram em ${CARGO_LONGO[cargo]} fora do campo dele ${noRecorte(uf)}` : "",
    numero: lf ? mi(lf.v) : "–",
    rotulo: lf ? `eleitores de ${CAND.L} votaram em ${CARGO_LONGO[cargo]} do ${LADO_MIN.F}${lf.intV ? ` (faixa de ${mi(lf.intV[0])} a ${mi(lf.intV[1])})` : ""}` : "",
  };
}

export function secCadeiras(D, uf) {
  const c = D.cadeiras?.[uf];
  if (!c) return vazio(uf);
  const casas = ["depfed", "depest", "senador"].filter((k) => c[k]).map((k) => {
    const tot = c[k].total || soma(c[k].cadeiras) || 1;
    return { casa: k, nome: CASA_NOME[k], total: tot, votos: partes(c[k].votos), cadeiras: Object.fromEntries(LADOS.map((l) => [l, +c[k].cadeiras?.[l] || 0])),
      pc: Object.fromEntries(LADOS.map((l) => [l, (+c[k].cadeiras?.[l] || 0) / tot])) };
  });
  const cam = casas.find((x) => x.casa === "depfed") || casas[0];
  return {
    ok: !!cam, uf, casas,
    titulo: cam ? `${LADO_NOME.L}: ${pct(cam.votos.L)} dos votos e ${pct(cam.pc.L)} das cadeiras ${cam.casa === "depfed" ? (uf === "BR" ? "da Câmara" : `da bancada ${uf === "DF" ? "do DF" : "de " + uf} na Câmara`) : "em " + cam.nome}` : "",
    numero: cam ? `${int(cam.cadeiras.L)} de ${int(cam.total)}` : "–",
    rotulo: cam ? `cadeiras ${cam.casa === "depfed" ? "de deputado federal" : "em " + cam.nome} para o ${LADO_MIN.L}` : "",
  };
}

export const CARGOS_DIV = ["depfed", "depest", "senador", "governador"];
export function secDivergencias(D, uf, cargo = "depfed") {
  const dv = D.divergencias;
  if (!dv) return vazio(uf);
  const porUF = UFS.map((u) => {
    const x = dv.uf?.[u]?.[cargo];
    return x ? { uf: u, div: x.divergentes, total: x.total, p: x.total ? x.divergentes / x.total : 0 } : null;
  }).filter(Boolean);
  const alvo = uf === "BR" ? porUF : porUF.filter((x) => x.uf === uf);
  const div = alvo.reduce((s, x) => s + x.div, 0), tot = alvo.reduce((s, x) => s + x.total, 0);
  const rk = lista(dv.ranking?.[cargo]).filter((x) => uf === "BR" || x.uf === uf);
  const dir = { LF: 0, FL: 0, LC: 0, FC: 0 };
  if (dv.mu) for (const [cd, m] of Object.entries(dv.mu)) {
    if (uf !== "BR" && ufDoCodigo(cd) !== uf) continue;
    // mesma regra de analise/calcular.py e do HUD: presidente com Lula ou Flávio (empate = C fica fora)
    if (m.pres !== "C" && m[cargo] && m[cargo] !== m.pres) dir[m.pres + m[cargo]] = (dir[m.pres + m[cargo]] || 0) + 1;
  }
  return {
    ok: tot > 0, uf, cargo, porUF, div, tot, p: tot ? div / tot : 0, ranking: rk, dir,
    titulo: tot ? `Em ${int(div)} de ${int(tot)} municípios ${deRecorte(uf)}, o lado que venceu para presidente não venceu para ${CARGO_LONGO[cargo]}` : "",
    numero: tot ? pct(div / tot, 0) : "–",
    rotulo: `dos municípios com lados diferentes para presidente e ${CARGO_LONGO[cargo]}`,
  };
}

export function secComparacao(D, uf) {
  const c = D.comparacao2022;
  if (!c) return vazio(uf);
  let lf = 0, bl = 0, n = 0;
  if (c.mu) for (const [cd, m] of Object.entries(c.mu)) {
    if (uf !== "BR" && ufDoCodigo(cd) !== uf) continue;
    n++;
    if (m.pres22 === "L" && m.pres26 === "F") lf++;
    else if (m.pres22 === "B" && m.pres26 === "L") bl++;
  }
  if (uf === "BR" && c.viradas) { lf = c.viradas.lula_para_flavio ?? lf; bl = c.viradas.bolsonaro_para_lula ?? bl; }
  const agg = c[uf];
  const leg = agg?.depfed22 && agg?.depfed26 ? LADOS.map((l) => ({ lado: l, a: partes(agg.depfed22)[l], b: partes(agg.depfed26)[l] })) : null;
  const pres = agg && Number.isFinite(agg.pres22_pct_lula) && Number.isFinite(agg.pres26_pct_lula) ? { a: agg.pres22_pct_lula, b: agg.pres26_pct_lula } : null;
  const rk = lista(c.ranking).filter((x) => uf === "BR" || x.uf === uf || ufDoCodigo(x.cd) === uf);
  return {
    ok: n > 0 || !!agg, uf, lf, bl, n, leg, pres, ranking: rk,
    titulo: `${int(lf)} ${lf === 1 ? "município votou" : "municípios votaram"} em ${CAND.L} em 2022 e em ${CAND.F} em 2026${uf === "BR" ? "" : " " + noRecorte(uf)}; ${int(bl)} fizeram o caminho inverso`,
    numero: int(lf),
    rotulo: `municípios trocaram Lula (2022) por Flávio (2026), de ${SIGLA.L} para ${SIGLA.F}`,
  };
}

/** pesquisas: as depois do 1º turno primeiro; dentro de cada grupo, a mais recente primeiro (data "DD/MM") */
export function ordenaPesquisas(ps) {
  const k = (p) => { const [d, m] = String(p.data || "").split("/").map(Number); return (m || 0) * 100 + (d || 0); };
  return [...(ps || [])].sort((a, b) => (!!a.antes_1t - !!b.antes_1t) || k(b) - k(a));
}

export function secCenarios(D) {
  const c = D.cenarios;
  if (!c) return vazio("BR");
  const pl = c.precisa?.lula_pct_dos_eliminados, pf = c.precisa?.flavio_pct_dos_eliminados;
  const elim = [...(c.eliminados || [])].sort((a, b) => b.votos - a.votos);
  const total = elim.reduce((s, e) => s + (e.votos || 0), 0);
  return {
    ok: true, uf: "BR", est: true, pl, pf, eliminados: elim, totalElim: total, pesquisas: ordenaPesquisas(c.pesquisas), cenarios: c.cenarios || [],
    titulo: Number.isFinite(pl) ? `Cenário: ${CAND.L} precisa de ${pct(pl, 0)} dos votos dos eliminados para virar; ${CAND.F}, de ${pct(pf, 0)} para manter a frente` : "Cenários do 2º turno",
    numero: Number.isFinite(pl) ? pct(pl, 0) : "–",
    rotulo: `dos votos dos candidatos eliminados (${mi(total)}) é o que ${CAND.L} precisa para virar, se os eleitores dos dois repetirem o voto`,
  };
}

export function secBrancos(D, uf) {
  const b = D.brancos?.[uf];
  if (!b) return vazio(uf);
  const itens = CARGOS.filter(([k]) => b[k]).map(([k, nome]) => {
    // base = votos possíveis: no Senado cada eleitor teve 2 votos (comparecimento × votos_por_eleitor)
    const x = b[k], comp = (x.comparecimento || 1) * (x.votos_por_eleitor || 1);
    return { cargo: k, nome, brancos: x.brancos, nulos: x.nulos, comp: x.comparecimento, base: comp, porEleitor: x.votos_por_eleitor || 1, pb: x.brancos / comp, pn: x.nulos / comp, p: (x.brancos + x.nulos) / comp };
  });
  const pres = itens.find((i) => i.cargo === "presidente"), dep = itens.find((i) => i.cargo === "depfed");
  const max = itens.reduce((m, i) => (i.p > (m?.p ?? -1) ? i : m), null);
  return {
    ok: itens.length > 0, uf, itens, max,
    titulo: pres && dep ? `${pct(dep.p)} dos votos para deputado federal foram brancos ou nulos ${noRecorte(uf)}, contra ${pct(pres.p)} para presidente` : "",
    numero: max ? pct(max.p) : "–",
    rotulo: max ? `brancos e nulos em ${CARGO_LONGO[max.cargo]}, o cargo com mais` : "",
  };
}

export function secFragmentacao(D, uf) {
  const f = D.fragmentacao?.[uf];
  if (!f) return vazio(uf);
  const casas = ["depfed", "depest"].filter((k) => f[k]).map((k) => ({ casa: k, nome: CASA_NOME[k], ...f[k] }));
  const cam = casas[0];
  return {
    ok: !!cam, uf, casas,
    titulo: cam ? `${cam.casa === "depfed" ? (uf === "BR" ? "A Câmara" : `A bancada ${uf === "DF" ? "do DF" : "de " + uf}`) : "A Assembleia"} tem ${num(cam.nep, 1)} partidos efetivos; o centro tem ${pct(cam.centro_pct_votos, 0)} dos votos e ${pct(cam.centro_pct_cadeiras, 0)} das cadeiras` : "",
    numero: cam ? num(cam.nep, 1) : "–",
    rotulo: "partidos efetivos (índice de Laakso-Taagepera)",
  };
}

export function secLegenda(D, uf) {
  const l = D.legenda?.[uf];
  if (!l) return vazio(uf);
  const casas = ["depfed", "depest"].filter((k) => l[k]).map((k) => ({ casa: k, nome: CARGO_NOME[k], total: l[k].total, ...Object.fromEntries(LADOS.map((x) => [x, l[k][x]])) }));
  const cam = casas[0];
  const lider = cam ? LADOS.reduce((a, b) => ((cam[b] ?? 0) > (cam[a] ?? 0) ? b : a), "L") : null;
  return {
    ok: !!cam, uf, casas,
    titulo: cam ? `${pct(cam.total)} dos votos para ${CARGO_LONGO[cam.casa]} ${noRecorte(uf)} foram só no número do partido; o ${LADO_MIN[lider]} é quem mais vota na legenda` : "",
    numero: cam ? pct(cam.total) : "–",
    rotulo: `dos votos para ${cam ? CARGO_LONGO[cam.casa] : ""} foram de legenda`,
  };
}

export function secPuxadores(D, uf, cargo = "depfed") {
  const p = D.puxadores?.[cargo];
  if (!p) return vazio(uf);
  const itens = p.filter((x) => uf === "BR" || x.uf === uf);
  const top = itens[0];
  return {
    ok: true, uf, cargo, itens, vazioUF: !itens.length,
    titulo: top ? `${top.nome} (${top.partido}-${top.uf}) teve ${votosTxt(top.votos)}, ${num(top.votos / (top.quociente || 1), 1)} vezes o quociente eleitoral` : `Nenhum dos 30 mais votados para ${CARGO_LONGO[cargo]} é ${deRecorte(uf)}`,
    numero: top ? `${int(top.puxados_estimados)}` : "–",
    rotulo: top ? `colegas de partido eleitos com a sobra de votos de ${top.nome} (${top.partido}) (estimativa)` : "",
    est: true,
  };
}

/** ordem e títulos das seções da página (id = âncora) */
export const SECOES = [
  ["destaques", "Destaques"], ["campos", "Votos por campo e cargo"], ["voto-dividido", "Voto dividido"],
  ["votos-cadeiras", "Votos × cadeiras"], ["divergencias", "Divergências"], ["comparacao-2022", "2022 × 2026"],
  ["cenarios-2-turno", "Cenários do 2º turno"], ["brancos-nulos", "Brancos e nulos"], ["fragmentacao", "Fragmentação"],
  ["legenda", "Voto de legenda"], ["puxadores", "Puxadores de voto"], ["faq", "Perguntas frequentes"], ["metodo", "Método"],
];

/** o recorte inteiro: tudo o que a página mostra para a UF escolhida (BR = Brasil) */
export function recorte(D, uf = "BR", op = {}) {
  const u = uf === "BR" || UF_NOME[uf] ? uf : "BR";
  return {
    uf: u,
    campos: secCampos(D, u),
    dividido: secDividido(D, u, op.cargoDividido || "depfed"),
    cadeiras: secCadeiras(D, u),
    divergencias: secDivergencias(D, u, op.cargoDiv || "depfed"),
    comparacao: secComparacao(D, u),
    cenarios: secCenarios(D),
    brancos: secBrancos(D, u),
    fragmentacao: secFragmentacao(D, u),
    legenda: secLegenda(D, u),
    puxadores: secPuxadores(D, u, op.cargoPux || "depfed"),
  };
}

/** lado de um partido em 2026 (ou 2022), com a exceção da UF quando houver; sem classificação = centro */
export function ladoDe(D, sg, uf, ano = "2026") {
  const x = D.lados?.[ano]?.[sg];
  if (!x) return "C";
  return (uf && x.uf?.[uf]) || x.lado || "C";
}

/** UFs que existem nos dados (para o seletor) */
export const ufsDisponiveis = (D) => UFS.filter((u) => D.campos?.[u] || D.cadeiras?.[u] || D.brancos?.[u] || ufsDe(D.divergencias?.uf).includes(u));
