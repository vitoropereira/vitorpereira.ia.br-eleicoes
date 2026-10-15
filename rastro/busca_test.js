// deno test rastro/busca_test.js
import "./busca.js";

const { normalizar, escapar, buscar, destacar, linha } = globalThis.RastroBusca;

function igual(a, b) {
  if (a !== b) throw new Error(`esperava ${JSON.stringify(b)}, veio ${JSON.stringify(a)}`);
}

const ITENS = [
  { t: "e", n: "JOÃO DA SILVA", c: "Governador(a) · SP · PL", u: "/rastro/governador/sp/joao-da-silva/", k: "joao da silva", p: 1 },
  { t: "e", n: "TARCÍSIO", c: "Governador(a) · SP · REP", u: "/rastro/#e-1", k: "tarcisio", p: 0 },
  { t: "f", n: "EMPRESA GRANDE LTDA", c: "recebeu R$ 1,00 de 1 campanha", u: "/rastro/fornecedor/33333333000191/", k: "empresa grande ltda 33333333000191" },
  { t: "s", n: "MARIA JOÃO", c: "sócio(a) de EMPRESA GRANDE LTDA", u: "/rastro/fornecedor/33333333000191/", k: "maria joao" },
];

Deno.test("normalizar ignora acento, caixa e espaços", () => {
  igual(normalizar("JOÃO"), "joao");
  igual(normalizar("  José   D'Ávila "), "jose d'avila");
  igual(normalizar("Ñandú  ÇA"), "nandu ca");
});

Deno.test("escapar cobre & < > \" '", () => {
  igual(escapar('<a "x" & y>'), "&lt;a &quot;x&quot; &amp; y&gt;");
  igual(escapar("d'avila"), "d&#39;avila");
});

Deno.test("buscar: sem acento, CNPJ com e sem pontuação, mínimo de 2 caracteres", () => {
  igual(buscar(ITENS, "joao").map((i) => i.n).join("|"), "JOÃO DA SILVA|MARIA JOÃO");
  igual(buscar(ITENS, "33.333.333/0001-91")[0].n, "EMPRESA GRANDE LTDA");
  igual(buscar(ITENS, "33333333000191")[0].n, "EMPRESA GRANDE LTDA");
  igual(buscar(ITENS, "j").length, 0);
  igual(buscar(ITENS, "TARC")[0].u, "/rastro/#e-1");
});

Deno.test("destacar escapa e marca o trecho no nome original", () => {
  igual(destacar("JOÃO DA SILVA", "joao"), "<b>JOÃO</b> DA SILVA");
  igual(destacar('ZÉ "<B>" & CIA', "<b>"), 'ZÉ &quot;<b>&lt;B&gt;</b>&quot; &amp; CIA');
  igual(destacar("<script>", "zz"), "&lt;script&gt;");
});

Deno.test("linha de eleito sem página avisa e escapa o contexto", () => {
  const h = linha({ t: "e", n: "A<B", c: 'X "Y"', u: "/rastro/#e-9", k: "a<b", p: 0 }, "a<", 0);
  igual(h.includes("página ainda não publicada; entra nos próximos lotes"), true);
  igual(h.includes("<b>A&lt;</b>B"), true);
  igual(h.includes("X &quot;Y&quot;"), true);
  igual(h.includes("<script"), false);
});
