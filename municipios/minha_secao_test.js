// deno test --allow-read --allow-env=LOCAIS municipios/minha_secao_test.js
// LOCAIS = pasta com os JSON de montar_secao.py montados das fixtures da #154 (tests/test_minha_secao.py faz isso);
// sem LOCAIS, usa um registro embutido no mesmo formato.
import "./minha_secao.js";

const M = globalThis.MinhaSecao;

function igual(a, b) {
  const x = JSON.stringify(a), y = JSON.stringify(b);
  if (x !== y) throw new Error(`esperava ${y}, veio ${x}`);
}

function ok(v, m) {
  if (!v) throw new Error(m || "falhou");
}

const EMBUTIDO = {
  "1200401": {
    cand: { "1": [[13, "Lula"], [22, "Jair Bolsonaro"], [15, "Simone Tebet"]] },
    t: { "1": [
      [-9.97, -67.81, "ESCOLA SÃO JOSÉ", "CENTRO", "69900", 430, 242, [127, 98], 17,
        [[9, 1, 300, 190, [100, 80], 10], [9, 2, 70, 12, null, null], [9, 7, 60, 40, null, null]]],
      [null, null, "COLÉGIO PEQUENO", "BOSQUE", "69900", 25, 18, null, null, [[9, 10, 25, 18, null, null]]],
      [-9.9, -67.8, "POSTO RURAL", "ZONA RURAL", "69900", 50, 32, null, null, [[9, 20, 50, 32, null, null]]],
    ] },
  },
  "3550308": {
    cand: { "1": [[13, "Lula"], [22, "Jair Bolsonaro"], [15, "Simone Tebet"]], "2": [[13, "Lula"], [22, "Jair Bolsonaro"]] },
    t: {
      "1": [[null, null, "EMEF CAMPOS SALLES", "SÉ", "01001", 400, 390, [200, 150, 30], 10, [[1, 5, 400, 390, [200, 150, 30], 10]]]],
      "2": [[null, null, "EMEF CAMPOS SALLES", "SÉ", "01001", 400, 394, [210, 180], 4, [[1, 5, 400, 394, [210, 180], 4]]]],
    },
  },
};

function dados() {
  const pasta = Deno.env.get("LOCAIS");
  if (!pasta) return EMBUTIDO;
  const out = {};
  for (const e of Deno.readDirSync(pasta)) {
    if (e.name.endsWith(".json")) out[e.name.replace(".json", "")] = JSON.parse(Deno.readTextFileSync(`${pasta}/${e.name}`));
  }
  return out;
}

const D = dados();
const RB = D["1200401"], SP = D["3550308"];
const PART = { "22": "PL", "13": "PT" };

Deno.test("fixture lida (a da #154 quando LOCAIS vem do pytest)", () => {
  igual(Object.keys(D).sort(), ["1200401", "3550308"]);
});

Deno.test("cep5 aceita 5 ou 8 dígitos, com hífen; o resto é null", () => {
  igual(M.cep5("69900-123"), "69900");
  igual(M.cep5("69900123"), "69900");
  igual(M.cep5(" 01001 "), "01001");
  igual(M.cep5("6990"), null);
  igual(M.cep5("699001"), null);
  igual(M.cep5(""), null);
});

Deno.test("busca por zona e seção acha o local e a seção", () => {
  const a = M.acharSecao(RB, 9, 1);
  igual(a.length, 1);
  igual(a[0].turno, "1");
  igual(a[0].local[2], "ESCOLA SÃO JOSÉ");
  igual(a[0].secao, [9, 1, 300, 190, [100, 80], 10]);
  igual(M.acharSecao(RB, "9", "20")[0].local[2], "POSTO RURAL");
});

Deno.test("busca por seção traz os dois turnos quando houver", () => {
  const a = M.acharSecao(SP, 1, 5);
  igual(a.map((x) => x.turno), ["1", "2"]);
  igual(a[1].secao[4], [210, 180]);
});

Deno.test("seção inexistente, agregada ou órfã não acha nada", () => {
  igual(M.acharSecao(RB, 9, 3), []); // agregada à 2
  igual(M.acharSecao(RB, 9, 4), []); // sem local no arquivo do TSE
  igual(M.acharSecao(RB, 8, 1), []);
});

Deno.test("locais junta os turnos de um mesmo local", () => {
  const l = M.locais(SP);
  igual(l.length, 1);
  igual(Object.keys(l[0].t), ["1", "2"]);
  igual(M.locais(RB).map((x) => x.nome), ["ESCOLA SÃO JOSÉ", "COLÉGIO PEQUENO", "POSTO RURAL"]);
});

Deno.test("busca por CEP filtra os locais do município", () => {
  igual(M.porCep(RB, "69900").length, 3);
  igual(M.porCep(SP, "01001").map((x) => x.nome), ["EMEF CAMPOS SALLES"]);
  igual(M.porCep(SP, "69900"), []);
});

Deno.test("perto de mim: ordena por distância e ignora local sem coordenada", () => {
  const p = M.pertoDe(M.locais(RB), -9.9, -67.8, 5);
  igual(p.map((x) => x.l.nome), ["POSTO RURAL", "ESCOLA SÃO JOSÉ"]);
  ok(p[0].km < 0.01);
  ok(p[1].km > 7 && p[1].km < 9, `distância ${p[1].km}`);
  const mun = [["1200401", "Rio Branco", "AC", "1200401", -9.93, -67.8], ["3550308", "São Paulo", "SP", "3550308", null, null],
    ["4106902", "Curitiba", "PR", "PR", -25.43, -49.27]];
  igual(M.municipiosPerto(mun, -25.4, -49.3, 3).map((m) => m[0]), ["4106902", "1200401"]);
});

Deno.test("distância Rio Branco–São Paulo ~ 2.700 km", () => {
  const d = M.distancia(-9.97, -67.81, -23.55, -46.63);
  ok(d > 2600 && d < 2800, String(d));
});

Deno.test("ranking e vencedor em % dos válidos", () => {
  const rk = M.ranking(SP.cand["1"], [200, 150, 30], PART);
  igual(rk.validos, 380);
  igual(rk.linhas.map((x) => [x.nr, x.sg]), [[13, "PT"], [22, "PL"], [15, ""]]);
  const v = M.vencedor(rk);
  igual([v.empate, v.linhas[0].nome], [false, "Lula"]);
  // votos aparados (sem os zeros do fim) e empate
  const e = M.vencedor(M.ranking(SP.cand["1"], [5, 5], PART));
  igual([e.empate, e.linhas.map((x) => x.nr)], [true, [13, 22]]);
  igual(M.ranking(SP.cand["1"], null, PART), null);
});

Deno.test("piso: bloco sem voto não mostra número de candidato", () => {
  const s2 = RB.t["1"][0][9][1];
  const h = M.bloco("Sua seção", RB.cand["1"], s2[4], s2[5], s2[2], s2[3], PART, 30);
  ok(h.includes("Menos de 30 eleitores compareceram"), h);
  ok(!h.includes("ms-cands"), h);
  // seção com 40 de comparecimento ocultada por supressão complementar
  const s7 = RB.t["1"][0][9][2];
  const h7 = M.bloco("Sua seção", RB.cand["1"], s7[4], s7[5], s7[2], s7[3], PART, 30);
  ok(h7.includes("deduzir pela diferença"), h7);
  ok(!h7.includes("ms-cands"), h7);
});

Deno.test("cartão da seção: seção e local, vencedor e cor de partido", () => {
  const l = M.locais(SP)[0];
  const h = M.cartao(l, SP, PART, 30, { secao: [1, 5], mun: "São Paulo/SP" });
  ok(h.includes("Sua seção (zona 1, seção 5) · 1º turno"));
  ok(h.includes("Sua seção (zona 1, seção 5) · 2º turno"));
  ok(h.includes("Local inteiro · 2º turno"));
  ok(h.includes("<b>Lula (PT)</b> ganhou aqui"));
  ok(h.includes("--c:var(--lula)") && h.includes("--c:var(--flavio)") && h.includes("--c:var(--outros)"));
  ok(!/#[0-9a-f]{3,6}\b/i.test(h), "cor literal no HTML");
});

Deno.test("cartão escapa texto vindo dos dados", () => {
  const reg = { cand: { "1": [[13, "<img onerror=x>"]] }, t: { "1": [[null, null, "<b>x</b>", "a&b", "01001", 100, 90, [80], 10, [[1, 1, 100, 90, [80], 10]]]] } };
  const h = M.cartao(M.locais(reg)[0], reg, {}, 30, {});
  ok(!h.includes("<img") && !h.includes("<b>x</b>"), h);
  ok(h.includes("&lt;b&gt;x&lt;/b&gt;") && h.includes("a&amp;b"));
});

// ---- mapa dos locais (#156)

Deno.test("mapa: um ponto por local com coordenada, no último turno; sem coordenada fica fora", () => {
  igual(M.turnoMapa(RB), "1");
  igual(M.turnoMapa(SP), "2");
  const p = M.pontosMapa(RB, "1", PART);
  igual(p.map((x) => x.l.nome), ["ESCOLA SÃO JOSÉ", "POSTO RURAL"]);
  igual(p.map((x) => [x.lat, x.lon, x.aptos]), [[-9.97, -67.81, 430], [-9.9, -67.8, 50]]);
  igual(M.pontosMapa(SP, "2", PART), []); // nenhum local de São Paulo na fixture tem coordenada
  igual(M.semCoordenada(RB, "1"), 1);
});

Deno.test("mapa: cor do vencedor só com token de partido; voto oculto fica sem cor de candidato", () => {
  const [escola, posto] = M.pontosMapa(RB, "1", PART);
  igual([escola.est, escola.sg, M.corPonto(escola)], ["venc", "PT", "var(--lula)"]);
  igual([posto.est, M.corPonto(posto)], ["sigilo", null]); // 32 votantes, voto por candidato omitido
  const reg = { cand: { "1": [[13, "A"], [22, "B"], [15, "C"]] }, t: { "1": [
    [1, 1, "X", "", "", 100, 90, [10, 70, 5], 5, []],
    [1, 2, "Y", "", "", 100, 90, [10, 10, 70], 0, []],
    [1, 3, "Z", "", "", 100, 90, [40, 40], 10, []],
    [1, 4, "W", "", "", 100, 90, [0, 0], 90, []],
  ] } };
  igual(M.pontosMapa(reg, "1", PART).map((x) => [x.est, M.corPonto(x)]),
    [["venc", "var(--flavio)"], ["venc", "var(--outros)"], ["empate", "var(--neutral)"], ["sem", "var(--neutral)"]]);
});

Deno.test("mapa: o ponto não carrega voto do local sob sigilo", () => {
  const posto = M.pontosMapa(RB, "1", PART)[1];
  igual([posto.sg, posto.p], ["", null]);
  ok(!("votos" in posto));
});

Deno.test("mapa: enquadrar mantém a proporção (com cos da latitude) e cabe na largura", () => {
  const e = M.enquadrar([-47, -24, -46, -23], 375, 600, 10);
  ok(Math.abs(e.x(-47) - 10) < 1e-9 && e.x(-46) <= 365 + 1e-9);
  ok(e.y(-23) < e.y(-24), "norte em cima");
  const k = Math.cos((23.5 * Math.PI) / 180);
  ok(Math.abs((e.x(-46) - e.x(-47)) / (e.y(-24) - e.y(-23)) - k) < 1e-9);
  ok(e.h <= 600 && e.h > 300, String(e.h));
  // município comprido na vertical: altura limitada, largura encolhe
  const v = M.enquadrar([-50, -30, -49.9, -20], 375, 500, 10);
  igual(v.h, 500);
  ok(v.x(-49.9) < 375);
});

Deno.test("mapa: raio pela raiz dos aptos (área proporcional), com mínimo para tocar", () => {
  igual(M.raio(1000, 1000, 10), 10);
  ok(Math.abs(M.raio(250, 1000, 10) - (M.RAIO_MIN + (10 - M.RAIO_MIN) * 0.5)) < 1e-9);
  igual(M.raio(0, 1000, 10), M.RAIO_MIN);
  ok(M.raioMax(5) > M.raioMax(2000));
});

Deno.test("mapa: toque acha o ponto mais perto dentro da folga, senão nada", () => {
  const pts = [{ x: 10, y: 10, r: 4 }, { x: 20, y: 10, r: 4 }, { x: 100, y: 100, r: 2 }];
  igual(M.tocado(pts, 11, 10, 8), 0);
  igual(M.tocado(pts, 17, 11, 8), 1);
  igual(M.tocado(pts, 60, 60, 8), -1);
  igual(M.tocado(pts, 109, 100, 8), 2);
});

Deno.test("mapa: 2 mil locais (tamanho de São Paulo) em menos de 50 ms sem canvas", () => {
  const t1 = [];
  for (let i = 0; i < 2000; i++) {
    t1.push([-23.5 - (i % 50) / 100, -46.4 - Math.floor(i / 50) / 100, "L" + i, "", "", 400 + i, 350, [200, 150 - (i % 3)], 10, []]);
  }
  const reg = { cand: { "1": [[13, "A"], [22, "B"]] }, t: { "1": t1 } };
  const t0 = performance.now();
  const p = M.pontosMapa(reg, "1", PART);
  const e = M.enquadrar([-46.9, -24, -46.3, -23.3], 375, 520, 8);
  const rm = M.raioMax(p.length);
  p.forEach((q) => { q.x = e.x(q.lon); q.y = e.y(q.lat); q.r = M.raio(q.aptos, 2399, rm); });
  M.tocado(p, 100, 100, 8);
  const ms = performance.now() - t0;
  igual(p.length, 2000);
  ok(ms < 50, `${ms} ms`);
});
