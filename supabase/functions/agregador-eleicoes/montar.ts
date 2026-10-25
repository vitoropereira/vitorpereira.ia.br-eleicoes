// Transformação pura TSE -> contrato do painel (`presidente.json` + {t, idg, pst}). Sem rede, sem relógio.

/** [eleitores, comparecimento, validos, brancos, nulos, [votos_c0, votos_c1, ...]] */
export type Linha = [number, number, number, number, number, number[]];

export interface Cand {
  n: string;
  nome: string;
  sg: string;
}

export interface Agora {
  t: string; // HH:MM do TSE (hg do arquivo mais novo)
  dg: string; // DD/MM/AAAA
  idg: string; // maior idg entre os arquivos de UF
  pst: number; // % de seções totalizadas no país
  ele: string; // código da eleição no TSE
  cargo: "presidente";
  cand: Cand[]; // ordem fixa (seq do TSE); `votos_ci` segue esta ordem
  br: Linha;
  uf: Record<string, Linha>; // inclui ZZ
  mu: Record<string, Linha>; // chave = código IBGE (cdi)
  ex: Record<string, Linha>; // exterior, chave = código TSE da cidade
  pu: Record<string, number>; // extra: % de seções por UF
  pm: Record<string, number>; // extra: % de seções por município (cdi)
  pend: string[]; // UFs cujo dado nesta publicação está atrás do TSE (a UF mudou e ainda não foi relida)
  /** número do candidato que o TSE marcou como eleito (`e: "s"` + `st` "Eleito"); ausente enquanto não houver */
  eleito?: string;
  /** de onde vêm `br` e `pst`: "tse" = arquivo Brasil do TSE (o número do site do TSE); "uf" = soma das UFs */
  total?: "tse" | "uf";
}

export interface ResumoArquivo {
  idg: string;
  pst: number;
  st: number; // seções totalizadas
  ts: number; // total de seções
  dg: string;
  hg: string;
}

const inteiro = (v: unknown): number => {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
};
const decimal = (v: unknown): number => inteiro(String(v ?? "0").replace(",", "."));

const NOME_EXIBICAO: Record<string, string> = { "Flavio Bolsonaro": "Flávio Bolsonaro" };
const MINUSCULAS = new Set(["de", "da", "do", "das", "dos", "e"]);

export function nomeExibicao(nmu: string): string {
  const t = nmu
    .toLocaleLowerCase("pt-BR")
    .split(/\s+/)
    .map((p, i) => (i > 0 && MINUSCULAS.has(p) ? p : p.charAt(0).toLocaleUpperCase("pt-BR") + p.slice(1)))
    .join(" ");
  return NOME_EXIBICAO[t] ?? t;
}

function candidatosBrutos(json: any, cargo = "1"): any[] {
  const carg = (json?.carg ?? []).find((c: any) => String(c?.cd) === cargo);
  const out: any[] = [];
  for (const agr of carg?.agr ?? []) {
    for (const par of agr?.par ?? []) {
      for (const c of par?.cand ?? []) out.push({ ...c, _sg: par.sg });
    }
  }
  return out;
}

/** Candidatos a presidente de um arquivo, em ordem estável (seq do TSE). */
export function extrairCandidatos(json: any): Cand[] {
  return candidatosBrutos(json)
    .sort((a, b) => inteiro(a.seq) - inteiro(b.seq) || inteiro(a.n) - inteiro(b.n))
    .map((c) => ({ n: String(c.n), nome: nomeExibicao(String(c.nmu ?? c.nm)), sg: String(c._sg ?? "") }));
}

/**
 * Candidatos com status "eleito" no arquivo. O TSE marca `e: "s"` E `st: "Eleito"`; `e: "s"` sozinho não basta,
 * porque no 1º turno quem vai ao 2º turno também vem com `e: "s"` (`st: "2º turno"`). `cargo` = código do TSE
 * (1 presidente, 3 governador), só para conferir o formato nos arquivos reais.
 */
export function eleitos(json: any, cargo = "1"): Cand[] {
  const brutos = candidatosBrutos(json, cargo);
  return brutos
    .filter((c) => c.e === "s" && /^eleit/i.test(String(c.st ?? "")))
    .map((c) => ({ n: String(c.n), nome: nomeExibicao(String(c.nmu ?? c.nm)), sg: String(c._sg ?? "") }));
}

/** Uma linha do contrato a partir de um arquivo de UF/município. Nulos = `tvn` (inclui nulos técnicos), para fechar com o comparecimento. */
export function linhaDe(json: any, cand: Cand[]): Linha {
  const votos = new Map(candidatosBrutos(json).map((c) => [String(c.n), inteiro(c.vap)]));
  const v = json?.v ?? {};
  const e = json?.e ?? {};
  return [
    inteiro(e.te),
    inteiro(e.c),
    inteiro(v.vv),
    inteiro(v.vb),
    inteiro(v.tvn ?? v.vn),
    cand.map((c) => votos.get(c.n) ?? 0),
  ];
}

export function resumoArquivo(json: any): ResumoArquivo {
  return {
    idg: String(json?.idg ?? "0"),
    pst: decimal(json?.s?.pst),
    st: inteiro(json?.s?.st),
    ts: inteiro(json?.s?.ts),
    dg: String(json?.dg ?? ""),
    hg: String(json?.hg ?? ""),
  };
}

export function somarLinhas(linhas: Linha[], ncand: number): Linha {
  const out: Linha = [0, 0, 0, 0, 0, new Array(ncand).fill(0)];
  for (const l of linhas) {
    for (let i = 0; i < 5; i++) (out[i] as number) += l[i] as number;
    for (let i = 0; i < ncand; i++) out[5][i] += l[5][i] ?? 0;
  }
  return out;
}

/** Índice do líder (maior votação) ou -1 se ninguém tem voto. Empate: o primeiro. */
export function lider(l: Linha): number {
  let melhor = -1;
  let max = 0;
  l[5].forEach((v, i) => {
    if (v > max) {
      max = v;
      melhor = i;
    }
  });
  return melhor;
}

export interface Entrada {
  ele: string;
  cand: Cand[];
  uf: Record<string, Linha>;
  mu: Record<string, Linha>;
  ex: Record<string, Linha>;
  pu: Record<string, number>;
  pm: Record<string, number>;
  pend?: string[];
  /** número do eleito segundo o TSE (ver `eleitos`); só entra no agora.json se estiver em `cand` */
  eleito?: string | null;
  /** metadados por UF (inclui ZZ) que compõem o país */
  meta: Record<string, ResumoArquivo>;
  /** arquivo Brasil do TSE (`br-c0001-…-u.json`), se lido nesta rodada */
  nacional?: { linha: Linha; resumo: ResumoArquivo } | null;
}

/**
 * O total do país vem do arquivo Brasil do TSE quando ele tem mais seções que a soma das UFs: é o número que o site do
 * TSE mostra (25/10: Brasil com 1.225 seções, UFs somando 214). Quando a soma está à frente, vale a soma: em 04/10 o
 * arquivo Brasil congelou às 19:14 enquanto as UFs seguiram.
 */
export function usarNacional(n: Entrada["nacional"], stUfs: number): boolean {
  return !!n && n.resumo.ts > 0 && n.resumo.st > stUfs && n.resumo.st <= n.resumo.ts;
}

/** Monta o `agora.json`. Lança se não houver nenhuma UF (nada consistente para publicar). */
export function montarAgora(e: Entrada): Agora {
  const ufs = Object.keys(e.uf).sort();
  if (ufs.length === 0) throw new Error("montarAgora: nenhuma UF disponível");
  let idg = 0n;
  let ref: ResumoArquivo | null = null;
  let st = 0;
  let ts = 0;
  for (const u of ufs) {
    const m = e.meta[u];
    if (!m) continue;
    st += m.st;
    ts += m.ts;
    const i = BigInt(m.idg || "0");
    if (i >= idg) {
      idg = i;
      ref = m;
    }
  }
  const nac = usarNacional(e.nacional, st) ? e.nacional! : null;
  const pst = nac
    ? Math.round((nac.resumo.st / nac.resumo.ts) * 10000) / 100
    : ts > 0
    ? Math.round((st / ts) * 10000) / 100
    : 0;
  // hora: a do arquivo mais novo entre a UF de referência e o Brasil (quando o Brasil é usado)
  const hg = nac && nac.resumo.hg > (ref?.hg ?? "") ? nac.resumo.hg : ref?.hg ?? "";
  const ordenar = <T>(o: Record<string, T>) => Object.fromEntries(Object.keys(o).sort().map((k) => [k, o[k]]));
  return {
    t: hg.slice(0, 5),
    dg: ref?.dg ?? "",
    idg: idg.toString(),
    pst,
    ele: e.ele,
    cargo: "presidente",
    cand: e.cand,
    br: nac ? nac.linha : somarLinhas(ufs.map((u) => e.uf[u]), e.cand.length),
    uf: ordenar(e.uf),
    mu: ordenar(e.mu),
    ex: ordenar(e.ex),
    pu: ordenar(e.pu),
    pm: ordenar(e.pm),
    pend: [...(e.pend ?? [])].filter((u) => u in e.uf).sort(),
    ...(e.eleito && e.cand.some((c) => c.n === e.eleito) ? { eleito: e.eleito } : {}),
    total: nac ? "tse" : "uf",
  };
}

const ehLinha = (l: unknown, n: number): boolean =>
  Array.isArray(l) && l.length === 6 && l.slice(0, 5).every((x) => Number.isInteger(x) && x >= 0) &&
  Array.isArray(l[5]) && l[5].length === n && l[5].every((x: unknown) => Number.isInteger(x) && (x as number) >= 0);

/** Valida o formato do contrato. Devolve a lista de problemas (vazia = ok). */
export function validarAgora(a: any): string[] {
  const erros: string[] = [];
  if (!a || typeof a !== "object") return ["não é objeto"];
  if (!/^\d\d:\d\d$/.test(a.t ?? "")) erros.push("t inválido");
  if (!/^\d+$/.test(a.idg ?? "")) erros.push("idg inválido");
  if (typeof a.pst !== "number" || a.pst < 0 || a.pst > 100) erros.push("pst inválido");
  if (!Array.isArray(a.cand) || a.cand.length === 0) erros.push("cand vazio");
  const n = Array.isArray(a.cand) ? a.cand.length : 0;
  if (!ehLinha(a.br, n)) erros.push("br inválido");
  if (a.pend !== undefined && !Array.isArray(a.pend)) erros.push("pend inválido");
  if (a.eleito !== undefined && !(Array.isArray(a.cand) && a.cand.some((c: any) => c?.n === a.eleito))) {
    erros.push("eleito fora de cand");
  }
  for (const k of ["uf", "mu", "ex"]) {
    if (!a[k] || typeof a[k] !== "object") erros.push(`${k} ausente`);
    else for (const [c, l] of Object.entries(a[k])) if (!ehLinha(l, n)) erros.push(`${k}.${c} inválido`);
  }
  return erros;
}
