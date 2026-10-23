// deno test hud/  — a função api/vivo.js (o teste fica aqui: todo arquivo em api/ vira função na Vercel)
import handler, { CACHE, caminhoValido, ORIGEM } from "../api/vivo.js";

const assertEquals = (a, b, m) => {
  if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${m || "diferente"}: ${JSON.stringify(a)} != ${JSON.stringify(b)}`);
};

const origemFalsa = (status, corpo = "{}", headers = {}) => {
  const pedidos = [];
  const f = async (url) => {
    pedidos.push(url);
    return new Response(status === 200 ? corpo : "erro", {
      status,
      headers: { "set-cookie": "__cf_bm=x", "cache-control": "private, no-cache", ...headers },
    });
  };
  return { f, pedidos };
};
const req = (p) => new Request(`https://eleicoes2026.vitorpereira.ia.br/api/vivo?p=${encodeURIComponent(p)}&t=1`);

Deno.test("caminhos do HUD passam; travessia e lixo não", () => {
  for (const ok of ["agora.json", "feed.json", "serie/index.json", "serie/1810.json"]) assertEquals(caminhoValido(ok), true, ok);
  for (const ruim of ["../x.json", "/agora.json", "a/../b.json", "agora", "agora.json?x", "", null, "a//b.json", "https://x/a.json"])
    assertEquals(caminhoValido(ruim), false, String(ruim));
});

Deno.test("200: sem o set-cookie da origem e com s-maxage (o CDN guarda)", async () => {
  const { f, pedidos } = origemFalsa(200, '{"a":1}', { etag: '"e1"', "content-type": "application/json" });
  const r = await handler(req("serie/1810.json"), f);
  assertEquals(pedidos, [ORIGEM + "serie/1810.json"]);
  assertEquals(r.status, 200);
  assertEquals(r.headers.get("set-cookie"), null);
  assertEquals(r.headers.get("cache-control"), CACHE);
  assertEquals(r.headers.get("etag"), '"e1"');
  assertEquals(await r.text(), '{"a":1}');
});

Deno.test("objeto inexistente (400 ou 404 do Storage) vira 404 em cache curto", async () => {
  for (const st of [400, 404]) {
    const r = await handler(req("agora.json"), origemFalsa(st).f);
    assertEquals(r.status, 404);
    assertEquals(r.headers.get("cache-control"), "public, s-maxage=15");
    assertEquals(r.headers.get("set-cookie"), null);
  }
});

Deno.test("erro da origem não entra em cache", async () => {
  const r = await handler(req("agora.json"), origemFalsa(500).f);
  assertEquals(r.status, 502);
  assertEquals(r.headers.get("cache-control"), "no-store");
});

Deno.test("caminho inválido não chega à origem", async () => {
  const { f, pedidos } = origemFalsa(200);
  const r = await handler(req("../segredo.json"), f);
  assertEquals(r.status, 400);
  assertEquals(pedidos, []);
});
