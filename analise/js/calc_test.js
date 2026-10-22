// deno test analise/js/  — contas da Análise (sem rede, sem DOM)
const assert = (c, m) => { if (!c) throw new Error(m || "falhou"); };
const assertEquals = (a, b, m) => assert(JSON.stringify(a) === JSON.stringify(b), `${m ? m + ": " : ""}${JSON.stringify(a)} != ${JSON.stringify(b)}`);
const assertAlmostEquals = (a, b, eps = 1e-9) => assert(Math.abs(a - b) < eps, `${a} != ${b}`);
import { ladoDe, escala, passo, marcas, teto, pct, pp, mi, int, num, votosTxt, partes, intervaloPct, intervaloV, recorte, ufDoCodigo, noRecorte, deRecorte, secDivergencias, secComparacao, secBrancos, secDividido, secCenarios, ordenaPesquisas, secTerraGente, SECOES } from "./calc.js";

Deno.test("escala linear e inversa", () => {
  const x = escala([0, 1], [10, 210]);
  assertEquals(x(0.5), 110);
  assertEquals(x.inv(110), 0.5);
  assertEquals(escala([5, 5], [0, 100])(5), 0); // domínio degenerado não explode
});

Deno.test("marcas redondas", () => {
  assertEquals(passo(1, 5), 0.2);
  assertEquals(marcas(1, 5), [0, 0.2, 0.4, 0.6, 0.8, 1]);
  assertEquals(teto(87, 4), 100);
  assertEquals(teto(0.43, 4), 0.6);
  assertEquals(passo(0), 1);
});

Deno.test("formatação pt-BR", () => {
  assertEquals(pct(0.4523), "45,2%");
  assertEquals(pct(0.5, 0), "50%");
  assertEquals(pp(0.031), "+3,1 p.p.");
  assertEquals(pp(-0.2), "−20,0 p.p.");
  assertEquals(mi(7_200_000), "7,2 mi");
  assertEquals(mi(850_000), "850 mil");
  assertEquals(mi(1234), "1.234");
  assertEquals(int(1234567.4), "1.234.567");
  assertEquals(num(3.456, 1), "3,5");
  assertEquals(pct(NaN), "–");
  assertEquals(votosTxt(1_240_000), "1,2 milhão de votos");
  assertEquals(votosTxt(3_000_000), "3 milhões de votos");
  assertEquals(votosTxt(850_000), "850.000 votos");
});

Deno.test("partes somam 1 e ignoram campos extras", () => {
  const p = partes({ L: 30, F: 50, C: 20, validos: 999 });
  assertAlmostEquals(p.L + p.F + p.C, 1, 1e-12);
  assertEquals(p.F, 0.5);
  assertEquals(partes({}), { L: 0, C: 0, F: 0 });
});

Deno.test("intervalo da estimativa: proporção ou votos", () => {
  assertEquals(intervaloPct({ v: 100, pct: 0.2, int: [0.15, 0.25] }), [0.15, 0.25]);
  assertEquals(intervaloPct({ v: 100, pct: 0.2, int: [75, 125] }), [0.15, 0.25]); // em votos: base 500
  assertEquals(intervaloPct({ v: 100, pct: 0.2 }), null);
  assertEquals(intervaloV({ v: 100, pct: 0.2, int: [0.15, 0.25] }), [75, 125]);
});

Deno.test("UF pelo código IBGE e preposições", () => {
  assertEquals(ufDoCodigo("4106902"), "PR");
  assertEquals(ufDoCodigo("5300108"), "DF");
  assertEquals(noRecorte("BR"), "no Brasil");
  assertEquals(noRecorte("SP"), "em São Paulo");
  assertEquals(noRecorte("BA"), "na Bahia");
  assertEquals(noRecorte("PR"), "no Paraná");
  assertEquals(deRecorte("PR"), "do Paraná");
  assertEquals(deRecorte("SP"), "de São Paulo");
});

// dados mínimos no formato do contrato
const D = {
  campos: {
    BR: { presidente: { L: 50, F: 45, C: 5, validos: 100 }, depfed: { L: 25, F: 40, C: 35, validos: 100, legenda: { L: 1, F: 1, C: 1 } } },
    PR: { presidente: { L: 35, F: 60, C: 5, validos: 100 }, depfed: { L: 15, F: 55, C: 30, validos: 100 } },
  },
  dividido: { metodo: "m", BR: { depfed: { est: true, lula_para_F: { v: 7_200_000, pct: 0.13, int: [0.11, 0.15] }, lula_para_C: { v: 9e6, pct: 0.16, int: [0.14, 0.18] }, lula_para_L: { v: 4e7, pct: 0.71, int: [0.69, 0.73] } } } },
  cadeiras: { BR: { depfed: { votos: { L: 0.26, F: 0.4, C: 0.34 }, cadeiras: { L: 124, F: 214, C: 175 }, total: 513 } } },
  divergencias: {
    mu: { "4106902": { pres: "F", depfed: "F" }, "4100103": { pres: "L", depfed: "F" }, "3550308": { pres: "L", depfed: "C" } },
    ranking: { depfed: [{ cd: "4100103", nome: "Abatiá", uf: "PR", pres: "L", pres_pct: 0.5, leg: "F", leg_pct: 0.4, eleitores: 10 }, { cd: "3550308", nome: "São Paulo", uf: "SP", pres: "L", pres_pct: 0.5, leg: "C", leg_pct: 0.4, eleitores: 99 }] },
    uf: { PR: { depfed: { divergentes: 1, total: 2 } }, SP: { depfed: { divergentes: 1, total: 1 } } },
  },
  comparacao2022: {
    mu: { "4106902": { pres22: "L", pres26: "F" }, "4100103": { pres22: "B", pres26: "L" }, "3550308": { pres22: "L", pres26: "F" } },
    viradas: { lula_para_flavio: 2, bolsonaro_para_lula: 1 },
    BR: { pres22_pct_lula: 0.5, pres26_pct_lula: 0.48, depfed22: { L: 0.3, F: 0.3, C: 0.4 }, depfed26: { L: 0.26, F: 0.4, C: 0.34 } },
  },
};

Deno.test("recorte BR × UF recalcula cada seção", () => {
  const br = recorte(D, "BR"), pr = recorte(D, "PR");
  assertEquals(br.uf, "BR"); assertEquals(pr.uf, "PR");
  assertEquals(br.campos.dif, 0.25);
  assertAlmostEquals(pr.campos.dif, 0.2, 1e-12);
  assert(br.campos.titulo.includes("no Brasil"));
  assert(pr.campos.titulo.includes("no Paraná"));
  assertEquals(br.divergencias.div, 2); assertEquals(br.divergencias.tot, 3);
  assertEquals(pr.divergencias.div, 1); assertEquals(pr.divergencias.tot, 2);
  assertEquals(pr.divergencias.ranking.map((x) => x.uf), ["PR"]);
  assertEquals(br.divergencias.dir.LF, 1); assertEquals(br.divergencias.dir.LC, 1);
  assertEquals(pr.divergencias.dir.LC, 0);
  assertEquals(br.comparacao.lf, 2); assertEquals(pr.comparacao.lf, 1); assertEquals(pr.comparacao.bl, 1);
  assertEquals(br.comparacao.leg.length, 3);
  assertEquals(pr.comparacao.leg, null);
  // sem dado na UF: a seção avisa, não inventa
  assertEquals(pr.dividido.ok, false);
  assertEquals(pr.cadeiras.ok, false);
  assertEquals(br.dividido.ok, true);
  assertEquals(br.dividido.numero, "7,2 mi");
  assert(br.dividido.est);
  assert(br.dividido.rotulo.includes("faixa"));
  assertEquals(br.cadeiras.numero, "124 de 513");
});

Deno.test("UF desconhecida cai no Brasil", () => {
  assertEquals(recorte(D, "XX").uf, "BR");
});

Deno.test("seções vazias sem quebrar", () => {
  const r = recorte({}, "BR");
  for (const k of ["campos", "dividido", "cadeiras", "divergencias", "comparacao", "brancos", "fragmentacao", "legenda", "puxadores", "cenarios"]) assertEquals(r[k].ok, false, k);
  assertEquals(secDivergencias({ divergencias: { uf: {} } }, "BR").ok, false);
  assertEquals(secComparacao({ comparacao2022: { mu: {} } }, "SP").ok, false);
});

Deno.test("seções da página têm âncora única", () => {
  const ids = SECOES.map(([id]) => id);
  assertEquals(new Set(ids).size, ids.length);
  assertEquals(ids[0], "destaques"); assertEquals(ids.at(-1), "metodo");
});

Deno.test("lado do partido com exceção por UF", () => {
  const L = { lados: { "2026": { PSD: { lado: "F", uf: { BA: "C" } } } } };
  assertEquals(ladoDe(L, "PSD", "SP"), "F");
  assertEquals(ladoDe(L, "PSD", "BA"), "C");
  assertEquals(ladoDe(L, "XYZ", "SP"), "C");
  assertEquals(ladoDe({}, "PT"), "C");
});

Deno.test("divergência: empate para presidente (C) fica fora das direções", () => {
  const dv = { divergencias: { mu: { "4106902": { pres: "C", depfed: "F" }, "4100103": { pres: "L", depfed: "C" }, "4100202": { pres: "F", depfed: "C" } }, uf: { PR: { depfed: { divergentes: 2, total: 3 } } } } };
  const s = secDivergencias(dv, "BR");
  assertEquals(s.dir, { LF: 0, FL: 0, LC: 1, FC: 1 });
  assertEquals(s.dir.CF, undefined);
});

Deno.test("brancos e nulos: Senado divide pelos 2 votos de cada eleitor", () => {
  const B = { brancos: { BR: {
    presidente: { brancos: 3, nulos: 2, comparecimento: 100 },
    senador: { brancos: 20, nulos: 14, comparecimento: 100, votos_por_eleitor: 2 },
    depfed: { brancos: 6, nulos: 6, comparecimento: 100 },
  } } };
  const s = secBrancos(B, "BR");
  const sen = s.itens.find((i) => i.cargo === "senador");
  assertAlmostEquals(sen.p, 0.17, 1e-12);
  assertAlmostEquals(sen.pb, 0.10, 1e-12);
  assertEquals(s.max.cargo, "senador"); // calculado, não digitado
  assert(s.rotulo.includes("senador"), s.rotulo);
  // sem votos_por_eleitor, deputado (12%) seria o maior só se o Senado estivesse inflado
  const B1 = { brancos: { BR: { ...B.brancos.BR, senador: { ...B.brancos.BR.senador, brancos: 5, nulos: 5 } } } };
  assertEquals(secBrancos(B1, "BR").max.cargo, "depfed");
});

Deno.test("voto dividido no DF (1 município): sem estimativa, avisa", () => {
  const cel = { v: 1, pct: 0.1, int: [0, 1] };
  const D1 = { dividido: { DF: { depfed: { poucos_municipios: true, n_mun: 1, lula_para_F: cel, lula_para_C: cel, lula_para_L: cel } } } };
  const s = secDividido(D1, "DF");
  assertEquals(s.ok, true);
  assertEquals(s.poucos, true);
  assertEquals(s.numero, "–");
  assertEquals(s.titulo, "Voto dividido não pode ser estimado no DF (1 município)");
  assert(s.nota && s.nota.length > 10, "nota explica");
});

Deno.test("cenários: contrato em proporção (0–1)", () => {
  const s = secCenarios({ cenarios: { precisa: { lula_pct_dos_eliminados: 0.6194, flavio_pct_dos_eliminados: 0.3806 }, eliminados: [], cenarios: [], pesquisas: [] } });
  assertEquals(s.numero, "62%");
  assert(s.titulo.includes("62%") && s.titulo.includes("38%"), s.titulo);
});

Deno.test("pesquisas: depois do 1º turno em cima, a mais recente primeiro", () => {
  const ps = [{ instituto: "A", data: "01/10", antes_1t: true }, { instituto: "B", data: "06/10", antes_1t: false }, { instituto: "C", data: "08/10", antes_1t: false }, { instituto: "D", data: "28/09", antes_1t: true }];
  assertEquals(ordenaPesquisas(ps).map((p) => p.instituto), ["C", "B", "A", "D"]);
  const s = secCenarios({ cenarios: { precisa: {}, pesquisas: ps } });
  assertEquals(s.pesquisas[0].instituto, "C");
});

Deno.test("terra × gente: frases com os números do JSON, sem palavra vetada", () => {
  const vz = { mun: 0, area: 0, validos: 0, area_pct: 0, validos_pct: 0 };
  const grupo = (o) => ({ mun: 10, area: 1000, validos: 500, lula: 200, flavio: 250, lula_pct: 0.4, flavio_pct: 0.5, area_br: 0.1, validos_br: 0.2, ...o });
  const D = { "terra-gente": {
    grupos: {
      BR: grupo({ lula_pct: 0.4583, flavio_pct: 0.4721, venc: { L: { mun: 2663, area: 2e6, validos: 6e7, area_pct: 0.3112, validos_pct: 0.5034 }, F: { mun: 2906, area: 6e6, validos: 5.9e7, area_pct: 0.6887, validos_pct: 0.4965 }, E: { mun: 2, area: 500, validos: 1000, area_pct: 0.0001, validos_pct: 0.0001 } } }),
      Norte: grupo({ area_br: 0.4534, validos_br: 0.0857 }),
      PB: grupo({ lula_pct: 0.6131, flavio_pct: 0.3307, area_br: 0.0067, validos_br: 0.0211, venc: { L: { mun: 223, area: 56718, validos: 2513747, area_pct: 1, validos_pct: 1 }, F: vz, E: vz } }),
    },
    capital_sp: { nome: "São Paulo", validos: 6552820, n_menores: 2074, area_menores: 1306368, area: 1535, menores_sem_area: 1 },
    sem_geometria: [{ cd: "5101837", nome: "Boa Esperança do Norte", uf: "MT" }],
  } };
  const s = secTerraGente(D, "BR");
  assertEquals(s.k, "F");
  assertEquals(s.numero, "68,9%");
  assert(s.titulo.includes("68,9%") && s.titulo.includes("47,2%"), s.titulo);
  assertEquals(s.frases.length, 5);
  const tx = s.frases.join(" ");
  for (const n of ["2.906", "2.663", "68,9%", "49,7%", "31,1%", "50,3%", "6.552.820", "2.074", "45,3%", "8,57%"]) assert(tx.includes(n), n);
  for (const v of ["exager", "engan", "distorc", "mentir", "na verdade"]) assert(!tx.toLowerCase().includes(v), v);
  assert(tx.includes("sem a área de 1 município sem polígono na malha"), "menores sem área");
  assertEquals(s.semGeo.map((x) => x.cd), ["5101837"]);
  const pb = secTerraGente(D, "PB");
  assertEquals(pb.k, "L");
  assertEquals(pb.frases[0], "Lula (PT) teve mais votos que Flávio (PL) em todos os 223 municípios.");
  assert(pb.frases.join(" ").includes("Paraíba tem 0,7% da área do país"), pb.frases.join(" "));
  assert(!pb.frases.join(" ").includes("6.552.820"), "capital só no Brasil e em SP");
  assertEquals(pb.semGeo.length, 0);
  assert(!pb.frases[1].includes("os de Flávio"), pb.frases[1]);
  D["terra-gente"].grupos.DF = grupo({ venc: { L: { mun: 1, area: 5760, validos: 1e6, area_pct: 1, validos_pct: 1 }, F: vz, E: vz } });
  assertEquals(secTerraGente(D, "DF").frases[0], "Lula (PT) teve mais votos que Flávio (PL) no único município.");
  assertEquals(secTerraGente(D, "AC").ok, false);
  assert(SECOES.some(([id]) => id === "terra-gente"));
});
