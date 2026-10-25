// Uma rodada do agregador: descobre a eleição, lê o TSE, monta e grava no bucket `vivo`.
import { type Armazenamento, gravarAtomico } from "./gravar.ts";
import { type Evento, gerarEventos, mesclarFeed } from "./feed.ts";
import {
  type Agora,
  type Cand,
  eleitos,
  extrairCandidatos,
  type Linha,
  linhaDe,
  montarAgora,
  type ResumoArquivo,
  resumoArquivo,
  usarNacional,
  validarAgora,
} from "./montar.ts";
import {
  caminhoMunicipio,
  caminhoMunicipios,
  caminhoUf,
  descobrirEleicao,
  extrairMunicipios,
  LimiteTse,
  type ListaMunicipios,
  type Tse,
} from "./tse.ts";

export interface EstadoUf extends ResumoArquivo {
  etag: string | null;
}

export interface Estado {
  ele: string | null;
  ultimoIdg: string; // maior idg já gravado em agora.json
  ultimoPst: number;
  uf: Record<string, EstadoUf>; // só UFs com todos os municípios confirmados
  mun: Record<string, string>; // "UF:cd" -> etag
  munList: ListaMunicipios | null;
  pendentes: string[]; // UFs que mudaram e ficaram para a próxima rodada
  eleito: string | null; // número do candidato já anunciado como eleito
  travaAte: number; // epoch ms; evita rodadas sobrepostas
  dono: string; // id da rodada que detém a trava
  pausaAte: number; // epoch ms; enquanto no futuro, nenhuma rodada fala com o TSE (disjuntor entre rodadas)
  pausaMs: number; // duração da última pausa: 2 -> 4 -> 8 min; zera numa rodada sem 429
}

export const estadoVazio = (): Estado => ({
  ele: null,
  ultimoIdg: "0",
  ultimoPst: 0,
  uf: {},
  mun: {},
  munList: null,
  pendentes: [],
  eleito: null,
  travaAte: 0,
  dono: "",
  pausaAte: 0,
  pausaMs: 0,
});

export interface Deps {
  tse: Tse;
  st: Armazenamento;
  agora: () => number; // epoch ms (injetável nos testes)
  orcamentoMs?: number; // padrão 120 s
  margemMs?: number; // parar de buscar municípios com menos que isto sobrando (padrão 20 s)
  concorrencia?: number; // padrão 16, mínimo 1
  /** Ensaio: usa este código em vez de descobrir o de 2º turno. Nunca em produção. */
  eleicaoForcada?: string;
  log?: (...a: unknown[]) => void;
}

export type Resultado =
  | { status: "sem-eleicao" }
  | { status: "ocupado" }
  | { status: "pausa"; ate: number }
  | { status: "trava-perdida" }
  | { status: "sem-dados"; motivo: string }
  | { status: "sem-mudanca"; pendentes: string[] }
  | { status: "idg-regressivo"; novo: string; ultimo: string }
  | {
    status: "gravado";
    idg: string;
    t: string;
    pst: number;
    ufsAtualizadas: string[];
    pendentes: string[];
    ms: number;
  };

const parse = (s: string | null): any => {
  if (!s) return null;
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
};

/** Semáforo FIFO: no máximo `n` tarefas simultâneas. */
function limitador(n: number) {
  let ativos = 0;
  const fila: (() => void)[] = [];
  return async <T>(fn: () => Promise<T>): Promise<T> => {
    if (ativos >= n) await new Promise<void>((ok) => fila.push(ok));
    ativos++;
    try {
      return await fn();
    } finally {
      ativos--;
      fila.shift()?.();
    }
  };
}

export const CONCORRENCIA_PADRAO = 16; // medido em 08/10: 16 conexões, ~145 req/s, 0 respostas 429 (PROPOSTA.md, Riscos)
/** Conexões simultâneas ao TSE. Vazio/inválido (inclusive `""` vindo do env, que Number() viraria 0) = padrão; mínimo 1. */
export const normalizarConcorrencia = (n: number | string | undefined | null): number => {
  if (typeof n === "string" && n.trim() === "") return CONCORRENCIA_PADRAO;
  const x = typeof n === "string" ? Number(n.trim()) : n;
  return typeof x === "number" && Number.isFinite(x) ? Math.max(1, Math.floor(x)) : CONCORRENCIA_PADRAO;
};

const PAUSA_INICIAL_MS = 120_000;
const PAUSA_MAXIMA_MS = 480_000;

const big = (s: unknown): bigint => {
  try {
    return BigInt(String(s));
  } catch {
    return 0n;
  }
};

const mesmoConjunto = (a: Cand[], b: Cand[]) =>
  a.length === b.length && new Set(a.map((c) => c.n)).size === new Set([...a, ...b].map((c) => c.n)).size;

const valido = (a: any, ele: string): Agora | null => (a && a.ele === ele && validarAgora(a).length === 0 ? a : null);

const hhmmBrasilia = (ms: number) => new Date(ms - 3 * 3600_000).toISOString().slice(11, 16);

export async function executar(deps: Deps): Promise<Resultado> {
  const { tse, st } = deps;
  const log = deps.log ?? (() => {});
  const orcamento = deps.orcamentoMs ?? 120_000;
  const margem = deps.margemMs ?? 20_000;
  const limite = limitador(normalizarConcorrencia(deps.concorrencia));
  const t0 = deps.agora();
  let limitado = false; // o TSE mandou 429: para de buscar nesta rodada (disjuntor)
  const estourou = () => limitado || deps.agora() - t0 > orcamento - margem;

  /** Libera a trava e aplica o disjuntor entre rodadas (pausa 2 -> 4 -> 8 min se houve 429; zera se não). */
  const salvar = async (e: Estado) => {
    e.travaAte = 0;
    e.dono = "";
    if (limitado) {
      e.pausaMs = Math.min(e.pausaMs > 0 ? e.pausaMs * 2 : PAUSA_INICIAL_MS, PAUSA_MAXIMA_MS);
      e.pausaAte = t0 + e.pausaMs;
      log(`TSE limitou o acesso; pausa de ${e.pausaMs / 60_000} min`);
    } else {
      e.pausaMs = 0;
      e.pausaAte = 0;
    }
    await st.enviar("_estado.json", JSON.stringify(e), 0);
  };

  // 1) estado e pausa
  let estado: Estado = { ...estadoVazio(), ...(parse(await st.ler("_estado.json")) ?? {}) };
  if (estado.pausaAte > t0) {
    log(`em pausa até ${new Date(estado.pausaAte).toISOString()}`);
    return { status: "pausa", ate: estado.pausaAte };
  }

  // 2) eleição: usa a do estado; só redescobre quando ausente
  let ele: string | null = deps.eleicaoForcada ?? estado.ele;
  if (deps.eleicaoForcada) log(`ATENÇÃO: eleição forçada para ${ele} (ensaio)`);
  if (!ele) {
    try {
      ele = await descobrirEleicao(tse);
    } catch (err) {
      log(`TSE indisponível ao descobrir a eleição: ${err}`);
      if (err instanceof LimiteTse) {
        limitado = true;
        await salvar(estado);
      }
      return { status: "sem-dados", motivo: `TSE indisponível: ${err}` };
    }
  }
  if (!ele) {
    log("2º turno federal ainda não publicado em ele-c.json; nada a fazer");
    return { status: "sem-eleicao" };
  }
  if (estado.ele !== ele) estado = { ...estadoVazio(), ele };
  if (estado.travaAte > t0) {
    log("rodada anterior ainda em andamento");
    return { status: "ocupado" };
  }
  const dono = crypto.randomUUID();
  const original = structuredClone(estado);
  estado.travaAte = t0 + orcamento + 30_000;
  estado.dono = dono;
  await st.enviar("_estado.json", JSON.stringify(estado), 0);

  try {
    // 3) lista de municípios (estática: fica no estado)
    if (!estado.munList) {
      const r = await tse.buscar(caminhoMunicipios(ele));
      if (r.status !== 200) {
        await salvar(original);
        return { status: "sem-dados", motivo: "lista de municípios indisponível" };
      }
      estado.munList = extrairMunicipios(r.json);
    }
    const lista = estado.munList;
    const ufs = Object.keys(lista).sort(); // todas as UFs que o TSE lista (27 + ZZ) são obrigatórias para publicar

    // 4) base: o rascunho (_parcial.json) ou, na falta dele, o publicado. `publicado` serve ao feed.
    const publicado = valido(parse(await st.ler("agora.json")), ele);
    let prev: Agora | null = valido(parse(await st.ler("_parcial.json")), ele) ?? publicado;
    if (!prev) {
      estado.uf = {};
      estado.mun = {};
    }

    // 5) arquivos de UF (+ZZ), com ETag
    const semLeitura = new Set<string>(); // UFs cujo arquivo não deu para ler nesta rodada (429/erro)
    const lidos = await Promise.all(ufs.map((uf) =>
      limite(async () => {
        try {
          const r = await tse.buscar(caminhoUf(ele, uf), estado.uf[uf]?.etag);
          return { uf, r };
        } catch (e) {
          if (e instanceof LimiteTse) limitado = true;
          log(`UF ${uf}: erro ${e}`);
          semLeitura.add(uf);
          return { uf, r: { status: 304 as const } };
        }
      })
    ));
    // 5b) arquivo Brasil do TSE, sem ETag (um GET por rodada). Erro ou 404 = o total segue sendo a soma das UFs.
    let nacionalJson: any = null;
    if (!limitado) {
      try {
        const r = await tse.buscar(caminhoUf(ele, "br"));
        if (r.status === 200) nacionalJson = r.json;
      } catch (e) {
        if (e instanceof LimiteTse) limitado = true;
        log(`Brasil: erro ${e}`);
      }
    }
    const novos: Record<string, { json: any; resumo: ResumoArquivo; etag: string | null }> = {};
    let cand: Cand[] = prev?.cand ?? [];
    let frescos: Cand[] | null = null; // candidatos do primeiro arquivo novo
    let eleitoNovo: Cand | null = null;
    for (const { uf, r } of lidos) {
      if (r.status === 404) {
        log(`UF ${uf}: ainda não publicada`);
        continue;
      }
      if (r.status !== 200) continue;
      const resumo = resumoArquivo(r.json);
      const velho = estado.uf[uf];
      if (velho && big(resumo.idg) < big(velho.idg)) {
        log(`UF ${uf}: idg ${resumo.idg} < ${velho.idg} já aceito; arquivo ignorado`);
        continue;
      }
      if (velho && velho.idg === resumo.idg && velho.pst === resumo.pst && prev?.uf[uf]) {
        estado.uf[uf] = { ...velho, etag: r.etag }; // só o ETag mudou
        continue;
      }
      novos[uf] = { json: r.json, resumo, etag: r.etag };
      const c = extrairCandidatos(r.json);
      if (c.length > 0 && !frescos) frescos = c;
      const el = eleitos(r.json)[0];
      if (el && estado.eleito !== el.n) eleitoNovo = c.find((x) => x.n === el.n) ?? el;
    }
    // conjunto de candidatos mudou (por número): o que está salvo não serve mais
    if (frescos) {
      if (prev && !mesmoConjunto(prev.cand, frescos)) {
        log("conjunto de candidatos mudou; recomeçando do zero");
        prev = null;
        estado.uf = {};
        estado.mun = {};
        cand = frescos;
      } else if (cand.length === 0) cand = frescos;
    }
    const candFinal = cand;

    // 6) trabalho em memória: parte da base, troca UF por UF
    const uf: Record<string, Linha> = structuredClone(prev?.uf ?? {});
    const mu: Record<string, Linha> = structuredClone(prev?.mu ?? {});
    const ex: Record<string, Linha> = structuredClone(prev?.ex ?? {});
    const pu: Record<string, number> = structuredClone(prev?.pu ?? {});
    const pm: Record<string, number> = structuredClone(prev?.pm ?? {});
    const prioridade = (u: string) => (estado.pendentes.includes(u) ? 0 : 1);
    const mudadas = Object.keys(novos).sort((a, b) => prioridade(a) - prioridade(b) || a.localeCompare(b));
    const confirmadas: string[] = [];
    const etagsMun: Record<string, string> = {};

    await Promise.all(mudadas.map(async (u) => {
      const { json, resumo, etag } = novos[u];
      const alvos = (lista[u] ?? []).filter((m) => u === "ZZ" || m.cdi);
      const linhasMun: Record<string, { linha: Linha; pst: number }> = {};
      const etagsLocais: Record<string, string> = {};
      let completo = true;
      await Promise.all(alvos.map((m) =>
        limite(async () => {
          if (!completo) return;
          if (estourou()) {
            completo = false;
            return;
          }
          const chave = u === "ZZ" ? m.cd : m.cdi;
          const chaveEtag = `${u}:${m.cd}`;
          const existente = (u === "ZZ" ? ex : mu)[chave];
          try {
            const r = await tse.buscar(caminhoMunicipio(ele, u, m.cd), existente ? estado.mun[chaveEtag] : null);
            if (r.status === 200) {
              linhasMun[chave] = { linha: linhaDe(r.json, candFinal), pst: resumoArquivo(r.json).pst };
              if (r.etag) etagsLocais[chaveEtag] = r.etag;
            } else if (r.status === 404 && !existente) {
              log(`município ${u}/${m.cd}: ainda não publicado`);
            }
          } catch (e) {
            if (e instanceof LimiteTse) limitado = true;
            log(`município ${u}/${m.cd}: erro ${e}`);
            completo = false;
          }
        })
      ));
      if (!completo) return; // UF fica inteira como estava; tenta de novo na próxima rodada
      // commit atômico da UF em memória
      uf[u] = linhaDe(json, candFinal);
      pu[u] = resumo.pst;
      for (const [k, v] of Object.entries(linhasMun)) {
        (u === "ZZ" ? ex : mu)[k] = v.linha;
        if (u !== "ZZ") pm[k] = v.pst;
      }
      Object.assign(etagsMun, etagsLocais);
      estado.uf[u] = { ...resumo, etag };
      confirmadas.push(u);
    }));
    Object.assign(estado.mun, etagsMun);
    // atrasadas: as que mudaram e não fecharam, mais as que já estavam atrasadas e nem deu para ler nesta rodada
    const pendAntes = new Set([...estado.pendentes, ...(publicado?.pend ?? [])]);
    estado.pendentes = [
      ...new Set([
        ...mudadas.filter((u) => !confirmadas.includes(u)),
        ...[...semLeitura].filter((u) => pendAntes.has(u)),
      ]),
    ].sort();
    if (estado.pendentes.length > 0) {
      log(
        `orçamento/erro: ${estado.pendentes.length} UF(s) ficam para a próxima rodada: ${estado.pendentes.join(",")}`,
      );
    }

    const faltando = ufs.filter((u) => !(u in uf));
    // total do país: arquivo Brasil quando ele está à frente da soma das UFs (ver usarNacional)
    const nacional = nacionalJson && candFinal.length > 0
      ? { linha: linhaDe(nacionalJson, candFinal), resumo: resumoArquivo(nacionalJson) }
      : null;
    const stUfs = Object.keys(uf).reduce((s, u) => s + (estado.uf[u]?.st ?? 0), 0);
    const pstNacional = nacional && usarNacional(nacional, stUfs)
      ? Math.round((nacional.resumo.st / nacional.resumo.ts) * 10000) / 100
      : null;
    // o total publicado ficou para trás: o Brasil andou (ou deixou de estar à frente) sem nenhuma UF mudar
    const nacionalMudou = !!publicado &&
      (pstNacional !== null ? publicado.total !== "tse" || publicado.pst !== pstNacional : publicado.total === "tse");
    // a base já estava completa e mais nova que o último publicado (ex.: rodada anterior caiu antes de publicar)
    const republicar = confirmadas.length === 0 && !!prev && faltando.length === 0 &&
      (big(prev.idg) > big(estado.ultimoIdg) || nacionalMudou);
    if (confirmadas.length === 0 && !republicar) {
      // nada novo para publicar, mas se o conjunto de UFs atrasadas mudou, o agora.json publicado passa a dizer isso
      // (mesmos números e mesmo idg; o HUD mostra "UFs atualizando" e a hora `t` da última leitura)
      const pendNovo = estado.pendentes.filter((u) => publicado && u in publicado.uf).sort();
      if (publicado && faltando.length === 0 && pendNovo.join() !== [...(publicado.pend ?? [])].sort().join()) {
        const atual = parse(await st.ler("_estado.json"));
        if (!atual || atual.dono !== dono || atual.travaAte < deps.agora()) {
          log("trava perdida para outra rodada; abortando sem gravar");
          return { status: "trava-perdida" };
        }
        await gravarAtomico(st, "agora.json", JSON.stringify({ ...publicado, pend: pendNovo }));
      }
      await salvar(estado);
      return faltando.length > 0 && (prev || mudadas.length > 0)
        ? { status: "sem-dados", motivo: `UFs faltando: ${faltando.join(",")}` }
        : prev || mudadas.length === 0
        ? { status: "sem-mudanca", pendentes: estado.pendentes }
        : { status: "sem-dados", motivo: "nenhuma UF completa dentro do orçamento" };
    }

    // 7) montar e validar
    const meta: Record<string, ResumoArquivo> = {};
    for (const u of Object.keys(uf)) if (estado.uf[u]) meta[u] = estado.uf[u];
    // resultado oficial: só quando o TSE marca (nunca deduzido de %); depois de marcado, segue nas próximas publicações
    const eleito = eleitoNovo?.n ?? estado.eleito;
    const agora = montarAgora({
      ele,
      cand: candFinal,
      uf,
      mu,
      ex,
      pu,
      pm,
      meta,
      pend: estado.pendentes,
      eleito,
      nacional,
    });
    if (!/^\d\d:\d\d$/.test(agora.t)) agora.t = hhmmBrasilia(deps.agora());
    const erros = validarAgora(agora);
    if (erros.length > 0) throw new Error(`agora.json inválido: ${erros.slice(0, 3).join("; ")}`);

    // 8) guarda: idg nunca regride (só vale para o que vai ser publicado)
    if (faltando.length === 0 && big(agora.idg) < big(original.ultimoIdg)) {
      log(`idg ${agora.idg} < último gravado ${original.ultimoIdg}; não grava`);
      await salvar(original);
      return { status: "idg-regressivo", novo: agora.idg, ultimo: original.ultimoIdg };
    }

    // 8b) ainda somos o dono da trava? Senão outra rodada assumiu e gravar aqui pisaria nela.
    const atual = parse(await st.ler("_estado.json"));
    if (!atual || atual.dono !== dono || atual.travaAte < deps.agora()) {
      log("trava perdida para outra rodada; abortando sem gravar");
      return { status: "trava-perdida" };
    }

    // 9) rascunho sempre; publicação só com todas as UFs
    const corpo = JSON.stringify(agora);
    await gravarAtomico(st, "_parcial.json", corpo, 0);
    if (faltando.length > 0) {
      await salvar(estado);
      return { status: "sem-dados", motivo: `UFs faltando: ${faltando.join(",")}` };
    }

    // série e feed primeiro, agora.json por último, estado no fim
    await gravarAtomico(st, `serie/${agora.t.replace(":", "")}.json`, corpo, 3600);

    const indice: any[] = parse(await st.ler("serie/index.json")) ?? [];
    const entrada = { t: agora.t, idg: agora.idg, pst: agora.pst, br: agora.br };
    const novoIndice = [...indice.filter((e) => e?.t !== agora.t), entrada].sort((a, b) => a.t.localeCompare(b.t));
    await gravarAtomico(st, "serie/index.json", JSON.stringify(novoIndice));

    const feedAntigo: Evento[] = parse(await st.ler("feed.json")) ?? [];
    const eventos = gerarEventos(publicado, agora, eleitoNovo);
    await gravarAtomico(st, "feed.json", JSON.stringify(mesclarFeed(feedAntigo, eventos)));

    await gravarAtomico(st, "agora.json", corpo);

    estado.ultimoIdg = agora.idg;
    estado.ultimoPst = agora.pst;
    if (eleitoNovo) estado.eleito = eleitoNovo.n;
    await salvar(estado);

    return {
      status: "gravado",
      idg: agora.idg,
      t: agora.t,
      pst: agora.pst,
      ufsAtualizadas: confirmadas.sort(),
      pendentes: estado.pendentes,
      ms: deps.agora() - t0,
    };
  } catch (e) {
    await salvar(original).catch(() => {});
    throw e;
  }
}
