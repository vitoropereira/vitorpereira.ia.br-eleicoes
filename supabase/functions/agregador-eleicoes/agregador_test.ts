import { assert, assertEquals, assertRejects } from "@std/assert";
import { avancar, criarTseFake, eleC, fixture, StorageFake } from "./_fakes.ts";
import { executar, normalizarConcorrencia } from "./executar.ts";
import { gerarEventos, mesclarFeed } from "./feed.ts";
import { gravarAtomico } from "./gravar.ts";
import {
  eleitos,
  extrairCandidatos,
  linhaDe,
  montarAgora,
  nomeExibicao,
  usarNacional,
  validarAgora,
} from "./montar.ts";
import { criarArmazenamentoSupabase } from "./gravar.ts";
import { tratar } from "./index.ts";
import { acharEleicaoFederal2T, descobrirEleicao, LimiteTse } from "./tse.ts";

const ELE = "6258";
const p = (u: string, cd?: string) =>
  cd
    ? `/oficial/ele2026/${ELE}/dados/${u}/${u}${cd}-c0001-e00${ELE}-u.json`
    : `/oficial/ele2026/${ELE}/dados/${u}/${u}-c0001-e00${ELE}-u.json`;
const relogio = (passo = 0) => {
  let t = 1_000_000;
  return { agora: () => t, avancar: () => (t += passo) };
};

// ---------------------------------------------------------------- descoberta

Deno.test("descoberta: só existem códigos de 1º turno -> null (arquivo real do TSE)", async () => {
  assertEquals(acharEleicaoFederal2T(fixture("ele-c-1t")), null);
  const tse = criarTseFake(ELE, false, false); // ele-c real, sem nada publicado sob 6258
  assertEquals(await descobrirEleicao(tse), null);
});

Deno.test("descoberta: acha turno 2 Federal 2026 e ignora Estadual, turno 1 e outros ciclos", () => {
  assertEquals(acharEleicaoFederal2T(eleC(true)), "6258");
  const so_estadual = eleC(false);
  so_estadual.pl.find((x: any) => x.c === "ele2026").e.push({
    cd: "6260",
    nm: "Eleição Ordinária Estadual - 2026 2º Turno",
    t: "2",
  });
  assertEquals(acharEleicaoFederal2T(so_estadual), null);
  const outro_ciclo = eleC(false);
  outro_ciclo.pl.find((x: any) => x.c === "ele2024").e.push({ cd: "999", nm: "Federal 2º Turno", t: "2" });
  assertEquals(acharEleicaoFederal2T(outro_ciclo), null);
  assertEquals(acharEleicaoFederal2T({}), null);
});

Deno.test("sem eleição: devolve sem-eleicao e não escreve nada", async () => {
  const st = new StorageFake();
  const r = await executar({ tse: criarTseFake(ELE, false, false), st, agora: relogio().agora });
  assertEquals(r.status, "sem-eleicao");
  assertEquals(st.escritas, []);
  assertEquals(st.objetos.size, 0);
});

// ---------------------------------------------------------------- transformação

Deno.test("montar: linha do contrato a partir de um município real (Curitiba)", () => {
  const j = fixture("mun-pr-curitiba");
  const cand = extrairCandidatos(j);
  assertEquals(cand.length, 12);
  assertEquals(cand[0].nome.length > 0, true);
  const l = linhaDe(j, cand);
  assertEquals(l.length, 6);
  assertEquals(l[0], 1415148); // eleitores
  assertEquals(l[1], 1136092); // comparecimento
  assertEquals(l[2], 1093434); // válidos
  assertEquals(l[3], 19244); // brancos
  assertEquals(l[4], 23414); // nulos (23378 + 36 técnicos): fecha com o comparecimento
  assertEquals(l[2] + l[3] + l[4], l[1]);
  assertEquals(l[5].reduce((a, b) => a + b, 0), l[2]); // votos nominais somam os válidos
});

Deno.test("montar: nomes de exibição", () => {
  assertEquals(nomeExibicao("FLAVIO BOLSONARO"), "Flávio Bolsonaro");
  assertEquals(nomeExibicao("LULA"), "Lula");
  assertEquals(nomeExibicao("MARIA DA SILVA"), "Maria da Silva");
});

async function rodada1() {
  const st = new StorageFake();
  const tse = criarTseFake(ELE);
  const r = await executar({ tse, st, agora: relogio().agora });
  return { st, tse, r };
}

Deno.test("agora.json: formato idêntico ao contrato (presidente.json + t, idg, pst)", async () => {
  const { st, r } = await rodada1();
  assertEquals(r.status, "gravado");
  const a = st.json("agora.json");
  assertEquals(validarAgora(a), []);
  // chaves do contrato
  for (const k of ["br", "uf", "mu", "ex", "t", "idg", "pst"]) assert(k in a, `falta ${k}`);
  assertEquals(a.br.length, 6);
  assertEquals(a.br[5].length, a.cand.length);
  assertEquals(Object.keys(a.uf), ["DF", "PR", "ZZ"]);
  assertEquals(Object.keys(a.mu).sort(), ["4100202", "4106902", "5300108"]); // IBGE de 7 dígitos
  assertEquals(Object.keys(a.ex), ["29254"]);
  assertEquals(typeof a.idg, "string");
  assertEquals(a.t, "12:51");
  assertEquals(a.pst, 100);
  // JSON compacto, sem espaços
  assertEquals(st.objetos.get("agora.json")!.includes(": "), false);
  // br = soma das UFs
  const somaVV = Object.values<any>(a.uf).reduce((s, l) => s + l[2], 0);
  assertEquals(a.br[2], somaVV);
  // idg do arquivo = maior idg das UFs
  assertEquals(a.idg, String(Math.max(...["uf-df", "uf-pr", "uf-zz"].map((n) => Number(fixture(n).idg)))));
});

Deno.test("invariante: total da UF == soma dos municípios (DF tem 1 município, dados reais)", async () => {
  const { st } = await rodada1();
  const a = st.json("agora.json");
  assertEquals(a.uf.DF, a.mu["5300108"]);
  // vale também sobre os arquivos brutos
  const c = extrairCandidatos(fixture("uf-df"));
  assertEquals(linhaDe(fixture("uf-df"), c), linhaDe(fixture("mun-df-brasilia"), c));
});

Deno.test("grava série, índice, feed e estado; nada fica em _tmp", async () => {
  const { st } = await rodada1();
  for (const c of ["agora.json", "serie/1251.json", "serie/index.json", "feed.json", "_estado.json"]) {
    assert(st.objetos.has(c), `falta ${c}`);
  }
  assertEquals([...st.objetos.keys()].filter((k) => k.startsWith("_tmp/")), []);
  assertEquals(st.json("serie/1251.json"), st.json("agora.json"));
  const idx = st.json("serie/index.json");
  assertEquals(idx.length, 1);
  assertEquals(idx[0].t, "12:51");
  assertEquals(idx[0].br, st.json("agora.json").br);
  assert(st.json("feed.json").length <= 50);
  assertEquals(st.json("_estado.json").travaAte, 0);
  // agora.json é a última coisa gravada antes do estado
  const iAgora = st.escritas.lastIndexOf("agora.json");
  assert(st.escritas.indexOf("serie/1251.json") < iAgora);
});

// ---------------------------------------------------------------- incremental / ETag

Deno.test("segunda rodada sem mudança: 304 em tudo, não regrava agora.json", async () => {
  const { st, tse } = await rodada1();
  const antes = st.escritas.filter((e) => e.includes("agora.json")).length;
  tse.chamadas.length = 0;
  const r = await executar({ tse, st, agora: relogio().agora });
  assertEquals(r.status, "sem-mudanca");
  assertEquals(st.escritas.filter((e) => e.includes("agora.json")).length, antes);
  assertEquals(tse.chamadas.filter((c) => /pr\d+-c0001/.test(c)), []); // nenhum município rebuscado
});

Deno.test("UF que mudou: rebusca só os municípios dela, com If-None-Match", async () => {
  const { st, tse } = await rodada1();
  const idgPr = Number(fixture("uf-pr").idg);
  tse.arquivos.set(p("pr"), avancar(fixture("uf-pr"), 500, idgPr + 10));
  tse.arquivos.set(p("pr", "75353"), avancar(fixture("mun-pr-curitiba"), 500, idgPr + 10));
  tse.chamadas.length = 0;
  const r = await executar({ tse, st, agora: relogio().agora });
  assertEquals(r.status, "gravado");
  if (r.status === "gravado") assertEquals(r.ufsAtualizadas, ["PR"]);
  assertEquals(tse.chamadas.filter((c) => c.includes("/df")).length, 1); // só o arquivo da UF (304)
  const a = st.json("agora.json");
  assertEquals(a.mu["4106902"][2], 1093434 + 500);
  assertEquals(a.mu["4100202"][2], 4201); // Adrianópolis veio do cache (304)
  // feed ganhou evento; índice tem as duas rodadas se o minuto mudou (aqui mesmo minuto -> 1 entrada)
  assert(st.json("serie/index.json").length >= 1);
});

// ---------------------------------------------------------------- idg monotônico

Deno.test("idg nunca regride (guarda global): estado com idg maior que o dos arquivos não publica", async () => {
  const { st, tse } = await rodada1();
  const antes = st.objetos.get("agora.json");
  const est = st.json("_estado.json");
  est.ultimoIdg = "99999999";
  st.objetos.set("_estado.json", JSON.stringify(est));
  const idg = Number(fixture("uf-pr").idg);
  tse.arquivos.set(p("pr"), avancar(fixture("uf-pr"), 5, idg + 5));
  tse.arquivos.set(p("pr", "75353"), avancar(fixture("mun-pr-curitiba"), 5, idg + 5));
  const r = await executar({ tse, st, agora: relogio().agora });
  assertEquals(r.status, "idg-regressivo");
  assertEquals(st.objetos.get("agora.json"), antes);
  assertEquals(st.json("_estado.json").ultimoIdg, "99999999");
  assertEquals(st.json("_estado.json").travaAte, 0);
});

Deno.test("I1: UF cujo arquivo volta com idg menor é ignorada (sem tocar no ETag nem nos municípios)", async () => {
  const { st, tse } = await rodada1();
  const antes = st.objetos.get("agora.json");
  const estAntes = st.json("_estado.json");
  tse.arquivos.set(p("pr"), avancar(fixture("uf-pr"), 999, 100));
  tse.arquivos.set(p("pr", "75353"), avancar(fixture("mun-pr-curitiba"), 999, 100));
  tse.chamadas.length = 0;
  const r = await executar({ tse, st, agora: relogio().agora });
  assertEquals(r.status, "sem-mudanca");
  assertEquals(st.objetos.get("agora.json"), antes);
  assertEquals(st.json("_estado.json").uf.PR, estAntes.uf.PR); // idg e etag antigos
  assertEquals(tse.chamadas.filter((c) => /pr\d+-c0001/.test(c)), []); // nem buscou municípios
});

// ---------------------------------------------------------------- orçamento

Deno.test("orçamento: ao estourar, a UF incompleta fica inteira como estava e o resto segue na rodada seguinte", async () => {
  const { st, tse } = await rodada1();
  const antes = st.json("agora.json");
  const idg0 = Number(fixture("uf-df").idg);
  // todas as UFs têm dados novos
  for (const [u, m] of [["df", "97012"], ["pr", "75353"], ["pr", "74039"], ["zz", "29254"]] as const) {
    tse.arquivos.set(
      p(u, m),
      avancar(
        fixture(
          u === "zz"
            ? "mun-zz-abidja"
            : m === "97012"
            ? "mun-df-brasilia"
            : m === "75353"
            ? "mun-pr-curitiba"
            : "mun-pr-adrianopolis",
        ),
        700,
        9_000_000,
      ),
    );
  }
  for (const u of ["df", "pr", "zz"]) tse.arquivos.set(p(u), avancar(fixture(`uf-${u}`), 700, 9_000_000 + idg0 % 7));

  // cada leitura de município "custa" 60 s: o orçamento (120 s, margem 20 s) acaba na 2ª leitura
  const rel = relogio(60_000);
  tse.aoLerMunicipio = rel.avancar;
  const r = await executar({ tse, st, agora: rel.agora, concorrencia: 1 });
  assertEquals(r.status, "gravado");
  if (r.status !== "gravado") return;
  assertEquals(r.ufsAtualizadas, ["DF"]);
  assertEquals(r.pendentes.sort(), ["PR", "ZZ"]);

  const meio = st.json("agora.json");
  assertEquals(validarAgora(meio), []);
  assertEquals(meio.uf.DF[2], antes.uf.DF[2] + 700); // DF novo
  assertEquals(meio.mu["5300108"][2], antes.mu["5300108"][2] + 700);
  assertEquals(meio.uf.PR, antes.uf.PR); // PR inteiro como antes
  assertEquals(meio.mu["4106902"], antes.mu["4106902"]);
  assertEquals(meio.mu["4100202"], antes.mu["4100202"]);
  assertEquals(meio.uf.ZZ, antes.uf.ZZ);
  assertEquals(meio.ex, antes.ex);
  assertEquals(st.json("_estado.json").pendentes.sort(), ["PR", "ZZ"]);
  assertEquals(BigInt(meio.idg) >= BigInt(antes.idg), true);

  // próxima rodada, com tempo normal: carrega o restante
  tse.aoLerMunicipio = undefined;
  const r2 = await executar({ tse, st, agora: relogio().agora });
  assertEquals(r2.status, "gravado");
  if (r2.status === "gravado") {
    assertEquals(r2.ufsAtualizadas, ["PR", "ZZ"]);
    assertEquals(r2.pendentes, []);
  }
  const fim = st.json("agora.json");
  assertEquals(fim.mu["4106902"][2], antes.mu["4106902"][2] + 700);
  assertEquals(fim.uf.PR[2], antes.uf.PR[2] + 700);
});

Deno.test("trava: rodada sobreposta é recusada", async () => {
  const { st, tse } = await rodada1();
  const e = st.json("_estado.json");
  e.travaAte = Date.now() + 100_000_000;
  st.objetos.set("_estado.json", JSON.stringify(e));
  const r = await executar({ tse, st, agora: () => Date.now() });
  assertEquals(r.status, "ocupado");
});

Deno.test("falha de escrita libera a trava e propaga o erro", async () => {
  const st = new StorageFake();
  st.falharEm = "serie/index.json";
  await assertRejects(() => executar({ tse: criarTseFake(ELE), st, agora: relogio().agora }));
  assertEquals(st.json("_estado.json").travaAte, 0);
  assertEquals(st.objetos.has("agora.json"), false); // agora.json só depois de série e feed
});

// ---------------------------------------------------------------- gravação atômica e feed

Deno.test("gravarAtomico: upsert direto no nome final, sem temporário, e recusa JSON inválido", async () => {
  const st = new StorageFake();
  await gravarAtomico(st, "agora.json", '{"a":1}');
  await gravarAtomico(st, "agora.json", '{"a":2}');
  assertEquals(st.objetos.get("agora.json"), '{"a":2}');
  assertEquals([...st.objetos.keys()], ["agora.json"]);
  assertEquals(st.escritas, ["agora.json", "agora.json"]);
  await assertRejects(() => gravarAtomico(st, "agora.json", "{quebrado"));
  assertEquals(st.objetos.get("agora.json"), '{"a":2}'); // nada foi escrito
});

Deno.test("feed: virada de líder, +N% de seções e eleito; no máximo 50 eventos", () => {
  const cand = [{ n: "13", nome: "Lula", sg: "PT" }, { n: "22", nome: "Flávio Bolsonaro", sg: "PL" }];
  const base = (pst: number, pr: [number, number]) => ({
    t: "19:00",
    dg: "25/10/2026",
    idg: "1",
    pst,
    ele: "6258",
    cargo: "presidente" as const,
    cand,
    br: [0, 0, 100, 0, 0, [50, 50]] as any,
    mu: {},
    ex: {},
    pu: {},
    pm: {},
    pend: [],
    uf: { PR: [0, 0, 100, 0, 0, pr] as any, ZZ: [0, 0, 1, 0, 0, [1, 0]] as any },
  });
  const ev = gerarEventos(base(10.2, [40, 60]), base(11.4, [55, 45]), cand[0]);
  assertEquals(ev.map((e) => e.t), ["apuracao", "virada", "eleito"]);
  assertEquals(ev[1].uf, "PR");
  assertEquals(ev[0].txt.startsWith("11% das seções"), true);
  assertEquals(gerarEventos(base(11.1, [55, 45]), base(11.9, [55, 45]), null), []); // mesmo inteiro, sem virada
  const muitos = Array.from({ length: 80 }, (_, i) => ({ h: "19:00", t: "apuracao" as const, txt: `e${i}` }));
  assertEquals(mesclarFeed(muitos, []).length, 50);
  assertEquals(mesclarFeed(muitos.slice(0, 3), muitos.slice(0, 2)).length, 3); // sem duplicata
});

Deno.test("montarAgora recusa entrada vazia", () => {
  let erro = false;
  try {
    montarAgora({ ele: "1", cand: [], uf: {}, mu: {}, ex: {}, pu: {}, pm: {}, meta: {} });
  } catch {
    erro = true;
  }
  assert(erro);
});

// ---------------------------------------------------------------- segurança da função

Deno.test("index: sem o segredo certo é 401; sem configuração é 500", async () => {
  const antes = ["AGREGADOR_SEGREDO", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"].map((k) =>
    [k, Deno.env.get(k)] as const
  );
  try {
    Deno.env.delete("AGREGADOR_SEGREDO");
    assertEquals((await tratar(new Request("http://x/"))).status, 500);
    Deno.env.set("AGREGADOR_SEGREDO", "segredo-de-teste");
    Deno.env.set("SUPABASE_URL", "http://127.0.0.1:1");
    Deno.env.set("SUPABASE_SERVICE_ROLE_KEY", "k");
    const sem = await tratar(new Request("http://x/"));
    assertEquals(sem.status, 401);
    await sem.body?.cancel();
    const errado = await tratar(new Request("http://x/", { headers: { "x-agregador": "outro" } }));
    assertEquals(errado.status, 401);
    await errado.body?.cancel();
    const bearer = await tratar(new Request("http://x/", { headers: { authorization: "Bearer segredo-de-teste" } }));
    assertEquals(bearer.status, 401); // só o cabeçalho x-agregador vale
    await bearer.body?.cancel();
  } finally {
    for (const [k, v] of antes) v === undefined ? Deno.env.delete(k) : Deno.env.set(k, v);
  }
});

Deno.test("429 do TSE: disjuntor para as buscas, mantém o último agora.json e não derruba a rodada", async () => {
  const { st, tse } = await rodada1();
  const antes = st.objetos.get("agora.json");
  const idg = Number(fixture("uf-pr").idg);
  tse.arquivos.set(p("pr"), avancar(fixture("uf-pr"), 5, idg + 5));
  const original = tse.buscar;
  tse.buscar = (c, e) => /pr\d+-c0001/.test(c) ? Promise.reject(new LimiteTse(c, 429)) : original(c, e);
  const r = await executar({ tse, st, agora: relogio().agora });
  assertEquals(r.status, "sem-mudanca");
  // números e idg intactos; só o pend passa a contar que PR ficou atrás do TSE
  assertEquals({ ...st.json("agora.json"), pend: [] }, JSON.parse(antes!));
  assertEquals(st.json("agora.json").pend, ["PR"]);
  assertEquals(st.json("_estado.json").pendentes, ["PR"]);
  assertEquals(st.json("_estado.json").travaAte, 0);
  // TSE fora do ar já na descoberta (estado vazio)
  const st2 = new StorageFake();
  const fora = criarTseFake(ELE);
  fora.buscar = () => Promise.reject(new LimiteTse("x", 429));
  assertEquals((await executar({ tse: fora, st: st2, agora: relogio().agora })).status, "sem-dados");
  assertEquals(st2.objetos.has("agora.json"), false);
});

// ---------------------------------------------------------------- revisão: C1, I1-I3 e menores

const clock = (t = 1_000_000) => {
  const c = { t, agora: () => c.t };
  return c;
};
const novosArquivos = (tse: ReturnType<typeof criarTseFake>, delta: number, idg: number) => {
  const mapa: [string, string, string?][] = [
    ["df", "uf-df"],
    ["df", "mun-df-brasilia", "97012"],
    ["pr", "uf-pr"],
    ["pr", "mun-pr-curitiba", "75353"],
    ["pr", "mun-pr-adrianopolis", "74039"],
    ["zz", "uf-zz"],
    ["zz", "mun-zz-abidja", "29254"],
  ];
  for (const [u, f, cd] of mapa) tse.arquivos.set(p(u, cd), avancar(fixture(f), delta, idg));
};

Deno.test("C1: primeira rodada cortada pelo orçamento não publica agora.json; _parcial guarda o progresso e a rodada seguinte publica", async () => {
  const st = new StorageFake();
  const tse = criarTseFake(ELE);
  const rel = relogio(60_000);
  tse.aoLerMunicipio = rel.avancar;
  const r = await executar({ tse, st, agora: rel.agora, concorrencia: 1 });
  assertEquals(r.status, "sem-dados");
  if (r.status === "sem-dados") assertEquals(r.motivo, "UFs faltando: PR,ZZ");
  assertEquals(st.objetos.has("agora.json"), false);
  assertEquals(st.objetos.has("feed.json"), false);
  assertEquals(st.objetos.has("serie/index.json"), false);
  const parcial = st.json("_parcial.json");
  assertEquals(Object.keys(parcial.uf), ["DF"]);
  assertEquals(st.json("_estado.json").pendentes.sort(), ["PR", "ZZ"]);
  assertEquals(st.json("_estado.json").travaAte, 0);

  tse.aoLerMunicipio = undefined;
  const r2 = await executar({ tse, st, agora: relogio().agora });
  assertEquals(r2.status, "gravado");
  if (r2.status === "gravado") assertEquals(r2.ufsAtualizadas, ["PR", "ZZ"]); // DF veio do parcial
  const a = st.json("agora.json");
  assertEquals(Object.keys(a.uf), ["DF", "PR", "ZZ"]);
  assertEquals(a.pend, []);
  assertEquals(st.json("_parcial.json"), a);
});

Deno.test("C1: pend lista as UFs cujo dado ficou para trás na publicação", async () => {
  const { st, tse } = await rodada1();
  novosArquivos(tse, 300, 9_000_000);
  const rel = relogio(60_000);
  tse.aoLerMunicipio = rel.avancar;
  await executar({ tse, st, agora: rel.agora, concorrencia: 1 });
  const a = st.json("agora.json");
  assertEquals(a.pend.sort(), ["PR", "ZZ"]);
  assertEquals(validarAgora(a), []);
});

Deno.test("I2: 429 abre pausa 2 -> 4 -> 8 min; rodada em pausa não toca no TSE; rodada limpa zera", async () => {
  const { st, tse } = await rodada1();
  const c = clock();
  const limitar = (on: boolean) => {
    const orig = tse.buscar;
    tse.buscar = on
      ? (cam, e) => (/pr\d+-c0001/.test(cam) ? Promise.reject(new LimiteTse(cam, 429)) : orig(cam, e))
      : orig;
    return orig;
  };
  const idg = Number(fixture("uf-pr").idg);
  tse.arquivos.set(p("pr"), avancar(fixture("uf-pr"), 5, idg + 5));
  tse.arquivos.set(p("pr", "75353"), avancar(fixture("mun-pr-curitiba"), 5, idg + 5));
  const livre = tse.buscar;
  limitar(true);
  await executar({ tse, st, agora: c.agora });
  let e = st.json("_estado.json");
  assertEquals([e.pausaMs, e.pausaAte], [120_000, c.t + 120_000]);
  tse.chamadas.length = 0;
  assertEquals((await executar({ tse, st, agora: c.agora })).status, "pausa");
  assertEquals(tse.chamadas, []);
  c.t += 120_001;
  await executar({ tse, st, agora: c.agora }); // ainda limitado
  assertEquals(st.json("_estado.json").pausaMs, 240_000);
  c.t += 240_001;
  await executar({ tse, st, agora: c.agora });
  assertEquals(st.json("_estado.json").pausaMs, 480_000);
  c.t += 480_001;
  await executar({ tse, st, agora: c.agora });
  assertEquals(st.json("_estado.json").pausaMs, 480_000); // teto
  c.t += 480_001;
  tse.buscar = livre;
  const r = await executar({ tse, st, agora: c.agora });
  assertEquals(r.status, "gravado");
  e = st.json("_estado.json");
  assertEquals([e.pausaMs, e.pausaAte], [0, 0]);
});

Deno.test("I2: reaproveita estado.ele; só redescobre quando ausente", async () => {
  const { st, tse } = await rodada1();
  tse.chamadas.length = 0;
  await executar({ tse, st, agora: relogio().agora });
  assertEquals(tse.chamadas.includes("/oficial/comum/config/ele-c.json"), false);
  assertEquals(st.json("_estado.json").ele, ELE);
  const e = st.json("_estado.json");
  e.ele = null;
  st.objetos.set("_estado.json", JSON.stringify(e));
  await executar({ tse, st, agora: relogio().agora });
  assertEquals(tse.chamadas.includes("/oficial/comum/config/ele-c.json"), true);
});

Deno.test("I3: rodada que perdeu a trava (dono mudou) aborta sem gravar nada", async () => {
  const { st, tse } = await rodada1();
  const antes = new Map(st.objetos);
  novosArquivos(tse, 100, 9_000_000);
  tse.aoLerMunicipio = () => {
    const e = JSON.parse(st.objetos.get("_estado.json")!);
    e.dono = "outra-rodada";
    st.objetos.set("_estado.json", JSON.stringify(e));
  };
  const r = await executar({ tse, st, agora: relogio().agora });
  assertEquals(r.status, "trava-perdida");
  for (const k of ["agora.json", "_parcial.json", "feed.json", "serie/index.json"]) {
    assertEquals(st.objetos.get(k), antes.get(k), k);
  }
  assertEquals(st.json("_estado.json").dono, "outra-rodada"); // não pisou no estado do outro
});

Deno.test("I3: trava expirada (travaAte < agora) também aborta", async () => {
  const { st, tse } = await rodada1();
  const antes = st.objetos.get("agora.json");
  novosArquivos(tse, 100, 9_000_000);
  const c = clock();
  tse.aoLerMunicipio = () => (c.t += 10_000_000);
  const r = await executar({ tse, st, agora: c.agora, margemMs: -1e12 });
  assertEquals(r.status, "trava-perdida");
  assertEquals(st.objetos.get("agora.json"), antes);
});

Deno.test("menor: conjunto de candidatos mudou -> recomeça com os novos candidatos", async () => {
  const { st, tse } = await rodada1();
  const mexer = (j: any) => {
    const c = structuredClone(j);
    for (const a of c.carg[0].agr) for (const q of a.par) for (const k of q.cand) if (k.n === "27") k.n = "99";
    return c;
  };
  const idg = 9_000_000;
  for (
    const [u, f, cd] of [
      ["df", "uf-df"],
      ["df", "mun-df-brasilia", "97012"],
      ["pr", "uf-pr"],
      ["pr", "mun-pr-curitiba", "75353"],
      ["pr", "mun-pr-adrianopolis", "74039"],
      ["zz", "uf-zz"],
      ["zz", "mun-zz-abidja", "29254"],
    ] as [string, string, string?][]
  ) {
    tse.arquivos.set(p(u, cd), mexer(avancar(fixture(f), 1, idg)));
  }
  const logs: unknown[] = [];
  await executar({ tse, st, agora: relogio().agora, log: (...a) => logs.push(a.join(" ")) });
  assert(logs.some((l) => String(l).includes("candidatos mudou")));
  // a rodada seguinte (estado e etags zerados) publica com o novo conjunto
  await executar({ tse, st, agora: relogio().agora });
  const a = st.json("agora.json");
  assert(a.cand.some((c: any) => c.n === "99") && !a.cand.some((c: any) => c.n === "27"));
});

Deno.test("menor: concorrência 0 ou inválida vira pelo menos 1 (padrão 16) e a rodada termina", async () => {
  assertEquals(normalizarConcorrencia(0), 1);
  assertEquals(normalizarConcorrencia(-5), 1);
  assertEquals(normalizarConcorrencia(undefined), 16);
  assertEquals(normalizarConcorrencia(NaN), 16);
  assertEquals(normalizarConcorrencia(7.9), 7);
  const st = new StorageFake();
  const r = await executar({ tse: criarTseFake(ELE), st, agora: relogio().agora, concorrencia: 0 });
  assertEquals(r.status, "gravado");
});

Deno.test("menor: Storage.ler só trata 400 como ausente se o corpo disser not_found", async () => {
  const orig = globalThis.fetch;
  const resp = (status: number, corpo: string) => () => Promise.resolve(new Response(corpo, { status }));
  const st = criarArmazenamentoSupabase("http://x", "k");
  try {
    globalThis.fetch = resp(400, '{"statusCode":"404","error":"not_found","message":"Object not found"}');
    assertEquals(await st.ler("a.json"), null);
    globalThis.fetch = resp(404, "x");
    assertEquals(await st.ler("a.json"), null);
    globalThis.fetch = resp(400, '{"error":"Bad Request","message":"invalid jwt"}');
    await assertRejects(() => st.ler("a.json"));
    globalThis.fetch = resp(500, "boom");
    await assertRejects(() => st.ler("a.json"));
    globalThis.fetch = resp(200, '{"ok":1}');
    assertEquals(await st.ler("a.json"), '{"ok":1}');
  } finally {
    globalThis.fetch = orig;
  }
});

Deno.test("menor: descoberta usa cdt2 do federal de 1º turno só se a config do 2º turno responde 200", async () => {
  // ramo 1: cdt2 = 6258 e a config de 6258 existe
  const com = criarTseFake(ELE, false, true);
  assertEquals(await descobrirEleicao(com), "6258");
  // ramo 2: cdt2 existe mas a config ainda dá 404
  const sem = criarTseFake(ELE, false, false);
  assertEquals(await descobrirEleicao(sem), null);
  // entrada explícita de turno 2 tem prioridade
  assertEquals(await descobrirEleicao(criarTseFake(ELE, true, false)), "6258");
});

// ---------------------------------------------------------------- resultado oficial e pend atrasado

Deno.test("eleito: formato real do TSE (e:'s' + st 'Eleito'); '2º turno' também vem com e:'s' e NÃO é eleito", () => {
  const dados = new URL("../../../relatorio/dados/", import.meta.url);
  const ler = (n: string) => JSON.parse(Deno.readTextFileSync(new URL(n, dados)));
  // governador 1º turno, arquivos reais: PR elegeu (Sergio Moro), RJ foi ao 2º turno
  assertEquals(eleitos(ler("pr-c0003.json"), "3").map((c) => c.nome), ["Sergio Moro"]);
  assertEquals(eleitos(ler("rj-c0003.json"), "3"), []);
  // presidente 1º turno (fixture real): Flávio e Lula com e:"s" e st "2º turno" -> ninguém eleito
  assertEquals(eleitos(fixture("uf-pr")), []);
});

const comEleito = (j: any, n: string) => {
  const c = structuredClone(j);
  for (const a of c.carg[0].agr) {
    for (const p of a.par) {
      for (const k of p.cand) Object.assign(k, k.n === n ? { e: "s", st: "Eleito" } : { e: "n", st: "Não eleito" });
    }
  }
  return c;
};

Deno.test("eleito: agora.json só traz `eleito` quando o TSE marca; sem marca, a chave não existe", async () => {
  const { st, tse } = await rodada1();
  assertEquals("eleito" in st.json("agora.json"), false); // fixtures do 1º turno: "2º turno", ninguém eleito
  // TSE marca o eleito numa nova totalização
  tse.arquivos.set(p("pr"), comEleito(avancar(fixture("uf-pr"), 50, 9_000_000), "22"));
  const r = await executar({ tse, st, agora: relogio().agora });
  assertEquals(r.status, "gravado");
  const a = st.json("agora.json");
  assertEquals(a.eleito, "22");
  assertEquals(validarAgora(a), []);
  assert(st.json("feed.json").some((e: any) => e.t === "eleito"));
  // e continua nas publicações seguintes
  tse.arquivos.set(p("df"), avancar(fixture("uf-df"), 10, 9_100_000));
  await executar({ tse, st, agora: relogio().agora });
  assertEquals(st.json("agora.json").eleito, "22");
});

Deno.test("eleito: número fora da lista de candidatos é recusado pelo contrato", () => {
  const a = montarAgora({
    ele: "6258",
    cand: [{ n: "22", nome: "A", sg: "PL" }],
    uf: { DF: [1, 1, 1, 0, 0, [1]] },
    mu: {},
    ex: {},
    pu: {},
    pm: {},
    meta: {},
    eleito: "13",
  });
  assertEquals("eleito" in a, false);
  assert(validarAgora({ ...a, eleito: "13" }).includes("eleito fora de cand"));
  assert(!validarAgora({ ...a, eleito: "22" }).includes("eleito fora de cand"));
});

Deno.test("pend atrasado: rodada sem nada novo ainda atualiza o pend do agora.json publicado (mesmo idg)", async () => {
  const { st, tse } = await rodada1();
  const antes = st.json("agora.json");
  assertEquals(antes.pend, []);
  // PR e ZZ mudam no TSE; a 1ª leitura de município já consome o orçamento: nenhuma UF fecha nesta rodada
  for (const [u, f] of [["pr", "uf-pr"], ["zz", "uf-zz"]]) tse.arquivos.set(p(u), avancar(fixture(f), 300, 9_000_000));
  for (
    const [u, f, cd] of [["pr", "mun-pr-curitiba", "75353"], ["pr", "mun-pr-adrianopolis", "74039"], [
      "zz",
      "mun-zz-abidja",
      "29254",
    ]]
  ) {
    tse.arquivos.set(p(u, cd), avancar(fixture(f), 300, 9_000_000));
  }
  const rel = relogio(101_000);
  tse.aoLerMunicipio = rel.avancar;
  const r = await executar({ tse, st, agora: rel.agora, concorrencia: 1 });
  assertEquals(r.status, "sem-mudanca");
  const a = st.json("agora.json");
  assertEquals(a.pend, ["PR", "ZZ"]);
  assertEquals({ ...a, pend: [] }, antes); // números, idg e t intactos
  assertEquals(st.json("_estado.json").travaAte, 0);
  // rodada seguinte fecha tudo: pend volta a []
  tse.aoLerMunicipio = undefined;
  await executar({ tse, st, agora: relogio().agora });
  assertEquals(st.json("agora.json").pend, []);
});

Deno.test("pend: UF cuja leitura falhou nesta rodada (429/erro no arquivo da UF) continua em pend", async () => {
  const { st, tse } = await rodada1();
  const idg = Number(fixture("uf-pr").idg);
  tse.arquivos.set(p("pr"), avancar(fixture("uf-pr"), 5, idg + 5));
  const original = tse.buscar;
  // rodada A: PR mudou, municípios de PR com 429 -> PR fica em pend
  tse.buscar = (c, e) => /pr\d+-c0001/.test(c) ? Promise.reject(new LimiteTse(c, 429)) : original(c, e);
  await executar({ tse, st, agora: relogio().agora });
  assertEquals(st.json("agora.json").pend, ["PR"]);
  // rodada B (depois da pausa): agora é o próprio arquivo da UF PR que falha -> PR continua atrás do TSE
  const est = st.json("_estado.json");
  st.objetos.set("_estado.json", JSON.stringify({ ...est, pausaAte: 0 }));
  tse.buscar = (c, e) => /\/pr-c0001/.test(c) ? Promise.reject(new Error("timeout")) : original(c, e);
  await executar({ tse, st, agora: relogio().agora });
  assertEquals(st.json("agora.json").pend, ["PR"]);
  assertEquals(st.json("_estado.json").pendentes, ["PR"]);
  // rodada C: tudo responde -> PR fecha e sai do pend
  tse.buscar = original;
  await executar({ tse, st, agora: relogio().agora });
  assertEquals(st.json("agora.json").pend, []);
});

Deno.test("concorrência pela variável de ambiente: vazia/inválida = padrão 16; número válido vale, mínimo 1", () => {
  assertEquals(normalizarConcorrencia(""), 16); // Number("") seria 0 -> 1 conexão: lento demais na noite
  assertEquals(normalizarConcorrencia("   "), 16);
  assertEquals(normalizarConcorrencia("abc"), 16);
  assertEquals(normalizarConcorrencia(undefined), 16);
  assertEquals(normalizarConcorrencia("12"), 12);
  assertEquals(normalizarConcorrencia(" 8 "), 8);
  assertEquals(normalizarConcorrencia("0"), 1);
  assertEquals(normalizarConcorrencia(12), 12);
});

// ---------------------------------------------------------------- total do país: arquivo Brasil × soma das UFs

/** Arquivo de UF com só `st` seções totalizadas (o resto igual): simula UF atrasada em relação ao Brasil. */
function comSecoes(j: any, st: number): any {
  const c = structuredClone(j);
  c.s.st = String(st);
  c.s.pst = (Math.round((st / Number(c.s.ts)) * 10000) / 100).toFixed(2).replace(".", ",");
  return c;
}
/** Arquivo Brasil: votos do PR + `delta` para o 13, com `st` seções de `ts` e a hora `hg`. */
function brasil(st: number, ts: number, delta: number, idg: number, hg = "17:06:27"): any {
  const c = avancar(fixture("uf-pr"), delta, idg);
  c.s.st = String(st);
  c.s.ts = String(ts);
  c.s.pst = (Math.round((st / ts) * 10000) / 100).toFixed(2).replace(".", ",");
  c.hg = hg;
  return c;
}
const TS_FAKE = 6969 + 27142 + 1351; // seções de DF + PR + ZZ nos fixtures

async function rodadaAtrasada(brSt: number) {
  const st = new StorageFake();
  const tse = criarTseFake(ELE);
  for (const [u, n] of [["df", 10], ["pr", 20], ["zz", 5]] as const) {
    tse.arquivos.set(p(u), comSecoes(fixture(`uf-${u}`), n));
  }
  tse.arquivos.set(p("br"), brasil(brSt, TS_FAKE, 1000, Number(fixture("uf-pr").idg) + 1));
  const r = await executar({ tse, st, agora: relogio().agora });
  return { st, tse, r };
}

Deno.test("total: Brasil à frente da soma das UFs -> br e pst vêm do arquivo Brasil; UFs e municípios não mudam", async () => {
  const { st, r } = await rodadaAtrasada(400);
  assertEquals(r.status, "gravado");
  const a = st.json("agora.json");
  assertEquals(validarAgora(a), []);
  assertEquals(a.total, "tse");
  assertEquals(a.pst, Math.round((400 / TS_FAKE) * 10000) / 100);
  const c = extrairCandidatos(fixture("uf-pr"));
  assertEquals(a.br, linhaDe(avancar(fixture("uf-pr"), 1000, 0), c)); // os votos do arquivo Brasil
  assertEquals(a.uf.PR, linhaDe(fixture("uf-pr"), c)); // a UF segue o arquivo dela
  assertEquals(a.t, "17:06"); // hora do Brasil, mais nova que a das UFs (12:51)
});

Deno.test("total: soma das UFs à frente do Brasil (Brasil congelado, como em 04/10) -> vale a soma", async () => {
  const { st } = await rodadaAtrasada(30); // UFs somam 35 seções
  const a = st.json("agora.json");
  assertEquals(a.total, "uf");
  assertEquals(a.br[2], Object.values<any>(a.uf).reduce((s, l) => s + l[2], 0));
  assertEquals(a.pst, Math.round((35 / TS_FAKE) * 10000) / 100);
});

Deno.test("total: sem arquivo Brasil (404) -> soma das UFs, como antes", async () => {
  const { st } = await rodada1();
  assertEquals(st.json("agora.json").total, "uf");
});

Deno.test("total: Brasil anda sem nenhuma UF mudar -> republica com o novo total (mesmo idg)", async () => {
  const { st, tse } = await rodadaAtrasada(400);
  const antes = st.json("agora.json");
  tse.arquivos.set(p("br"), brasil(900, TS_FAKE, 5000, Number(fixture("uf-pr").idg) + 2, "17:20:00"));
  tse.chamadas.length = 0;
  const r = await executar({ tse, st, agora: relogio().agora });
  assertEquals(r.status, "gravado");
  const a = st.json("agora.json");
  assertEquals(a.pst, Math.round((900 / TS_FAKE) * 10000) / 100);
  assertEquals(
    a.br[5][extrairCandidatos(fixture("uf-pr")).findIndex((c) => c.n === "13")],
    antes.br[5][extrairCandidatos(fixture("uf-pr")).findIndex((c) => c.n === "13")] + 4000,
  );
  assertEquals(a.idg, antes.idg);
  assertEquals(a.t, "17:20");
  assertEquals(tse.chamadas.filter((c) => /\w\d+-c0001/.test(c)), []); // nenhum município rebuscado
});

Deno.test("total: Brasil igual ao publicado -> sem-mudanca, não regrava", async () => {
  const { st, tse } = await rodadaAtrasada(400);
  const n = st.escritas.filter((e) => e === "agora.json").length;
  const r = await executar({ tse, st, agora: relogio().agora });
  assertEquals(r.status, "sem-mudanca");
  assertEquals(st.escritas.filter((e) => e === "agora.json").length, n);
});

Deno.test("total: UFs passam o Brasil (que parou) -> volta para a soma", async () => {
  const { st, tse } = await rodadaAtrasada(400);
  const idg = Number(fixture("uf-pr").idg) + 10;
  tse.arquivos.set(p("pr"), comSecoes(avancar(fixture("uf-pr"), 0, idg), 27142));
  const r = await executar({ tse, st, agora: relogio().agora });
  assertEquals(r.status, "gravado");
  const a = st.json("agora.json");
  assertEquals(a.total, "uf");
  assertEquals(a.br[2], Object.values<any>(a.uf).reduce((s, l) => s + l[2], 0));
});

Deno.test("total: erro ao ler o Brasil não derruba a rodada (segue com a soma)", async () => {
  const st = new StorageFake();
  const tse = criarTseFake(ELE);
  const buscar = tse.buscar.bind(tse);
  tse.buscar = (c, e) => (c.includes("/br/") ? Promise.reject(new Error("timeout")) : buscar(c, e));
  const r = await executar({ tse, st, agora: relogio().agora });
  assertEquals(r.status, "gravado");
  assertEquals(st.json("agora.json").total, "uf");
});

Deno.test("montar: usarNacional só com st do Brasil > soma, ts > 0 e st <= ts", () => {
  const n = (st: number, ts: number) => ({
    linha: [0, 0, 0, 0, 0, [0, 0]] as any,
    resumo: { idg: "1", pst: 0, st, ts, dg: "", hg: "" },
  });
  assertEquals(usarNacional(n(10, 100), 5), true);
  assertEquals(usarNacional(n(5, 100), 5), false);
  assertEquals(usarNacional(n(10, 0), 5), false);
  assertEquals(usarNacional(n(200, 100), 5), false);
  assertEquals(usarNacional(null, 5), false);
});
