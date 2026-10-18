// deno test hud/  — contador do cabeçalho (sitebar) com assinatura falsa
import { montar, rotulo, texto } from "./topo-pessoas.js";
const assertEquals = (a, b) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${JSON.stringify(a)} != ${JSON.stringify(b)}`); };

function falsoEl() {
  const b = { textContent: "" };
  const attrs = {};
  return {
    b, attrs, hidden: true, title: "",
    dataset: { url: "https://abc.exemplo.test", key: "sb_publishable_x", canal: "eleicoes-hud" },
    querySelector: (s) => (s === "b" ? b : null),
    setAttribute: (k, v) => { attrs[k] = v; },
  };
}

Deno.test("texto e rótulo: milhar pt-BR, singular e lotado", () => {
  assertEquals(texto(1234), "1.234");
  assertEquals(texto("100+"), "100+");
  assertEquals(rotulo(1), "1 pessoa no site agora");
  assertEquals(rotulo(7), "7 pessoas no site agora");
});

Deno.test("montar: lê a config do data-*, mostra o número e esconde com null", () => {
  const el = falsoEl();
  let cfg, cb;
  const desliga = () => {};
  const ret = montar(el, (c, f) => { cfg = c; cb = f; return desliga; });
  assertEquals(ret, desliga);
  assertEquals(cfg, { url: "https://abc.exemplo.test", key: "sb_publishable_x", canal: "eleicoes-hud" });
  assertEquals(el.hidden, true);
  cb(12);
  assertEquals([el.hidden, el.b.textContent, el.attrs["aria-label"]], [false, "12", "12 pessoas no site agora"]);
  cb("100+");
  assertEquals(el.b.textContent, "100+");
  cb(null);
  assertEquals(el.hidden, true);
});

Deno.test("montar: sem o <b>, não assina", () => {
  let chamou = false;
  montar({ querySelector: () => null, dataset: {} }, () => { chamou = true; });
  assertEquals(chamou, false);
});
