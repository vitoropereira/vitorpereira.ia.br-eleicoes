// deno test hud/  — contas do HUD (sem rede, sem DOM)
import { linha, linhaSerie, somar, oficial, duelo } from "./calc.js";

const ok = (c, m) => { if (!c) throw new Error(m || "falhou"); };
const perto = (a, b, m) => ok(Math.abs(a - b) < 1e-9, `${m}: ${a} != ${b}`);

const LISTA = [
  { n: "22", nome: "Ruas", sg: "PL" },
  { n: "55", nome: "Paes", sg: "PSD" },
  { n: "10", nome: "Garotinho", sg: "REPUBLICANOS", sj: true },
];

Deno.test("denominador = válidos + anulados sub judice (regra do TSE)", () => {
  const r = linha("governador", [1000, 900, 800, 50, 50, [420, 300, 80], 80], LISTA);
  perto(r.total, 880, "total");
  perto(r.cands[0].p, 420 / 880, "1º");
  perto(r.cands[1].p, 300 / 880, "2º");
});

Deno.test("sub judice tem % e etiqueta, e pode liderar o município", () => {
  const r = linha("governador", [1000, 900, 700, 50, 50, [200, 100, 400], 400], LISTA);
  ok(r.lider.nome === "Garotinho" && r.lider.sj === true, "líder do município é o mais votado");
  perto(r.lider.p, 400 / 1100, "% do sub judice");
});

Deno.test("somar regiões soma votos e vansj", () => {
  const s = somar([[10, 8, 6, 1, 1, [4, 2], 1], [20, 16, 12, 2, 2, [5, 7], 3], null]);
  ok(JSON.stringify(s) === JSON.stringify([30, 24, 18, 3, 3, [9, 9], 4]), JSON.stringify(s));
});

Deno.test("linha do tempo por UF acha Flávio e Lula pelo número, não pela posição", () => {
  const lista = [{ n: "13", nome: "Lula", sg: "PT" }, { n: "22", nome: "Flávio Bolsonaro", sg: "PL" }];
  const r = linhaSerie([36.6, 50.63, 41.23], lista);
  ok(r.lider.nome === "Flávio Bolsonaro" && r.lider.sg === "PL", r.lider.nome);
  perto(r.p1, 0.5063, "p1"); perto(r.pst, 36.6, "pst");
  ok(duelo([]).F.n === "22" && duelo([]).L.n === "13", "fallback");
});

Deno.test("situação oficial vem do status.json, pelo número", () => {
  const st = { governador: { RJ: { status: "2turno", a: "22", b: "55" } }, senador: { PR: { eleitos: ["55", "22"] } } };
  const o = oficial(st, "governador", "RJ", LISTA);
  ok(o.status === "2turno" && o.a.nome === "Ruas" && o.b.nome === "Paes");
  ok(oficial(st, "senador", "PR", LISTA).eleitos.map((c) => c.nome).join() === "Paes,Ruas");
  ok(oficial(null, "governador", "RJ", LISTA) === null, "sem status → null (manchete neutra)");
});

Deno.test("zero voto apurado: ninguém lidera e o mapa não pinta (2º turno antes das primeiras seções)", async () => {
  const { corPara } = await import("./calc.js");
  const r = linha("presidente", [1000, 0, 0, 0, 0, [0, 0, 0]], LISTA);
  ok(r.vazio === true && r.lider === null && r.segundo === null, "sem líder");
  ok(r.p1 === 0 && r.margem === 0, "p1/margem zerados");
  ok(corPara("municipios", r, "presidente") === null && corPara("vantagem", r, "presidente") === null, "sem cor de partido");
  const r1 = linha("presidente", [1000, 10, 10, 0, 0, [0, 1, 9]], LISTA);
  ok(!r1.vazio && r1.lider.nome === "Garotinho", "um voto já define o líder");
});

// ---------- 2º turno, itens da revisão (a–d)
import { resumoLeitor, fonteTurno2, modoValido, senadoEleitos, divergencia, cargoDivergencia, MODOS } from "./calc.js";

const PRES = [{ n: "22", nome: "Flávio Bolsonaro", sg: "PL" }, { n: "13", nome: "Lula", sg: "PT" }];
const META = { cand: { presidente: PRES } };

Deno.test("a. resumo do leitor de tela usa a leitura da UF escolhida durante a linha do tempo", () => {
  const ponto = { ht: "18:32", pst: 36.6, f: 50.63, l: 41.23, uf: { PR: [83.37, 62.1, 30.2] } };
  const base = { turno: 1, temVivo: false, fonte: { br: [1, 1, 1, 0, 0, [1, 0]] }, meta: META, cargo: "presidente", lista: PRES };
  const br = resumoLeitor({ ...base, ponto, pontoUF: ponto, ufSel: null });
  ok(br.includes("36,6%") && br.includes("50,63%"), br);
  const pr = resumoLeitor({ ...base, ponto, pontoUF: ponto, ufSel: "PR" });
  ok(pr.includes("Paraná") && pr.includes("83,4%") && pr.includes("62,10%") && !pr.includes("50,63"), pr);
  const sem = resumoLeitor({ ...base, ponto, pontoUF: ponto, ufSel: "BA" });
  ok(sem.includes("Bahia") && sem.includes("não tinha publicado"), sem);
  // fora da linha do tempo, com UF escolhida: a linha da UF, não a nacional
  const fonte = { br: [0, 0, 100, 0, 0, [60, 40]], uf: { PR: [0, 0, 10, 0, 0, [9, 1]] }, pst: 50, pu: { PR: 80 }, t: "19:06" };
  const t2 = resumoLeitor({ ...base, turno: 2, temVivo: true, fonte, ponto: null, pontoUF: null, ufSel: "PR" });
  ok(t2.includes("Paraná") && t2.includes("90,00%") && t2.includes("80,0%") && t2.includes("19:06"), t2);
  const zero = resumoLeitor({ ...base, turno: 2, temVivo: true, fonte: { br: [9, 0, 0, 0, 0, [0, 0]], pst: 0 }, ponto: null, ufSel: null });
  ok(zero.includes("nenhum voto apurado"), zero);
});

Deno.test("partido junto: comSigla e cartao", async () => {
  const { comSigla, cartao, cartaoCurto } = await import("./calc.js");
  const f = PRES[0];
  ok(comSigla(f) === "Flávio Bolsonaro (PL)", comSigla(f));
  ok(comSigla(f, true) === "Flávio (PL)", comSigla(f, true));
  ok(cartaoCurto(f) === "Flávio · PL", cartaoCurto(f));
  ok(cartao({ nome: "Dr. Furlan", sg: "PSD" }) === "Dr. Furlan · PSD", "cartão de lista não corta nome de 2 palavras");
  ok(cartao({ nome: "Professora Maria do Carmo", sg: "PL" }) === "Professora Maria · PL", "até 2 palavras");
  ok(comSigla({ nome: "PL", sg: "PL" }) === "PL" && cartao({ nome: "PL", sg: "PL" }) === "PL", "nome já é a sigla");
  ok(comSigla({ nome: "Fulano" }) === "Fulano" && cartao({ nome: "Fulano", sg: "" }) === "Fulano", "sem sigla");
});

Deno.test("partido junto: textoComSigla acrescenta a sigla do dado em texto pronto", async () => {
  const { textoComSigla } = await import("./calc.js");
  ok(textoComSigla("eleitor de Lula, deputado do lado de Flávio", PRES) === "eleitor de Lula (PT), deputado do lado de Flávio (PL)", "dois nomes");
  ok(textoComSigla("Lula (PT) e Flávio Bolsonaro (PL)", PRES) === "Lula (PT) e Flávio Bolsonaro (PL)", "já tem sigla: intacto");
  ok(textoComSigla("Lulalândia", PRES) === "Lulalândia", "palavra inteira");
  ok(textoComSigla("50% das seções · Flávio Bolsonaro 51,0% × Lula 49,0%", PRES) === "50% das seções · Flávio Bolsonaro (PL) 51,0% × Lula (PT) 49,0%", "feed do agregador: nome completo");
  ok(textoComSigla("apoia Flávio (faixa de 90%)", PRES) === "apoia Flávio (PL) (faixa de 90%)", "parêntese que não é sigla");
  ok(textoComSigla("Flávio Dino e Luiz Inácio Lula da Silva", PRES) === "Flávio Dino e Luiz Inácio Lula da Silva", "outro sobrenome");
});

Deno.test("partido junto: narração do leitor de tela traz a sigla do dado", () => {
  const ponto = { ht: "18:32", pst: 36.6, f: 50.63, l: 41.23, uf: { PR: [83.37, 62.1, 30.2] } };
  const base = { turno: 1, temVivo: false, fonte: { br: [0, 0, 100, 0, 0, [60, 40]] }, meta: META, cargo: "presidente", lista: PRES };
  const t = resumoLeitor({ ...base, ponto, pontoUF: ponto, ufSel: null });
  ok(t.includes("Flávio (PL) 50,63%") && t.includes("Lula (PT) 41,23%"), t);
  const u = resumoLeitor({ ...base, ponto, pontoUF: ponto, ufSel: "PR" });
  ok(u.includes("Flávio (PL) 62,10%") && u.includes("Lula (PT) 30,20%"), u);
  const v = resumoLeitor({ ...base, ponto: null, pontoUF: null, ufSel: null });
  ok(v.includes("Flávio Bolsonaro (PL) 60,00%") && v.includes("Lula (PT) 40,00%"), v);
});

Deno.test("b. minuto da linha do tempo: nunca mostra o ao vivo no lugar do minuto escolhido", () => {
  const vivo = { idg: "9" }, m1 = { t: "18:32", dados: { idg: "1" } };
  ok(fonteTurno2(null, null, m1, vivo).fonte === vivo, "sem minuto: ao vivo");
  ok(fonteTurno2(3, "18:32", m1, vivo).fonte === m1.dados, "minuto carregado");
  const carregando = fonteTurno2(4, "19:06", m1, vivo);
  ok(carregando.fonte === null && carregando.carregando, "minuto novo carregando: nada, nem o anterior nem o ao vivo");
  const falhou = fonteTurno2(4, "19:06", { t: "19:06", erro: new Error("x") }, vivo);
  ok(falhou.fonte === null && falhou.erro === true, "falhou: erro, sem cair no ao vivo");
});

Deno.test("c. Apurado sem pm volta para Municípios (só no 2º turno)", () => {
  ok(modoValido("apurado", 2, { pst: 10 }) === "municipios", "sem pm");
  ok(modoValido("apurado", 2, { pm: {} }) === "apurado", "com pm");
  ok(modoValido("apurado", 1, {}) === "apurado", "1º turno não muda");
  ok(modoValido("estados", 2, { pst: 1 }) === "estados", "outros modos intactos");
  ok(modoValido("apurado", 2, null) === "apurado", "sem dado ainda: não mexe");
});

Deno.test("d. Senado: 'são eleitos' só com status.json E 100% apurado", () => {
  const of = { eleitos: [PRES[0], PRES[1]] };
  ok(senadoEleitos(of, 100)?.length === 2, "oficial + 100%");
  ok(senadoEleitos(of, 99.99) === null, "parcial: nunca eleito");
  ok(senadoEleitos(of, undefined) === null, "sem pst: nunca eleito");
  ok(senadoEleitos({ eleitos: [] }, 100) === null && senadoEleitos(null, 100) === null, "sem status: nunca eleito");
});

Deno.test("série do 2º turno: leitura sem voto (0%) fica de fora; Flávio e Lula pelo número", async () => {
  const { serieTurno2 } = await import("./calc.js");
  const cand = [{ n: "13", nome: "Lula", sg: "PT" }, { n: "22", nome: "Flávio Bolsonaro", sg: "PL" }];
  const s = serieTurno2([
    { t: "17:00", pst: 0, br: [10, 0, 0, 0, 0, [0, 0]] },
    { t: "18:32", pst: 45.6, br: [10, 8, 100, 0, 0, [40, 60]] },
  ], cand);
  ok(s.length === 1 && s[0].ht === "18:32", JSON.stringify(s));
  perto(s[0].f, 60, "Flávio pelo número 22"); perto(s[0].l, 40, "Lula pelo número 13");
  ok(serieTurno2(null, cand).length === 0, "sem índice");
});

Deno.test("2º turno: 'eleito' só do agora.json (`eleito` do TSE), nunca de porcentagem", async () => {
  const { eleitoTurno2, resumoLeitor: rl } = await import("./calc.js");
  const fonte = { br: [0, 0, 100, 0, 0, [60, 40]], pst: 100, t: "22:40" };
  ok(eleitoTurno2(fonte, PRES) === null, "60% a 100% apurado, sem marca do TSE: ninguém eleito");
  ok(eleitoTurno2({ ...fonte, eleito: "22" }, PRES)?.nome === "Flávio Bolsonaro", "marca do TSE pelo número");
  ok(eleitoTurno2({ ...fonte, eleito: "99" }, PRES) === null, "número fora da lista: ignora");
  const base = { turno: 2, temVivo: true, meta: META, cargo: "presidente", lista: PRES, ponto: null, pontoUF: null };
  ok(!rl({ ...base, fonte, ufSel: null }).includes("eleito"), "resumo sem marca: sem eleito");
  ok(rl({ ...base, fonte: { ...fonte, eleito: "22" }, ufSel: null }).startsWith("Flávio Bolsonaro (PL) é eleito presidente"), "resumo com marca");
});

Deno.test("2º turno: leitura parada há mais de 5 min com apuração aberta → 'aguardando nova leitura do TSE', sem 'ao vivo'", async () => {
  const { situacaoVivo, PARADO_MS } = await import("./calc.js");
  const lida = Date.UTC(2026, 9, 25, 23, 47); // 20:47 em Brasília
  let agora = lida + 60_000;
  const vivo = { status: "ok", dados: { t: "20:47", dg: "25/10/2026", pst: 93.2 }, mudouEm: agora };
  const s1 = situacaoVivo(vivo, agora);
  ok(s1.aoVivo && s1.longo === "atualizado às 20h47" && s1.txt.includes("93,2%"), JSON.stringify(s1));
  agora = lida + PARADO_MS + 1;
  const s2 = situacaoVivo(vivo, agora);
  ok(!s2.aoVivo && s2.longo === "atualizado às 20h47 · aguardando nova leitura do TSE" && s2.txt.includes("aguardando"), JSON.stringify(s2));
  const s3 = situacaoVivo({ ...vivo, dados: { t: "20:47", dg: "25/10/2026", pst: 100 } }, lida + 3_600_000);
  ok(s3.aoVivo && !s3.longo.includes("aguardando"), "100%: não fica 'aguardando'");
  ok(!situacaoVivo({ status: "atrasado", dados: vivo.dados }, agora).aoVivo, "TSE sem resposta: sem ao vivo");
});

Deno.test("leitura parada: idade pela hora do TSE (t + dg, Brasília), não pela hora em que a aba viu", async () => {
  const { situacaoVivo, idadeLeitura } = await import("./calc.js");
  const utc = (h, m) => Date.UTC(2026, 9, 25, h, m); // 25/10/2026; Brasília = UTC-3
  const dados = { t: "20:47", dg: "25/10/2026", pst: 90 };
  ok(idadeLeitura(dados, utc(23, 53)) === 6 * 60_000, `idade: ${idadeLeitura(dados, utc(23, 53))}`);
  // a aba acabou de abrir (mudouEm agora), mas a leitura do TSE é de 6 min atrás: parada
  const s1 = situacaoVivo({ status: "ok", dados, mudouEm: utc(23, 53) }, utc(23, 53));
  ok(!s1.aoVivo && s1.longo.includes("aguardando nova leitura do TSE"), JSON.stringify(s1));
  // leitura do TSE de 2 min atrás, mesmo com a aba sem ver mudança há muito tempo: não está parada
  const s2 = situacaoVivo({ status: "ok", dados, mudouEm: utc(22, 0) }, utc(23, 49));
  ok(s2.aoVivo, JSON.stringify(s2));
  // sem dg: usa a data de hoje em Brasília (e ontem se a hora ainda não chegou hoje)
  ok(idadeLeitura({ t: "23:58" }, Date.UTC(2026, 9, 26, 3, 3)) === 5 * 60_000 + 0, "virada do dia");
  ok(idadeLeitura({ t: "xx" }, utc(23, 0)) === null, "t inválido: sem idade");
});

Deno.test("Exterior: cidade sem voto válido fica fora do ranking, mas é contada", async () => {
  const { exteriorCidades } = await import("./calc.js");
  const meta = { exterior: [["ABUJA", "1"], ["LISBOA", "2"], ["TÓQUIO", "3"], ["NOVA", "4"]] };
  const res = { ex: { "1": [10, 0, 0, 0, 0, [0, 0]], "2": [99, 90, 80, 5, 5, [50, 30]], "3": [50, 40, 40, 0, 0, [10, 30]] } };
  const { itens, semVoto } = exteriorCidades(meta, res, PRES);
  ok(itens.map((x) => x.nome).join() === "LISBOA,TÓQUIO", itens.map((x) => x.nome).join());
  ok(semVoto === 2, `Abuja (zero) e Nova (sem linha): ${semVoto}`);
  ok(exteriorCidades(meta, null, PRES).semVoto === 0, "sem dado nenhum: nada a contar");
});

Deno.test("modo Divergência: só no 1º turno, compara presidente com o cargo legislativo", () => {
  ok(MODOS.some(([k]) => k === "divergencia"), "modo no seletor");
  ok(modoValido("divergencia", 2, { pm: {} }) === "municipios", "2º turno volta para Municípios");
  ok(modoValido("divergencia", 1, {}) === "divergencia", "1º turno mantém");
  ok(cargoDivergencia("presidente") === "depfed" && cargoDivergencia("senador") === "senador", "cargo comparado");
  const m = { pres: "L", depfed: "F", senador: "L", governador: "C" };
  ok(divergencia(m, "presidente").diverge === true, "presidente → depfed");
  ok(divergencia(m, "senador").diverge === false, "mesmo lado");
  ok(divergencia(m, "governador").leg === "C", "centro conta como lado diferente");
  ok(divergencia(m, "governador").diverge === true, "centro diverge");
  ok(divergencia(m, "depest") === null && divergencia(null, "depfed") === null, "sem dado");
  ok(divergencia({ pres: "C", depfed: "F" }, "presidente") === null, "empate para presidente fica fora");
});

Deno.test("contaDivergencia: empate para presidente conta no total e fica fora dos divergentes", async () => {
  const { contaDivergencia } = await import("./calc.js");
  const mu = { a: { pres: "L", depfed: "F" }, b: { pres: "C", depfed: "F" }, c: { pres: "F", depfed: "F" }, d: { pres: "L" } };
  const r = contaDivergencia(mu, "presidente");
  ok(r.n === 1 && r.t === 3 && r.empates === 1, JSON.stringify(r));
});
