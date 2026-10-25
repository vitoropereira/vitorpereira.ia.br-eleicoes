// deno test home_test.js  — fases da home do 2º turno (issue 205). Funções puras: sem DOM, sem rede.
import { ancoraAntiga, faltam, fase, INICIO_APURACAO, placar, textoProjecao } from "./home.js";
const assertEquals = (a, b) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${JSON.stringify(a)} != ${JSON.stringify(b)}`); };

const BRT = (d, h, m = 0) => Date.UTC(2026, 9, d, h + 3, m); // 25/10 17:00 em Brasília = 20:00 UTC
const CAND = [{ n: "22", nome: "Flávio Bolsonaro", sg: "PL" }, { n: "13", nome: "Lula", sg: "PT" }];
const VIVO = { idg: "1", pst: 42.5, cand: CAND, br: [1000, 800, 700, 50, 50, [350, 350]], mu: {} };

Deno.test("fase: véspera até as 17h de 25/10, com ou sem dado", () => {
  assertEquals(INICIO_APURACAO, BRT(25, 17));
  assertEquals(fase(BRT(24, 23), null), "vespera");
  assertEquals(fase(BRT(25, 16, 59), null), "vespera");
  assertEquals(fase(BRT(25, 16, 59), VIVO), "vespera"); // dado cedo demais (ensaio) não muda a fase
});

Deno.test("fase: depois das 17h sem agora.json continua véspera; com dado, apuração", () => {
  assertEquals(fase(BRT(25, 17, 1), null), "vespera");
  assertEquals(fase(BRT(25, 17, 1), undefined), "vespera");
  assertEquals(fase(BRT(25, 17, 1), VIVO), "apuracao");
});

Deno.test("fase: eleito marcado pelo TSE = resultado", () => {
  assertEquals(fase(BRT(25, 21), { ...VIVO, eleito: "13" }), "resultado");
  assertEquals(fase(BRT(25, 21), { ...VIVO, eleito: "" }), "apuracao");
});

Deno.test("faltam: horas e minutos até as 17h; vazio depois", () => {
  assertEquals(faltam(BRT(25, 13, 48)), "faltam 3h 12min");
  assertEquals(faltam(BRT(25, 16, 30)), "faltam 30min");
  assertEquals(faltam(BRT(24, 17, 0)), "faltam 24h 0min");
  assertEquals(faltam(BRT(25, 17, 0)), "");
});

Deno.test("placar: % sobre os válidos, na ordem de agora.cand", () => {
  const p = placar({ ...VIVO, br: [1000, 800, 700, 50, 50, [420, 280]] });
  assertEquals(p.pst, 42.5);
  assertEquals(p.cands.map((c) => [c.nome, c.sg, c.v, c.lado]), [["Flávio Bolsonaro", "PL", 420, "F"], ["Lula", "PT", 280, "L"]]);
  assertEquals(p.cands.map((c) => Math.round(c.p * 100) / 100), [60, 40]);
});

Deno.test("placar: a ordem vem de agora.cand, não de quem lidera", () => {
  const p = placar({ ...VIVO, cand: [CAND[1], CAND[0]], br: [1000, 800, 700, 50, 50, [100, 600]] });
  assertEquals(p.cands.map((c) => c.sg), ["PT", "PL"]);
  assertEquals(p.cands.map((c) => c.v), [100, 600]);
});

Deno.test("placar: sem cand no agora.json usa a lista de reserva", () => {
  const { cand: _, ...semCand } = VIVO;
  const p = placar(semCand, CAND);
  assertEquals(p.cands.map((c) => c.sg), ["PL", "PT"]);
  assertEquals(placar(semCand, null).cands, []); // sem nenhuma lista, não inventa candidato
});

Deno.test("placar: sem voto nenhum, 0% e sem dividir por zero", () => {
  const p = placar({ ...VIVO, br: [1000, 0, 0, 0, 0, [0, 0]] });
  assertEquals(p.cands.map((c) => c.p), [0, 0]);
});

Deno.test("âncora antiga do relatório vai para /1-turno/", () => {
  assertEquals(ancoraAntiga("#presidente"), "/1-turno/#presidente");
  assertEquals(ancoraAntiga("#metodo"), "/1-turno/#metodo");
  assertEquals(ancoraAntiga("#perguntas"), "/1-turno/#perguntas");
  assertEquals(ancoraAntiga("#governadores"), "/1-turno/#governadores");
});

Deno.test("âncora desconhecida ou vazia não redireciona", () => {
  assertEquals(ancoraAntiga("#qualquer-coisa"), null);
  assertEquals(ancoraAntiga("#"), null);
  assertEquals(ancoraAntiga(""), null);
  assertEquals(ancoraAntiga("#vespera"), null); // âncora da própria home
});

Deno.test("projeção ao vivo: texto com % final, chance e hora; arquivo inválido = vazio", () => {
  const pj = { t: "19:20", pst: 2.2, f: 50.27, l: 49.73, pf: 40.7, pl: 59.3, nf: "Flávio Bolsonaro", nl: "Lula", sf: "PL", sl: "PT" };
  assertEquals(textoProjecao(pj), "Projeção para o fim da apuração: Flávio Bolsonaro (PL) 50,3% × Lula (PT) 49,7% · " +
    "chance de vencer 41% × 59% · calculada às 19:20. É modelo, não resultado.");
  assertEquals(textoProjecao(null), "");
  assertEquals(textoProjecao({ ...pj, f: "50" }), "");
  assertEquals(textoProjecao({ ...pj, t: "" }), "");
});
