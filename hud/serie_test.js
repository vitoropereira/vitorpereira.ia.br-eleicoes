// deno test hud/  — gráfico "Ao longo da apuração": quais leituras entram (sem DOM)
import { PST_MIN_GRAFICO, serieVisivel } from "./calc.js";

const igual = (a, b) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${JSON.stringify(a)} != ${JSON.stringify(b)}`); };
const p = (pst) => ({ pst, f: 50, l: 50, ht: "20:00" });

Deno.test("serieVisivel: leituras abaixo de 1% saem do gráfico (25/10: 0,04%, 0,25%, 0,29% achatavam o eixo)", () => {
  igual(PST_MIN_GRAFICO, 1);
  igual(serieVisivel([p(0.04), p(0.25), p(0.29), p(1.65), p(10.9)]).map((s) => s.pst), [1.65, 10.9]);
});

Deno.test("serieVisivel: com menos de 2 leituras acima de 1%, mostra tudo (o gráfico precisa de uma linha)", () => {
  igual(serieVisivel([p(0.04), p(0.25), p(1.65)]).map((s) => s.pst), [0.04, 0.25, 1.65]);
  igual(serieVisivel([p(0.04), p(0.25)]).map((s) => s.pst), [0.04, 0.25]);
});

Deno.test("serieVisivel: 1º turno (começou em 24,5%) não muda", () => {
  const s = [p(24.5), p(36.6), p(99.7)];
  igual(serieVisivel(s), s);
});
