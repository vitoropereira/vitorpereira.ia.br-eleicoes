// deno test hud/  — botão "☰ Seções" (issue 138) com um DOM falso mínimo
import { ligarSecoes } from "./secoes.js";
const assertEquals = (a, b) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${JSON.stringify(a)} != ${JSON.stringify(b)}`); };

function alvo() {
  const ouv = {};
  return {
    ouv,
    addEventListener: (t, f) => { (ouv[t] ||= []).push(f); },
    removeEventListener: (t, f) => { ouv[t] = (ouv[t] || []).filter((x) => x !== f); },
    disparar: (t, e = {}) => { for (const f of ouv[t] || []) f({ preventDefault() {}, ...e }); },
  };
}

function montar() {
  const doc = alvo();
  doc.activeElement = null;
  const el = (nome) => ({ ...alvo(), nome, focus() { doc.activeElement = this; } });
  const links = [el("a1"), el("a2")];
  const attrs = { "aria-expanded": "false" };
  const bt = { ...el("bt"), getAttribute: (k) => attrs[k], setAttribute: (k, v) => { attrs[k] = String(v); } };
  const nav = { hidden: true, querySelector: (s) => (s === "a" ? links[0] : null) };
  const dentro = new Set([bt, nav, ...links]);
  const raiz = { ...alvo(), dataset: {}, querySelector: (s) => (s === "button" ? bt : s === "nav" ? nav : null), contains: (n) => n === raiz || dentro.has(n) };
  return { doc, raiz, bt, nav, links, attrs };
}

Deno.test("clicar no botão abre, marca aria-expanded e leva o foco ao primeiro link; clicar de novo fecha", () => {
  const m = montar();
  ligarSecoes(m.raiz, m.doc);
  assertEquals([m.attrs["aria-expanded"], m.nav.hidden], ["false", true]);
  m.bt.disparar("click");
  assertEquals([m.attrs["aria-expanded"], m.nav.hidden, m.doc.activeElement?.nome], ["true", false, "a1"]);
  m.bt.disparar("click");
  assertEquals([m.attrs["aria-expanded"], m.nav.hidden], ["false", true]);
});

Deno.test("Esc fecha e devolve o foco ao botão", () => {
  const m = montar();
  ligarSecoes(m.raiz, m.doc);
  m.bt.disparar("click");
  m.doc.disparar("keydown", { key: "Escape" });
  assertEquals([m.attrs["aria-expanded"], m.nav.hidden, m.doc.activeElement?.nome], ["false", true, "bt"]);
});

Deno.test("Esc com o menu fechado não rouba o foco", () => {
  const m = montar();
  ligarSecoes(m.raiz, m.doc);
  m.doc.activeElement = { nome: "busca" };
  m.doc.disparar("keydown", { key: "Escape" });
  assertEquals(m.doc.activeElement.nome, "busca");
});

Deno.test("clicar fora fecha; clicar dentro não", () => {
  const m = montar();
  ligarSecoes(m.raiz, m.doc);
  m.bt.disparar("click");
  m.doc.disparar("click", { target: m.links[1] });
  assertEquals(m.nav.hidden, false);
  m.doc.disparar("click", { target: { nome: "mapa" } });
  assertEquals([m.attrs["aria-expanded"], m.nav.hidden], ["false", true]);
});

Deno.test("foco saindo do menu (Tab) fecha", () => {
  const m = montar();
  ligarSecoes(m.raiz, m.doc);
  m.bt.disparar("click");
  m.raiz.disparar("focusout", { relatedTarget: m.links[1] });
  assertEquals(m.nav.hidden, false);
  m.raiz.disparar("focusout", { relatedTarget: { nome: "fora" } });
  assertEquals(m.nav.hidden, true);
});

Deno.test("desligar remove os ouvintes; ligar duas vezes não duplica", () => {
  const m = montar();
  const desliga = ligarSecoes(m.raiz, m.doc);
  ligarSecoes(m.raiz, m.doc);
  assertEquals((m.bt.ouv.click || []).length, 1);
  desliga();
  assertEquals([(m.bt.ouv.click || []).length, (m.doc.ouv.click || []).length, (m.doc.ouv.keydown || []).length], [0, 0, 0]);
});
