// Contas e textos do HUD (sem DOM): normaliza o formato do contrato, cores por modo, resumos.
import { corRGB, corCSS, misturar, token } from "./partidos.js";

export const UF_NOME = {
  AC: "Acre", AL: "Alagoas", AP: "Amapá", AM: "Amazonas", BA: "Bahia", CE: "Ceará", DF: "Distrito Federal", ES: "Espírito Santo",
  GO: "Goiás", MA: "Maranhão", MT: "Mato Grosso", MS: "Mato Grosso do Sul", MG: "Minas Gerais", PA: "Pará", PB: "Paraíba",
  PR: "Paraná", PE: "Pernambuco", PI: "Piauí", RJ: "Rio de Janeiro", RN: "Rio Grande do Norte", RS: "Rio Grande do Sul",
  RO: "Rondônia", RR: "Roraima", SC: "Santa Catarina", SP: "São Paulo", SE: "Sergipe", TO: "Tocantins", ZZ: "Exterior",
};
export const UFS = Object.keys(UF_NOME).filter((u) => u !== "ZZ").sort();
export const REGIOES = [
  ["Norte", ["AC", "AM", "AP", "PA", "RO", "RR", "TO"]],
  ["Nordeste", ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"]],
  ["Centro-Oeste", ["DF", "GO", "MS", "MT"]],
  ["Sudeste", ["ES", "MG", "RJ", "SP"]],
  ["Sul", ["PR", "RS", "SC"]],
];
export const CARGOS = [
  ["presidente", "Presidente"], ["governador", "Governadores"], ["senador", "Senado"],
  ["depfed", "Dep. Federal"], ["depest", "Dep. Estadual"],
];
export const CARGO_NOME = Object.fromEntries(CARGOS);
export const MODOS = [["municipios", "Municípios"], ["estados", "Estados"], ["vantagem", "Vantagem"], ["apurado", "Apurado"], ["divergencia", "Divergência"]];

// ---------- modo Divergência (dados da Análise: /analise/dados/divergencias.json)
// Lados: L = campo de Lula, F = campo de Flávio, C = centro/sem lado. Cor só por token de campo.
export const LADO_TOKEN = { L: "--lula", F: "--flavio", C: "--outros" };
export const LADO_NOME = { L: "campo de Lula (PT)", F: "campo de Flávio (PL)", C: "centro" };
/** cargo legislativo comparado com presidente: o do recorte, ou deputado federal quando o recorte é presidente */
export const cargoDivergencia = (cargo) => (cargo === "presidente" ? "depfed" : cargo);
/** {pres, leg, diverge} de um município (m = divergencias.mu[cod]); null sem dado ou com empate para presidente
 *  (pres = "C"). Divergente = presidente com Lula ou Flávio e o cargo com outro lado, inclusive o centro. */
export function divergencia(m, cargo) {
  const c = cargoDivergencia(cargo);
  if (!m || !m.pres || m.pres === "C" || !m[c]) return null;
  return { pres: m.pres, leg: m[c], diverge: m[c] !== m.pres };
}

/** contagem do modo Divergência: n divergentes de t municípios com dado no cargo (mesma base da /analise/);
 *  empates = municípios com empate para presidente (contam no total, nunca como divergentes) */
export function contaDivergencia(mu, cargo) {
  const c = cargoDivergencia(cargo); let n = 0, t = 0, empates = 0;
  for (const m of Object.values(mu || {})) {
    if (!m || !m.pres || !m[c]) continue;
    t++;
    if (m.pres === "C") { empates++; continue; }
    if (m[c] !== m.pres) n++;
  }
  return { n, t, empates };
}

// ---------- formatação pt-BR
export const pct = (x, d = 1) => (Number.isFinite(x) ? x.toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d }) : "–");
export const int = (x) => (Number.isFinite(x) ? Math.round(x).toLocaleString("pt-BR") : "–");
const PART = new Set(["de", "da", "do", "dos", "das", "e", "d'"]);
/** "ABIDJÃ" → "Abidjã"; nomes já em caixa de título passam intactos */
export const titulo = (s) => (s && s === s.toUpperCase()
  ? s.toLowerCase().split(" ").map((w, i) => (i && PART.has(w) ? w : w.charAt(0).toUpperCase() + w.slice(1))).join(" ")
  : s || "");
export const semAcento = (s) => String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
export const primeiroNome = (n) => {
  const p = String(n).split(" ");
  return p.length > 2 ? p.slice(0, 2).join(" ") : n;
};

const comPartido = (c) => Boolean(c.sg) && c.sg !== c.nome;
/** partido junto do nome, em texto corrido: "Flávio Bolsonaro (PL)"; `curto` usa só o 1º nome. Sem duplicar quando o nome já é a sigla. */
export const comSigla = (c, curto) => {
  const n = curto ? String(c.nome).split(" ")[0] : c.nome;
  return comPartido(c) ? `${n} (${c.sg})` : n;
};
/** texto pronto de outra fonte (títulos de /analise/dados/destaques.json): "Lula" vira "Lula (PT)" e "Flávio" vira "Flávio (PL)",
 *  com a sigla do dado (`lista`). Quem já vem com a sigla ou com o sobrenome fica como está; os dados publicados não mudam. */
export function textoComSigla(txt, lista) {
  const { F, L } = duelo(lista), sg = { Flávio: F.sg, Lula: L.sg };
  return String(txt ?? "").replace(/(?<![\p{L}\d])(Flávio|Lula)(?![\p{L}\d]| \p{Lu}| da Silva| \()/gu, (_, n) => `${n} (${sg[n]})`);
}
/** partido junto do nome, em cartão, legenda e dica: "Flávio · PL" */
export const cartao = (c) => (comPartido(c) ? `${String(c.nome).split(" ")[0]} · ${c.sg}` : c.nome);

const CURTA = { REPUBLICANOS: "REPUB", SOLIDARIEDADE: "SD", CIDADANIA: "CID", DEMOCRATA: "DEM", MOBILIZA: "MOB" };
/** sigla curta para rótulos no mapa */
export const curta = (sg) => CURTA[sg] || sg;

export const ehDep = (c) => c === "depfed" || c === "depest";

/**
 * Resultado normalizado de uma linha do contrato.
 * pres/gov/sen: [eleitores, comparecimento, validos, brancos, nulos, [votos...]] com candidatos de `lista`
 * dep: [validos, "PL", votos_partido_top, [["Nome","PL",votos],...]]
 */
export function linha(cargo, row, lista) {
  if (!row) return null;
  if (ehDep(cargo)) {
    const [vv, sg, vp, top] = row;
    const cands = (top || []).map(([nome, s, v]) => ({ nome, sg: s, v, p: vv ? v / vv : 0 }));
    return { dep: true, val: cands, validos: vv, sg, partidoV: vp, partidoP: vv ? vp / vv : 0, cands, lider: { sg }, p1: vv ? vp / vv : 0, margem: null };
  }
  // [eleitores, comparecimento, validos, brancos, nulos, [votos], vansj]
  // Semântica do TSE: votos anulados sub judice (vansj) entram no total até o julgamento.
  // % = votos / (validos + vansj); candidato "sj" tem % e etiqueta. Líder = mais votado (inclusive sj).
  // "Eleito" / "2º turno" NUNCA sai daqui: vem de /hud/status.json (situação oficial).
  const [el, comp, vv, vb, vn, votos, vansj = 0] = row;
  const cands = (lista || []).map((c, i) => ({ ...c, v: votos?.[i] || 0 }));
  const base = (vv + vansj) || cands.reduce((s, c) => s + c.v, 0) || 1;
  cands.forEach((c) => { c.p = c.v / base; });
  cands.sort((a, b) => b.v - a.v);
  // nenhum voto apurado ainda (2º turno antes das primeiras seções): ninguém lidera, sem cor no mapa
  const vazio = !cands.some((c) => c.v > 0);
  const [a, b] = vazio ? [] : cands;
  return {
    eleitores: el, comparecimento: comp, validos: vv, brancos: vb, nulos: vn, vansj, total: base, cands, val: cands,
    lider: a || null, segundo: b || null, p1: a ? a.p : 0, margem: a ? a.p - (b ? b.p : 0) : 0, vazio,
    pc: el ? comp / el : 0, pbn: comp ? (vb + vn) / comp : 0,
  };
}

const lim = (x) => Math.max(0, Math.min(1, x));

/** intensidade (0..1) da cor de um resultado em cada modo */
export function intensidade(modo, r, cargo) {
  if (!r) return 0;
  if (modo === "vantagem") return r.margem == null ? 0.35 + 0.65 * lim((r.p1 - 0.1) / 0.3) : 0.12 + 0.88 * lim(r.margem / 0.45);
  if (ehDep(cargo)) return 0.42 + 0.58 * lim((r.p1 - 0.08) / 0.35);
  return 0.42 + 0.58 * lim((r.p1 - 0.3) / 0.4);
}

/** cor de preenchimento de canvas para um resultado */
export function corPara(modo, r, cargo, pstFrac = 1) {
  if (!r) return null;
  if (modo !== "apurado" && !r.lider) return null; // sem voto: cor de "sem dado", não a do 1º da lista
  const bg = token("--bg");
  if (modo === "apurado") return misturar(token("--ink2"), bg, 0.12 + 0.75 * lim(pstFrac));
  return misturar(corRGB(r.lider?.sg), bg, intensidade(modo, r, cargo));
}

export const cor = corCSS;

// Na série do 1º turno, "f" e "l" são Flávio (22) e Lula (13): acha pelo NÚMERO, nunca pela posição na lista
export const N_FLAVIO = "22", N_LULA = "13";
export function duelo(lista) {
  const por = (n) => (lista || []).find((c) => String(c.n) === n);
  return { F: por(N_FLAVIO) || { n: N_FLAVIO, nome: "Flávio Bolsonaro", sg: "PL" }, L: por(N_LULA) || { n: N_LULA, nome: "Lula", sg: "PT" } };
}

/** linha de UF a partir de um ponto da série: [pst, f, l] */
export function linhaSerie(uf3, lista) {
  if (!uf3) return null;
  const [pst, f, l] = uf3;
  const { F, L } = duelo(lista);
  const cands = [{ ...F, p: f / 100 }, { ...L, p: l / 100 }].sort((a, b) => b.p - a.p);
  return { cands, val: cands, lider: cands[0], segundo: cands[1], p1: cands[0].p, margem: cands[0].p - cands[1].p, pst };
}

/** soma linhas no formato [el, comp, vv, vb, vn, [votos], vansj] */
export function somar(rows) {
  const out = [0, 0, 0, 0, 0, [], 0];
  for (const r of rows) {
    if (!r) continue;
    for (let i = 0; i < 5; i++) out[i] += r[i] || 0;
    r[5].forEach((v, i) => { out[5][i] = (out[5][i] || 0) + v; });
    out[6] += r[6] || 0;
  }
  return out;
}

export const fundo = () => token("--bg");

/**
 * Situação oficial (de /hud/status.json, gerado do relatorio.json no build).
 * Devolve {status, a, b, eleitos} com os candidatos já resolvidos pela lista, ou null.
 * Os números de candidato identificam a pessoa (nomes podem vir com acentuação diferente).
 */
export function oficial(status, cargo, uf, lista) {
  const e = status?.[cargo]?.[uf || "BR"];
  if (!e || !lista) return null;
  const por = (n) => lista.find((c) => String(c.n) === String(n)) || null;
  return { status: e.status || null, a: por(e.a), b: por(e.b), eleitos: (e.eleitos || []).map(por).filter(Boolean) };
}

/**
 * Senado: "eleito(s)" só com a situação oficial (status.json) E a apuração em 100%. Devolve a lista de eleitos ou null.
 * Leitura parcial nunca anuncia eleito, mesmo que o status.json diga.
 */
export function senadoEleitos(of, pst) {
  return of?.eleitos?.length && pst === 100 ? of.eleitos : null;
}

/** 2º turno: o modo Apurado depende do `pm` (% por município); leitura sem `pm` volta para Municípios. */
export function modoValido(modo, turno, fonte) {
  if (modo === "divergencia" && turno === 2) return "municipios"; // divergência é do 1º turno (presidente × legislativo)
  return modo === "apurado" && turno === 2 && fonte && !fonte.pm ? "municipios" : modo;
}

/**
 * 2º turno, presidente: de onde vem o dado do recorte.
 * Sem minuto escolhido (idx null): o ao vivo. Com minuto: só o agora.json DAQUELE minuto; enquanto carrega ou se
 * falhou, nada (nunca o ao vivo disfarçado de minuto passado). `erro` = o minuto escolhido não carregou.
 */
export function fonteTurno2(idx, tSel, minuto, vivoDados) {
  if (idx == null) return { fonte: vivoDados || null, erro: false, carregando: false };
  const deste = minuto && minuto.t === tSel;
  if (deste && minuto.dados) return { fonte: minuto.dados, erro: false, carregando: false };
  if (deste && minuto.erro) return { fonte: null, erro: true, carregando: false };
  return { fonte: null, erro: false, carregando: true };
}

/** texto do aviso para leitor de tela (aria-live): segue a UF escolhida, inclusive na linha do tempo */
export function resumoLeitor({ turno, temVivo, fonte, meta, cargo, ponto, pontoUF, ufSel, lista }) {
  if (turno === 2 && !temVivo) return "2º turno: aguardando o TSE, 25 de outubro a partir das 17h.";
  if (!fonte || !meta) return "Carregando resultados.";
  if (cargo !== "presidente") {
    return `${CARGO_NOME[cargo]}${ufSel ? " em " + UF_NOME[ufSel] : ""}. Mapa colorido pelo ${ehDep(cargo) ? "partido mais votado" : "partido do 1º colocado"} em cada município.`;
  }
  const onde = ufSel ? ` em ${UF_NOME[ufSel]}` : "";
  if (ponto) {
    const d = ponto.d ? ponto.d + " " : "";
    const { F, L } = duelo(lista), fl = comSigla(F, true), lu = comSigla(L, true);
    if (!ufSel) return `Presidente em ${d}${ponto.ht}, ${pct(ponto.pst, 1)}% das seções: ${fl} ${pct(ponto.f, 2)}%, ${lu} ${pct(ponto.l, 2)}%.`;
    const u = pontoUF?.uf?.[ufSel];
    if (!u) return `Presidente${onde}: o TSE não tinha publicado esta UF às ${ponto.ht}.`;
    return `Presidente${onde} em ${d}${pontoUF.ufDe || ponto.ht}, ${pct(u[0], 1)}% das seções: ${fl} ${pct(u[1], 2)}%, ${lu} ${pct(u[2], 2)}%.`;
  }
  const r = linha("presidente", ufSel ? fonte.uf?.[ufSel] : fonte.br, lista);
  const apurado = turno === 2 ? `, ${fonte.t ? "às " + fonte.t + ", " : ""}${pct((ufSel ? fonte.pu?.[ufSel] : null) ?? fonte.pst ?? 0, 1)}% das seções` : "";
  if (!r) return `Presidente${onde}: sem dados.`;
  if (r.vazio) return `Presidente, ${turno}º turno${onde}${apurado}: nenhum voto apurado ainda.`;
  const el = turno === 2 && !ufSel ? eleitoTurno2(fonte, lista) : null;
  const placar = r.cands.slice(0, 2).map((c) => `${comSigla(c)} ${pct(c.p * 100, 2)}%`).join(", ");
  if (el) return `${comSigla(el)} é eleito presidente (TSE)${apurado}: ${placar}.`;
  return `Presidente, ${turno}º turno${onde}${apurado}: ${placar}.`;
}

/**
 * Pontos da linha do tempo do 2º turno a partir de /vivo/serie/index.json ({t, pst, br}). Leitura sem voto válido
 * (abertura, 0% das seções) fica de fora: não há % para desenhar e ela achataria o gráfico em 0%.
 */
export function serieTurno2(indice, cand) {
  const c = cand || [], { F, L } = duelo(c);
  const pos = (x) => c.findIndex((k) => String(k.n) === String(x.n));
  return (Array.isArray(indice) ? indice : []).filter((e) => (e?.br?.[2] || 0) > 0).map((e) => {
    const tot = (e.br[2] || 0) + (e.br[6] || 0);
    const v = (x) => { const i = pos(x); return i >= 0 ? (e.br[5]?.[i] || 0) : 0; };
    return { ht: e.t, pst: e.pst, f: (100 * v(F)) / tot, l: (100 * v(L)) / tot };
  });
}

/** 2º turno: o eleito vem SÓ do TSE (agora.json `eleito`, número), nunca de porcentagem. null se não houver. */
export function eleitoTurno2(fonte, lista) {
  if (!fonte?.eleito) return null;
  return (lista || []).find((c) => String(c.n) === String(fonte.eleito)) || null;
}

export const PARADO_MS = 5 * 60 * 1000;
const BRT_MS = 3 * 3600_000; // Brasília = UTC-3 (sem horário de verão)
/**
 * Idade da leitura do TSE em ms: `t` ("HH:MM", hora de Brasília) no dia `dg` ("DD/MM/AAAA"); sem `dg`, hoje em
 * Brasília (ou ontem, se a hora ainda não chegou hoje). null se `t` não for uma hora válida.
 */
export function idadeLeitura(d, agora = Date.now()) {
  const h = /^(\d\d):(\d\d)$/.exec(String(d?.t || ""));
  if (!h) return null;
  const dg = /^(\d\d)\/(\d\d)\/(\d{4})$/.exec(String(d?.dg || ""));
  let ms;
  if (dg) ms = Date.UTC(+dg[3], +dg[2] - 1, +dg[1], +h[1], +h[2]) + BRT_MS;
  else {
    const hoje = new Date(agora - BRT_MS);
    ms = Date.UTC(hoje.getUTCFullYear(), hoje.getUTCMonth(), hoje.getUTCDate(), +h[1], +h[2]) + BRT_MS;
    if (ms > agora) ms -= 86400_000;
  }
  return agora - ms;
}
/**
 * Selo do 2º turno: "atualizado às HH:MM" (hora `t` da leitura do TSE). Se a leitura não muda há mais de 5 min e a
 * apuração não acabou, "aguardando nova leitura do TSE" e nada de "ao vivo".
 */
export function situacaoVivo(vivo, agora = Date.now()) {
  const d = vivo?.dados;
  if (vivo?.status === "atrasado") return { cls: "atraso", txt: `TSE sem resposta · último dado às ${d?.t || "–"}`, aoVivo: false };
  if (!d) {
    if (vivo?.status === "carregando" || vivo?.status === "inicial") return { cls: "", txt: "Consultando…", aoVivo: false };
    return { cls: "", txt: "Aguardando o TSE", aoVivo: false };
  }
  const hora = (d.t || "").replace(":", "h");
  // idade pela hora do TSE (t/dg); só sem `t` válido cai na hora em que esta aba viu a leitura mudar
  const idade = idadeLeitura(d, agora) ?? (vivo.mudouEm != null ? agora - vivo.mudouEm : null);
  const parado = (d.pst ?? 0) < 100 && idade != null && idade > PARADO_MS;
  // txt/curto: selo do cabeçalho (curto cabe na barra); longo: frase inteira (painel, linha do tempo, leitor de tela)
  if (parado) {
    return { cls: "atraso", txt: `${hora} · aguardando o TSE`, curto: `${hora} · aguardando`, aoVivo: false,
      longo: `atualizado às ${hora} · aguardando nova leitura do TSE` };
  }
  return { cls: "vivo", txt: `${hora} · ${pct(d.pst ?? 0, 1)}% apurado`, curto: `${hora} · ${pct(d.pst ?? 0, 1)}%`, aoVivo: true,
    longo: `atualizado às ${hora}` };
}

/**
 * Exterior: cidades com voto (ordenadas por válidos, entram no ranking e na cor do líder) e quantas ficaram sem voto
 * válido (fora do ranking; o HUD mostra "+N cidades sem voto válido" no fim da lista).
 */
export function exteriorCidades(meta, res, lista, titulador = (s) => s) {
  if (!meta || !res?.ex) return { itens: [], semVoto: 0 };
  const todas = (meta.exterior || []).map(([nome, cod]) => ({ nome: titulador(nome), r: linha("presidente", res.ex[cod], lista) }));
  const itens = todas.filter((x) => x.r?.lider).sort((a, b) => b.r.validos - a.r.validos);
  return { itens, semVoto: todas.length - itens.length };
}
