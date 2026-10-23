// deno test hud/  — modo "Pessoas": raio do círculo ∝ √eleitorado (sem DOM)
import { MODOS, modoValido, raioPessoas, bolhasPessoas } from "./calc.js";

const ok = (c, m) => { if (!c) throw new Error(m || "falhou"); };
const perto = (a, b, m) => ok(Math.abs(a - b) < 1e-9, `${m}: ${a} != ${b}`);

Deno.test("raioPessoas: a razão das áreas é a razão do eleitorado", () => {
  const k = 0.0007;
  const a = raioPessoas(40000, k), b = raioPessoas(10000, k);
  perto((a * a) / (b * b), 4, "áreas");
  perto(a / b, 2, "te 4× maior → raio 2×");
  perto(raioPessoas(0, k), 0, "sem eleitorado");
});

Deno.test("bolhasPessoas: alinhado a muns, null quando falta dado", () => {
  const muns = [{ cod: "1" }, { cod: "2" }, { cod: "3" }];
  const pessoas = { k: 0.01, mu: { 1: [1.5, -2.5, 10000], 3: [0, 0, 400] } };
  const b = bolhasPessoas(muns, pessoas);
  ok(b.length === 3, "alinhado");
  ok(b[1] === null, "sem dado");
  perto(b[0].x, 1.5, "x"); perto(b[0].y, -2.5, "y"); perto(b[0].r, 1, "r = 0,01·√10000");
  perto(b[2].r, 0.2, "r de 400");
  ok(bolhasPessoas(muns, null).every((x) => x === null), "sem arquivo, tudo null");
});

Deno.test("MODOS e modoValido: Pessoas vale nos dois turnos", () => {
  ok(MODOS.some(([k, nome]) => k === "pessoas" && nome === "Pessoas"), "MODOS");
  ok(modoValido("pessoas", 1, null) === "pessoas", "1º turno");
  ok(modoValido("pessoas", 2, null) === "pessoas", "2º turno");
  ok(modoValido("pessoas", 2, { pm: false }) === "pessoas", "2º turno sem pm");
});
