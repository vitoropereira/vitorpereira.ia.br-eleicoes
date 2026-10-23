// /vivo/* → esta função (rewrite no vercel.json) → bucket `vivo` do Supabase Storage.
// Por que uma função e não o rewrite direto: o Storage responde com `set-cookie` (__cf_bm, do Cloudflare dele) e
// `cache-control: private, no-cache`, e o CDN da Vercel não guarda resposta com set-cookie. Sem cache, cada poll de
// cada visitante (a cada 15 s) ia direto ao Supabase do plano grátis. Aqui a resposta sai sem o cookie e com s-maxage:
// o Supabase recebe ~1 pedido por arquivo a cada 15 s por região da Vercel, não 1 por visitante (22/10/2026).
export const config = { runtime: "edge" };

export const ORIGEM = "https://qzczyicspbizosjogmlq.supabase.co/storage/v1/object/public/vivo/";
export const CACHE = "public, s-maxage=15, stale-while-revalidate=30";

/** Só caminhos do bucket que o HUD lê: segmentos simples terminando em .json, sem `..` nem barra inicial. */
export function caminhoValido(p) {
  return typeof p === "string" && /^[A-Za-z0-9_-]+(\/[A-Za-z0-9_-]+)*\.json$/.test(p);
}

export default async function handler(req, origem = fetch) {
  const p = new URL(req.url).searchParams.get("p");
  if (!caminhoValido(p)) return new Response("caminho inválido", { status: 400 });
  const r = await origem(ORIGEM + p);
  // o Storage responde objeto inexistente com 400 ou 404: os dois viram 404 em cache curto (o arquivo do 2º turno
  // ainda não existe e cada visitante bateria na origem); erro da origem (5xx) não entra em cache
  const falta = r.status === 400 || r.status === 404;
  const status = r.ok ? 200 : falta ? 404 : 502;
  const h = new Headers({
    "content-type": r.ok ? r.headers.get("content-type") || "application/json" : "text/plain; charset=utf-8",
    "access-control-allow-origin": "*",
    "cache-control": r.ok ? CACHE : falta ? "public, s-maxage=15" : "no-store",
  });
  const etag = r.ok && r.headers.get("etag");
  if (etag) h.set("etag", etag);
  return new Response(r.ok ? await r.arrayBuffer() : falta ? "não encontrado" : "origem indisponível", { status, headers: h });
}
