// Único lugar com fetch do HUD: arquivos do 1º turno (estáticos), malha, dados da Análise e o ao vivo do 2º turno.

const GEO = "/geo/";
const cache = new Map();

async function json(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) { const e = new Error(`${url}: HTTP ${r.status}`); e.status = r.status; throw e; }
  return r.json();
}

/** arquivo estático do 1º turno (meta, presidente, governador, senador, depfed, depest, serie, feed) — cacheado */
export function t1(nome) {
  const url = `${GEO}t1/${nome}.json`;
  if (!cache.has(url)) cache.set(url, json(url).catch((e) => { cache.delete(url); throw e; }));
  return cache.get(url);
}

/** dados da Análise (/analise/dados/<nome>.json): destaques e divergências; cacheado */
export function analise(nome) {
  const url = `/analise/dados/${nome}.json`;
  if (!cache.has(url)) cache.set(url, json(url).catch((e) => { cache.delete(url); throw e; }));
  return cache.get(url);
}

/** posições e raios do modo Pessoas (municipios/pessoas.py): só pedido quando o modo é escolhido */
export function pessoas() {
  const url = `${GEO}pessoas.json`;
  if (!cache.has(url)) cache.set(url, json(url).catch((e) => { cache.delete(url); throw e; }));
  return cache.get(url);
}

export function malha() {
  const url = `${GEO}municipios.topo.json`;
  if (!cache.has(url)) cache.set(url, json(url).catch((e) => { cache.delete(url); throw e; }));
  return cache.get(url);
}

// ---------------- 2º turno: /vivo/agora.json
// Regras: só faz polling com a aba do 2º turno ativa; 15 s com dado, 60 s enquanto não há dado (400/403/404/erro);
// pausa com a aba do navegador escondida e busca na hora ao voltar; mantém o último estado bom;
// descarta resposta com idg menor ou inválida.
export const VIVO_URL = "/vivo/agora.json";
export const INTERVALO = 15000, INTERVALO_VAZIO = 60000;

const idgNum = (x) => { try { return BigInt(String(x ?? "").replace(/\D/g, "") || "0"); } catch { return 0n; } };
/** "ainda não há dado": 400/403/404 (o rewrite do Storage devolve 400 + "Bucket not found"/NoSuchBucket) ou corpo de erro 404 */
const SEM_DADO = new Set([400, 403, 404]);
const corpoVazio = (d) => !!d && typeof d === "object" && !Array.isArray(d) && (
  String(d.statusCode) === "404" || /NoSuchBucket|not[_ ]found/i.test(`${d.error ?? ""} ${d.code ?? ""} ${d.message ?? ""}`));
const valido = (d) => d && typeof d === "object" && Array.isArray(d.br) && d.mu && typeof d.mu === "object";

/** deps injetáveis para teste: fetch, setTimeout, clearTimeout, doc (document), agora (relógio) */
export function criarVivo(aoMudar, deps = {}) {
  const F = deps.fetch || ((...a) => fetch(...a));
  const ST = deps.setTimeout || ((f, ms) => setTimeout(f, ms)), CT = deps.clearTimeout || ((t) => clearTimeout(t));
  const doc = deps.doc !== undefined ? deps.doc : (typeof document !== "undefined" ? document : null);
  // mudouEm: quando a leitura mudou de fato pela última vez (idg, pst ou eleito); o HUD usa para "aguardando nova leitura"
  const est = { status: "inicial", dados: null, erro: null, ultimoOk: null, falhas: 0, mudouEm: null };
  const AGORA = deps.agora || (() => Date.now());
  let timer = 0, ativo = false, carregando = false;
  const emitir = () => aoMudar({ ...est });

  async function baixar() {
    const r = await F(`${VIVO_URL}?t=${Math.floor(Date.now() / 15000)}`, { cache: "no-store" });
    if (!r.ok) { const e = new Error(`agora.json: HTTP ${r.status}`); e.status = r.status; e.vazio = SEM_DADO.has(r.status); throw e; }
    const d = await r.json();
    if (corpoVazio(d)) { const e = new Error("agora.json: sem dado ainda"); e.vazio = true; throw e; }
    if (!valido(d)) throw new Error("agora.json inválido");
    return d;
  }

  // só o pend mudando não é leitura nova do TSE (o agregador regrava o pend com os mesmos números)
  const chave = (d) => `${d.idg}|${d.pst}|${d.eleito || ""}`;
  function aceitar(d) {
    if (est.dados && idgNum(d.idg) < idgNum(est.dados.idg)) return; // mais velho: descarta
    if (!est.dados || chave(d) !== chave(est.dados)) est.mudouEm = AGORA();
    est.dados = d;
  }

  async function buscar() {
    if (carregando) return;
    carregando = true;
    if (!est.dados) { est.status = "carregando"; emitir(); }
    try {
      aceitar(await baixar());
      est.status = "ok"; est.erro = null; est.falhas = 0; est.ultimoOk = Date.now();
    } catch (e) {
      est.falhas++;
      est.erro = e;
      // sem dado nenhum ainda: estado vazio ("aguardando o TSE"); com dado: mantém o último bom
      est.status = est.dados ? "atrasado" : (e.vazio ? "vazio" : "erro");
    } finally {
      carregando = false;
      emitir();
      agendar();
    }
  }

  function agendar() {
    CT(timer);
    if (!ativo) return;
    timer = ST(() => { if (doc?.hidden) agendar(); else buscar(); }, est.dados ? INTERVALO : INTERVALO_VAZIO);
  }

  const aoVoltar = () => { if (ativo && !doc?.hidden) { CT(timer); buscar(); } };
  doc?.addEventListener?.("visibilitychange", aoVoltar);

  return {
    ativar() { if (ativo) return; ativo = true; buscar(); },
    desativar() { ativo = false; CT(timer); },
    /** 1 leitura sem polling: o HUD abre direto no 2º turno quando o agora.json já existe */
    async sondar() {
      try { aceitar(await baixar()); est.status = "ok"; est.ultimoOk = Date.now(); emitir(); return true; }
      catch { return false; }
    },
    get estado() { return { ...est }; },
  };
}

/** feed.json e serie/index.json do 2º turno (null se ainda não existem) */
export async function vivoExtra(nome, F = (...a) => fetch(...a)) {
  try {
    const r = await F(`/vivo/${nome}?t=${Math.floor(Date.now() / 15000)}`, { cache: "no-store" });
    if (!r.ok) return null;
    const d = await r.json();
    return corpoVazio(d) ? null : d;
  } catch { return null; }
}

/** agora.json de um minuto da noite (/vivo/serie/HHMM.json), com cache LRU de 16 */
const lru = new Map();
export async function vivoMinuto(t, F = (...a) => fetch(...a), signal) {
  const k = String(t).replace(":", "");
  if (lru.has(k)) { const v = lru.get(k); lru.delete(k); lru.set(k, v); return v; }
  const r = await F(`/vivo/serie/${k}.json`, signal ? { signal } : undefined);
  if (!r.ok) { const e = new Error(`serie/${k}: HTTP ${r.status}`); e.status = r.status; e.vazio = SEM_DADO.has(r.status); throw e; }
  const d = await r.json();
  if (corpoVazio(d)) { const e = new Error(`serie/${k}: sem dado ainda`); e.vazio = true; throw e; }
  lru.set(k, d); if (lru.size > 16) lru.delete(lru.keys().next().value);
  return d;
}

/**
 * Leitor do minuto da linha do tempo: cada pedido novo cancela o anterior (AbortController) e resposta velha é
 * descartada (devolve null). Falha devolve {t, erro}: quem chama mantém o minuto escolhido e avisa, sem cair no ao vivo.
 */
export function criarMinuto(F = (...a) => fetch(...a)) {
  let n = 0, ctl = null;
  return {
    async ler(t) {
      const id = ++n;
      ctl?.abort();
      ctl = typeof AbortController !== "undefined" ? new AbortController() : null;
      try {
        const dados = await vivoMinuto(t, F, ctl?.signal);
        return id === n ? { t, dados } : null;
      } catch (erro) {
        return id === n ? { t, erro } : null;
      }
    },
    cancelar() { n++; ctl?.abort(); ctl = null; },
  };
}
