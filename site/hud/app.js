// HUD da apuração: estado da página, cabeçalho, mapa, linha do tempo, busca, Exterior e acessibilidade.
import { html, render, useState, useEffect, useMemo, useRef, useCallback, useErrorBoundary } from "/vendor/preact-htm.module.js";
import { t1, malha, analise, criarVivo, vivoExtra, criarMinuto } from "./dados.js";
import { decodificar, decodificarUFs } from "./topo.js";
import { Mapa } from "./mapa.js";
import { assinarPresenca } from "./presenca.js";
import { limparCache, token, misturar } from "./partidos.js";
import {
  UF_NOME, UFS, CARGOS, CARGO_NOME, MODOS, pct, int, titulo, semAcento, linha, linhaSerie, corPara, cor, ehDep, comSigla, textoComSigla, curta,
} from "./calc.js";
import { oficial, duelo, resumoLeitor, fonteTurno2, modoValido, serieTurno2, eleitoTurno2, situacaoVivo, exteriorCidades } from "./calc.js";
import { divergencia, cargoDivergencia, contaDivergencia, LADO_TOKEN, LADO_NOME } from "./calc.js";
import { Placar, ResumoUFs, ResumoDep, PorRegiao, Feed, Sw, Nome } from "./paineis.js";

const DESKTOP = () => matchMedia("(min-width: 1024px)").matches;
// spec §9: aparelho fraco ou economia de dados abre em Estados com a malha leve das UFs;
// a malha municipal só vem quando a pessoa escolhe outro modo, aproxima ou busca um município
const BAIXO = (typeof navigator !== "undefined") && ((navigator.deviceMemory && navigator.deviceMemory < 2) || !!navigator.connection?.saveData);

// ---------------- pequena "store" para a dica (evita re-renderizar a página a cada movimento do mouse)
const dicaSubs = new Set();
let dicaAtual = null;
const setDica = (d) => { dicaAtual = d; dicaSubs.forEach((f) => f(d)); };

// ---------------- um painel com erro não derruba a página
function Seguro({ children }) {
  const [erro, limpar] = useErrorBoundary((e) => console.error("[hud]", e));
  if (erro) return html`<p class="vazio-txt">Não deu para mostrar este bloco. <button type="button" class="link" onClick=${limpar}>Tentar de novo</button></p>`;
  return children;
}

// ---------------- ícones (traço, currentColor)
const Ic = {
  busca: html`<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>`,
  globo: html`<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 3 2.5 15 0 18M12 3c-2.5 3-2.5 15 0 18"/></svg>`,
  cheia: html`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>`,
  mais: html`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>`,
  menos: html`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14"/></svg>`,
  brasil: html`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h6M4 4v6M20 20h-6M20 20v-6M20 4l-6 6M4 20l6-6"/></svg>`,
  x: html`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>`,
  olho: html`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>`,
};

// ---------------- "pessoas agora": presença no Supabase Realtime (hud/presenca.js); o build define
// window.HUD_PRESENCE = { url, key, canal } (key = publishable, pública por desenho). Sem config ou com erro: nada aparece.
function PessoasAgora() {
  const P = typeof window !== "undefined" ? window.HUD_PRESENCE : undefined;
  const [n, setN] = useState(null);
  useEffect(() => { try { return assinarPresenca(P, setN); } catch { setN(null); return undefined; } }, [P]);
  if (!P || n == null) return null;
  return html`<span class="pessoas">${Ic.olho}<b>${typeof n === "string" ? n : int(n)}</b> ${n === 1 ? "pessoa" : "pessoas"} agora</span>`;
}

// ---------------- cabeçalho
function Topo({ turno, setTurno, cargo, setCargo, status, onBusca, onExterior, onCheia, cheia }) {
  return html`
    <header class="hud-top">
      <a class="marca" href="/" aria-label="Eleições 2026, por Vitor Pereira (início)">
        <span class="wm">vitor<span class="dim">pereira</span><span class="cursor" aria-hidden="true"></span></span>
        <span class="sep" aria-hidden="true">/</span><span class="ctx">eleições 2026</span>
      </a>
      <div class="seg turnos" role="group" aria-label="Turno">
        ${[1, 2].map((t) => html`<button type="button" aria-pressed=${turno === t} onClick=${() => setTurno(t)}>${t}º turno</button>`)}
      </div>
      <div class="seg cargos" role="group" aria-label="Cargo">
        ${CARGOS.map(([k, nome]) => {
          const off = turno === 2 && k !== "presidente";
          return html`<button type="button" aria-pressed=${cargo === k} disabled=${off} title=${off ? "No 2º turno só há votação para presidente e, em alguns estados, governador" : null} onClick=${() => setCargo(k)}>${nome}</button>`;
        })}
        <a class="aba" href="/analise/">Análise</a>
      </div>
      <div class="acoes">
        <button type="button" class="bt busca" onClick=${onBusca} aria-keyshortcuts="Meta+K Control+K">${Ic.busca}<span>Buscar</span><kbd>⌘K</kbd></button>
        <span class=${"status " + status.cls} title=${status.longo || null}><i class="dot" aria-hidden="true"></i><span class=${status.curto ? "st-l" : ""}>${status.txt}</span>${status.curto && html`<span class="st-c" aria-hidden="true">${status.curto}</span>`}</span>
        <button type="button" class="bt" onClick=${onExterior}>${Ic.globo}<span>Exterior</span></button>
        <button type="button" class="bt ic" onClick=${onCheia} aria-label=${cheia ? "Sair da tela cheia" : "Tela cheia"} title=${cheia ? "Sair da tela cheia" : "Tela cheia"}>${Ic.cheia}</button>
      </div>
    </header>`;
}

// ---------------- barra de modos + legenda
function Modos({ modo, setModo, legenda, travado, semApurado, turno }) {
  return html`
    <div class="modos">
      <div class="seg" role="group" aria-label="Modo do mapa">
        ${MODOS.map(([k, nome]) => {
          const off = (k === "apurado" && semApurado) || (k === "divergencia" && turno === 2);
          const dica = k === "apurado" && semApurado ? "O % apurado por município ainda não veio nesta leitura"
            : k === "divergencia" ? (turno === 2 ? "Divergência compara os cargos do 1º turno" : "Municípios onde presidente e o cargo escolhido foram para lados diferentes") : null;
          return html`<button type="button" aria-pressed=${modo === k} disabled=${off} title=${dica} onClick=${() => setModo(k)}>${nome}</button>`;
        })}
      </div>
      ${legenda && html`<p class="legenda">${legenda}</p>`}
      ${travado && html`<p class="legenda nota">${travado}</p>`}
    </div>`;
}

// ---------------- linha do tempo
function LinhaDoTempo({ serie, idx, setIdx, ativa, motivo, turno, vivo }) {
  const n = serie?.length || 0;
  const atual = n ? serie[idx == null ? n - 1 : idx] : null;
  const final = idx == null || idx === n - 1;
  return html`
    <div class="linha" role="group" aria-label="Linha do tempo da apuração">
      ${ativa && n > 1 ? html`
        <span class="hora mono">${atual.d ? html`<small>${atual.d}</small>` : null}${atual.ht}</span>
        <div class="trilho">
          <input type="range" min="0" max=${n - 1} step="1" value=${idx == null ? n - 1 : idx}
            aria-label="Momento da apuração" aria-valuetext=${`${atual.d ? atual.d + " " : ""}${atual.ht}, ${pct(atual.pst, 1)}% das seções`}
            onInput=${(e) => { const v = +e.currentTarget.value; setIdx(v === n - 1 ? null : v); }} />
          <div class="marcas" aria-hidden="true">${serie.map((s, i) => html`<span style=${{ left: (i / (n - 1)) * 100 + "%" }} class=${i === (idx ?? n - 1) ? "on" : ""} title=${`${s.d ? s.d + " " : ""}${s.ht} · ${pct(s.pst, 1)}%`}>${pct(s.pst, 0)}%</span>`)}</div>
        </div>
        <span class="pst mono">${pct(atual.pst, 1)}%</span>` : html`<span class="linha-off">${motivo}</span>`}
      <${PessoasAgora} />
      <span class=${"aovivo " + (turno === 2 && vivo === "ok" && final ? "on" : "")}><i class="dot" aria-hidden="true"></i>${turno === 2 ? (!final ? "Revendo a noite" : vivo === "ok" ? "Ao vivo" : vivo === "parado" ? "Aguardando nova leitura do TSE" : "Aguardando") : final ? "Resultado final" : "Revendo a noite"}</span>
    </div>`;
}

// ---------------- dica (hover/toque)
function Dica({ conteudo }) {
  const [d, setD] = useState(dicaAtual);
  const ref = useRef();
  useEffect(() => { dicaSubs.add(setD); return () => dicaSubs.delete(setD); }, []);
  useEffect(() => {
    const el = ref.current; if (!el || !d) return;
    const w = el.offsetWidth, h = el.offsetHeight, vw = innerWidth, vh = innerHeight;
    let x = d.x + 16, y = d.y + 16;
    if (x + w > vw - 8) x = d.x - w - 16;
    if (y + h > vh - 8) y = d.y - h - 16;
    el.style.transform = `translate(${Math.max(8, x)}px,${Math.max(8, y)}px)`;
  });
  if (!d || (d.i < 0 && !d.cod) || (d.i == null && !d.cod)) return null;
  const c = conteudo(d);
  if (!c) return null;
  return html`<div class=${"dica" + (d.fixa ? " fixa" : "")} ref=${ref} role=${d.fixa ? "dialog" : "tooltip"} aria-label=${d.fixa ? "Detalhes do município" : null}>
    ${d.fixa && html`<button type="button" class="fechar" aria-label="Fechar" onClick=${() => d.fechar?.()}>${Ic.x}</button>`}
    ${c}</div>`;
}

// ---------------- busca (⌘K)
function Busca({ aberto, fechar, meta, geo, onEscolha }) {
  const ref = useRef(), inp = useRef();
  const [q, setQ] = useState(""); const [sel, setSel] = useState(0);
  useEffect(() => { const d = ref.current; if (!d) return; if (aberto && !d.open) { d.showModal(); setQ(""); setSel(0); setTimeout(() => inp.current?.focus(), 0); } else if (!aberto && d.open) d.close(); }, [aberto]);
  const indice = useMemo(() => {
    if (!meta) return [];
    const out = UFS.map((u) => ({ tipo: "uf", uf: u, txt: UF_NOME[u], sub: "Estado", k: semAcento(UF_NOME[u] + " " + u) }));
    for (const [cod, [nome, uf]] of Object.entries(meta.mun || {})) out.push({ tipo: "mun", cod, uf, txt: nome, sub: UF_NOME[uf], k: semAcento(nome) });
    (meta.cand?.presidente || []).forEach((c) => out.push({ tipo: "cand", cargo: "presidente", txt: c.nome, sub: `Presidente · ${c.sg}`, k: semAcento(c.nome) }));
    for (const cg of ["governador", "senador"]) for (const [uf, l] of Object.entries(meta.cand?.[cg] || {})) l.forEach((c) => out.push({ tipo: "cand", cargo: cg, uf, txt: c.nome, sub: `${CARGO_NOME[cg]} · ${uf} · ${c.sg}`, k: semAcento(c.nome) }));
    return out;
  }, [meta]);
  const res = useMemo(() => {
    const s = semAcento(q.trim()); if (s.length < 2) return [];
    const ini = [], meio = [];
    for (const it of indice) { const p = it.k.indexOf(s); if (p === 0) ini.push(it); else if (p > 0) meio.push(it); if (ini.length > 12) break; }
    return [...ini, ...meio].slice(0, 10);
  }, [q, indice]);
  const escolher = (it) => { fechar(); onEscolha(it); };
  return html`<dialog class="modal busca-dlg" ref=${ref} onClose=${fechar} aria-label="Buscar município, estado ou candidato">
    <div class="busca-in">${Ic.busca}<input ref=${inp} type="search" data-clarity-mask="true" placeholder="Município, estado ou candidato" value=${q}
      aria-label="Buscar" aria-controls="busca-res" aria-activedescendant=${res[sel] ? "br-" + sel : null}
      onInput=${(e) => { setQ(e.currentTarget.value); setSel(0); }}
      onKeyDown=${(e) => {
        if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(res.length - 1, s + 1)); }
        else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(0, s - 1)); }
        else if (e.key === "Enter" && res[sel]) { e.preventDefault(); escolher(res[sel]); }
      }} />
      <button type="button" class="bt ic" aria-label="Fechar busca" onClick=${fechar}>${Ic.x}</button></div>
    <ul id="busca-res" role="listbox" aria-label="Resultados">
      ${res.map((it, i) => html`<li id=${"br-" + i} role="option" aria-selected=${i === sel}><button type="button" tabindex="-1" onClick=${() => escolher(it)} onMouseMove=${(e) => { if (e.movementX || e.movementY) setSel(i); }}><b>${it.txt}</b><small>${it.sub}</small></button></li>`)}
      ${q.trim().length >= 2 && !res.length && html`<li class="nada">Nada encontrado para “${q}”.</li>`}
      ${q.trim().length < 2 && html`<li class="nada">Digite ao menos 2 letras. Ex.: Curitiba, Bahia, Pernambuco.</li>`}
    </ul></dialog>`;
}

// ---------------- Exterior
function Exterior({ aberto, fechar, meta, res, lista, turno }) {
  const ref = useRef();
  useEffect(() => { const d = ref.current; if (!d) return; if (aberto && !d.open) d.showModal(); else if (!aberto && d.open) d.close(); }, [aberto]);
  const { itens, semVoto } = useMemo(() => exteriorCidades(meta, res, lista, titulo), [meta, res, lista]);
  const zz0 = res?.uf?.ZZ && linha("presidente", res.uf.ZZ, lista), zz = zz0?.lider && zz0.segundo ? zz0 : null;
  return html`<dialog class="modal ext-dlg" ref=${ref} onClose=${fechar} aria-labelledby="ext-t">
    <div class="cab"><h2 id="ext-t">Exterior · Presidente</h2><button type="button" class="bt ic" aria-label="Fechar" onClick=${fechar}>${Ic.x}</button></div>
    ${zz ? html`<p class="ext-tot"><${Sw} sg=${zz.lider.sg} /><${Nome} c=${zz.lider} /> ${pct(zz.p1 * 100, 1)}% × <${Nome} c=${zz.segundo} /> ${pct(zz.segundo.p * 100, 1)}% · ${int(zz.validos)} votos válidos em ${itens.length} cidades</p>` : html`<p class="vazio-txt">Sem dados do exterior para este turno ainda.</p>`}
    <div class="ext-lista"><table><thead><tr><th scope="col">Cidade</th><th scope="col">1º colocado</th><th class="n" scope="col">%</th><th class="n" scope="col">Válidos</th></tr></thead>
    <tbody>${itens.map(({ nome, r }) => html`<tr><td>${nome}</td><td><${Sw} sg=${r.lider.sg} />${comSigla(r.lider)}</td><td class="n">${pct(r.p1 * 100, 1)}</td><td class="n">${int(r.validos)}</td></tr>`)}
    ${semVoto > 0 && html`<tr class="sem-voto"><td colspan="4">+${int(semVoto)} ${semVoto === 1 ? "cidade" : "cidades"} ${turno === 2 ? "sem votos apurados ainda" : "sem voto válido"}</td></tr>`}</tbody></table></div>
  </dialog>`;
}

// ---------------- app
function App() {
  const [turno, setTurno] = useState(1);
  // /ao-vivo/?cargo=depfed abre direto no cargo (links da página /analise/)
  const [cargo, setCargoS] = useState(() => { const c = new URLSearchParams(location.search).get("cargo"); return CARGO_NOME[c] ? c : "presidente"; });
  // ?modo=divergencia (link da /analise/) abre direto no modo
  const [modo, setModoS] = useState(() => { const m = new URLSearchParams(location.search).get("modo"); return MODOS.some(([k]) => k === m) && m !== "estados" ? m : BAIXO ? "estados" : "municipios"; });
  const [idx, setIdxS] = useState(null);
  const [ufSel, setUfSel] = useState(null);
  const [meta, setMeta] = useState(null);
  const [res, setRes] = useState({});
  const [serie, setSerie] = useState([]);
  const [feed, setFeed] = useState([]);
  const [geo, setGeo] = useState(null);
  const [erro, setErro] = useState(null);
  const [tema, setTema] = useState(0);
  const [vivo, setVivo] = useState({ status: "inicial", dados: null });
  const [situacao, setSituacao] = useState(null); // /hud/status.json: eleito/2º turno oficiais
  const [busca, setBusca] = useState(false);
  const [ext, setExt] = useState(false);
  const [cheia, setCheia] = useState(false);
  const [diverg, setDiverg] = useState(null); // /analise/dados/divergencias.json, só quando o modo Divergência é escolhido
  const [destaques, setDestaques] = useState(null);
  const [zoom, setZoom] = useState(1);
  const mapaEl = useRef(), mapa = useRef(), vivoCtl = useRef(), minutoCtl = useRef(null), st = useRef({});
  if (!minutoCtl.current) minutoCtl.current = criarMinuto();

  // dados do 1º turno + malha
  useEffect(() => {
    Promise.all([t1("meta"), t1("presidente")]).then(([m, p]) => { setMeta(m); setRes((r) => ({ ...r, presidente: p })); })
      .catch((e) => setErro(e));
    t1("serie").then(setSerie).catch(() => setSerie([]));
    fetch("/hud/status.json").then((r) => (r.ok ? r.json() : null)).then(setSituacao).catch(() => setSituacao(null));
    t1("feed").then(setFeed).catch(() => setFeed([]));
    analise("destaques").then((d) => setDestaques(Array.isArray(d) ? d : null)).catch(() => setDestaques(null));
    if (modo === "divergencia") analise("divergencias").then(setDiverg).catch(() => setDiverg({ erro: true }));
    if (BAIXO) fetch("/hud/ufs.json").then((r) => { if (!r.ok) throw new Error("ufs.json " + r.status); return r.json(); })
      .then((m) => setGeo(decodificarUFs(m))).catch(() => pedirMalha());
    else pedirMalha();
    const mq = matchMedia("(prefers-color-scheme: light)");
    const f = () => { limparCache(); setTema((x) => x + 1); };
    mq.addEventListener("change", f);
    new MutationObserver(f).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const fs = () => setCheia(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", fs);
    vivoCtl.current = criarVivo(setVivo);
    // abre direto no 2º turno quando o agora.json já existe
    vivoCtl.current.sondar().then((ok) => { if (ok && !st.current.turnoEscolhido) setTurnoX(2, true); });
    const tecla = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setBusca(true); }
      else if (e.key === "/" && !/INPUT|TEXTAREA/.test(document.activeElement?.tagName)) { e.preventDefault(); setBusca(true); }
      else if (e.key === "Escape" && dicaAtual) setDica(null);
    };
    addEventListener("keydown", tecla);
    return () => removeEventListener("keydown", tecla);
  }, []);

  useEffect(() => {
    if (turno !== 1 || cargo === "presidente" || res[cargo]) return; // presidente vem junto com o meta
    t1(cargo).then((d) => setRes((r) => ({ ...r, [cargo]: d }))).catch((e) => setErro(e));
  }, [cargo, turno]);

  // 2º turno: polling só com a aba ativa
  useEffect(() => {
    const v = vivoCtl.current; if (!v) return;
    if (turno === 2) v.ativar(); else v.desativar();
  }, [turno]);

  function pedirMalha() {
    if (st.current.malhaPedida) return;
    st.current.malhaPedida = true;
    malha().then((t) => setGeo(decodificar(t))).catch((e) => { st.current.malhaPedida = false; setErro(e); });
  }

  const setTurnoX = (t, auto) => { if (!auto) st.current.turnoEscolhido = true; setTurno(t); setIdxS(null); setUfSel(null); setDica(null); if (t === 2) { setCargoS("presidente"); if (modo !== "municipios" && modo !== "estados") setModoS("municipios"); } };
  const setCargo = (c) => { setCargoS(c); setDica(null); if (c !== "presidente") setIdxS(null); };
  const setModo = (m) => {
    if (m !== "estados") pedirMalha();
    if (m === "divergencia" && !diverg) analise("divergencias").then(setDiverg).catch(() => setDiverg({ erro: true }));
    setModoS(m); if ((m === "municipios" || m === "divergencia") && idx != null) setIdxS(null);
  };
  const setIdx = (i) => {
    setIdxS(i);
    if (turno === 2) return; // no 2º turno a linha do tempo troca o minuto, o mapa segue por município
    if (i == null) { if (modo === "estados" && st.current.modoAntes) setModoS(st.current.modoAntes); st.current.modoAntes = null; }
    else if (modo === "municipios" || modo === "vantagem" || modo === "divergencia") { st.current.modoAntes = modo; setModoS("estados"); }
  };

  // 2º turno: feed, série (índice) e o minuto escolhido na linha do tempo
  const [feed2, setFeed2] = useState(null), [serie2b, setSerie2b] = useState(null), [minuto, setMinuto] = useState(null);
  // relê feed e série quando a leitura muda; o idg sozinho não basta (UF pendente que fecha depois mantém o idg)
  const chaveVivo = vivo.dados ? `${vivo.dados.idg}|${vivo.dados.pst}|${(vivo.dados.pend || []).join()}` : "";
  useEffect(() => {
    if (turno !== 2 || !chaveVivo) return;
    vivoExtra("feed.json").then((f) => f && setFeed2(f));
    vivoExtra("serie/index.json").then((x) => Array.isArray(x) && setSerie2b(x));
  }, [turno, chaveVivo]);
  const serie2 = useMemo(() => serieTurno2(serie2b, vivo.dados?.cand), [serie2b, vivo.dados?.cand]);
  // minuto escolhido: cancela o pedido anterior, ignora resposta velha; se falhar, fica no minuto com aviso
  const tSel = turno === 2 && idx != null ? serie2[idx]?.ht ?? null : null;
  const [tentarMinuto, setTentarMinuto] = useState(0);
  useEffect(() => {
    if (!tSel) { minutoCtl.current.cancelar(); setMinuto(null); return; }
    minutoCtl.current.ler(tSel).then((r) => { if (r) setMinuto(r); });
  }, [tSel, tentarMinuto]);
  const f2 = fonteTurno2(tSel ? idx : null, tSel, minuto, vivo.dados);

  // fonte de dados do recorte atual
  const fonte = turno === 2 ? (cargo === "presidente" ? f2.fonte : null) : res[cargo];
  // leitura nova sem pm (% por município): Apurado não tem o que mostrar, volta para Municípios
  useEffect(() => { const m = modoValido(modo, turno, fonte); if (m !== modo) setModoS(m); }, [modo, turno, fonte]);
  // % apurado por UF / município (2º turno: pu/pm do agregador; 1º turno final: 100%)
  const pstUF = (uf) => (turno === 2 ? (fonte?.pu?.[uf] ?? fonte?.pst ?? 0) : 100);
  const pstMun = (cod) => (turno === 2 ? (fonte?.pm?.[cod] ?? fonte?.pst ?? 0) : 100);
  const listaPres = useMemo(() => {
    if (turno === 2 && vivo.dados) {
      if (Array.isArray(vivo.dados.cand)) return vivo.dados.cand; // contrato: votos seguem agora.cand
      const n = vivo.dados.br?.[5]?.length || 2;
      return (meta?.cand?.presidente || []).slice(0, n);
    }
    return meta?.cand?.presidente || [];
  }, [turno, vivo.dados, meta]);
  const lista = useCallback((uf) => (cargo === "presidente" ? listaPres : meta?.cand?.[cargo]?.[uf]), [cargo, listaPres, meta]);
  const ponto = turno === 1 && cargo === "presidente" && idx != null ? serie[idx] : null;
  const pontoUF = useMemo(() => {
    if (!ponto) return null;
    if (ponto.uf) return ponto;
    // pontos sem detalhe por UF: usa a leitura mais próxima que tem
    let best = null, d = Infinity;
    serie.forEach((s, i) => { if (s.uf && Math.abs(i - idx) < d) { d = Math.abs(i - idx); best = s; } });
    return best ? { ...ponto, uf: best.uf, ufDe: best.ht } : ponto;
  }, [ponto, serie, idx]);

  const resultadoUF = useCallback((uf) => {
    if (pontoUF?.uf) return linhaSerie(pontoUF.uf[uf], listaPres);
    return fonte ? linha(cargo, fonte.uf?.[uf], lista(uf)) : null;
  }, [pontoUF, fonte, cargo, lista, listaPres]);

  // cores do mapa
  const cores = useMemo(() => {
    if (!geo) return null;
    const bg = token("--bg");
    if (!fonte) { const n = misturar(token("--neutral"), bg, 0.45); return geo.muns.map(() => n); }
    if (modo === "estados" || pontoUF || geo.soUF) {
      const porUF = {};
      for (const uf of Object.keys(geo.ufs)) {
        const r = resultadoUF(uf);
        porUF[uf] = r ? corPara(modo === "apurado" ? "apurado" : modo === "vantagem" ? "vantagem" : "municipios", r, cargo, (r.pst ?? pstUF(uf)) / 100) : null;
      }
      return geo.muns.map((m) => porUF[m.uf]);
    }
    if (modo === "divergencia") {
      if (!diverg?.mu) { const n = misturar(token("--neutral"), bg, 0.3); return geo.muns.map(() => n); }
      const igual = misturar(token("--neutral"), bg, 0.35);
      const forte = Object.fromEntries(Object.entries(LADO_TOKEN).map(([l, t]) => [l, misturar(token(t), bg, 0.9)]));
      return geo.muns.map((m) => { const d = divergencia(diverg.mu[m.cod], cargo); return d ? (d.diverge ? forte[d.leg] : igual) : null; });
    }
    return geo.muns.map((m) => {
      const r = linha(cargo, fonte.mu?.[m.cod], lista(m.uf));
      return r ? corPara(modo, r, cargo, pstMun(m.cod) / 100) : null;
    });
  }, [geo, fonte, cargo, modo, pontoUF, tema, turno, resultadoUF, lista, vivo.dados, diverg]);

  const rotulos = useMemo(() => {
    if (!geo) return [];
    return Object.keys(geo.ufs).map((uf) => {
      const r = fonte ? resultadoUF(uf) : null;
      if (!r || !r.lider) return { uf, cor: "var(--neutral)", txt: "", aria: `${UF_NOME[uf]}: sem dados` };
      const txt = ehDep(cargo) ? curta(r.sg) : modo === "apurado" ? `${pct(r.pst ?? pstUF(uf), 0)}%` : `${pct(r.p1 * 100, 0)}%`;
      return { uf, cor: cor(r.lider.sg), txt, aria: `${UF_NOME[uf]}: ${ehDep(cargo) ? r.sg + " mais votado" : `${comSigla(r.lider)} ${pct(r.p1 * 100, 1)}%`}. Aproximar.` };
    });
  }, [geo, fonte, resultadoUF, cargo, modo, turno, vivo.dados]);

  // mapa (imperativo)
  st.current = { ...st.current, ufSel, cargo };
  useEffect(() => {
    if (!geo || !mapaEl.current) return;
    if (mapa.current) {
      mapa.current.setGeo(geo);
      const p = st.current.pendente; st.current.pendente = null;
      if (p && !geo.soUF) setTimeout(() => onEscolha(p), 0);
      return;
    }
    mapa.current = new Mapa(mapaEl.current, geo, {
      onHover: (i, x, y) => { if (dicaAtual?.fixa || st.current.buscaEm > performance.now() - 900) return; setDica(i >= 0 ? { i, x, y } : null); },
      // (com a malha leve, i é a UF inteira; a dica mostra o resultado do estado)
      onClick: (i, x, y) => {
        mapa.current.setSelecao(i);
        setDica(i >= 0 ? { i, x, y, fixa: true, fechar: () => { mapa.current.setSelecao(-1); setDica(null); } } : null);
      },
      onUF: (uf) => escolherUF(uf),
      onZoom: (z) => { setZoom(z); if (z > 1.5) pedirMalha(); },
    });
    if (new URLSearchParams(location.search).has("diag")) window.__hudMapa = mapa.current; // só para medição/QA (?diag)
    const ins = () => mapa.current?.setInsets(medirInsets());
    ins(); addEventListener("resize", ins);
  }, [geo]);
  useEffect(() => { mapa.current?.setCores(cores); }, [cores]);
  useEffect(() => { mapa.current?.setRotulos(rotulos); }, [rotulos]);
  useEffect(() => { mapa.current?.setUF(ufSel); }, [ufSel]);
  useEffect(() => { const f = () => mapa.current?.setInsets(medirInsets()); requestAnimationFrame(f); }, [geo, turno]);

  function medirInsets() {
    const c = mapaEl.current; if (!c) return { t: 0, r: 0, b: 0, l: 0 };
    const box = c.getBoundingClientRect();
    const q = (s) => document.querySelector(s)?.getBoundingClientRect();
    const m = q(".modos");
    const t = m ? Math.max(0, m.bottom - box.top + 8) : 0;
    if (!DESKTOP()) return { t, r: 8, b: 8, l: 8 };
    const e = q(".painel.esq"), d = q(".painel.dir"), l = q(".linha");
    return { l: e ? e.right - box.left + 8 : 0, r: d ? box.right - d.left + 8 : 0, t, b: l ? box.bottom - l.top + 8 : 0 };
  }

  function escolherUF(uf) {
    if (st.current.ufSel === uf) { setUfSel(null); mapa.current?.ajustar(true); return; }
    setUfSel(uf); setDica(null); mapa.current?.setSelecao(-1); mapa.current?.enquadrarUF(uf);
  }
  const voltar = () => { setUfSel(null); mapa.current?.ajustar(true); };

  function onEscolha(it) {
    if (it.tipo === "uf") return escolherUF(it.uf);
    if (it.tipo === "cand") { setCargo(it.cargo); if (it.uf) { setUfSel(it.uf); mapa.current?.enquadrarUF(it.uf); } return; }
    if (!geo || geo.soUF) { st.current.pendente = it; pedirMalha(); return; }
    const i = geo.indice.get(it.cod);
    if (i == null) { // município sem geometria na malha do IBGE (ex.: 5101837, MT): só a dica, sem mapa
      const r = mapaEl.current.getBoundingClientRect();
      setDica({ cod: it.cod, x: r.left + r.width / 2 - 140, y: r.top + 80, fixa: true, fechar: () => setDica(null) });
      return;
    }
    setUfSel(null);
    st.current.buscaEm = performance.now(); // o mapa anda sob o mouse parado: não deixa o hover roubar a dica
    mapa.current.setSelecao(i); mapa.current.enquadrarMun(i);
    setTimeout(() => {
      const m = geo.muns[i], M = mapa.current, r = M.cv.getBoundingClientRect();
      setDica({ i, x: r.left + m.cx * M.k + M.ox, y: r.top + m.cy * M.k + M.oy, fixa: true, fechar: () => { M.setSelecao(-1); setDica(null); } });
    }, matchMedia("(prefers-reduced-motion: reduce)").matches ? 30 : 450);
  }

  // conteúdo da dica (no modo Divergência, com a linha "presidente × cargo" no fim)
  const conteudoDica = (d) => {
    const c = conteudoBase(d);
    const cod = d.cod || (d.i >= 0 ? geo?.muns[d.i]?.cod : null);
    const dv = c && modo === "divergencia" && turno === 1 && !geo?.soUF ? divergencia(diverg?.mu?.[cod], cargo) : null;
    return dv ? html`${c}<p class="dk-nota dk-dv">Presidente: ${LADO_NOME[dv.pres]} · ${CARGO_NOME[cargoDivergencia(cargo)]}: ${LADO_NOME[dv.leg]}${dv.diverge ? " · lados diferentes" : " · mesmo lado"}</p>` : c;
  };
  const conteudoBase = (d) => {
    const m = d.i >= 0 ? geo?.muns[d.i] : null;
    const cod = d.cod || m?.cod; if (!cod) return null;
    const uf = meta?.mun?.[cod]?.[1] || m?.uf;
    if (geo?.soUF && m) { // malha leve: a "área" é o estado
      const r = resultadoUF(uf);
      const cab = html`<p class="dk-nome"><b>${UF_NOME[uf]}</b> <span>${uf}</span></p>`;
      if (!r) return html`${cab}<p class="dk-nota">${turno === 2 ? "Aguardando o TSE · 25/10 a partir das 17h" : "Sem dados."}</p>`;
      if (r.vazio) return html`${cab}<p class="dk-nota">Nenhuma seção apurada ainda</p>`;
      return html`${cab}<p class="dk-nota">${CARGO_NOME[cargo]} · estado</p>${listaDica(r)}<p class="dk-nota">Aproxime para ver os municípios</p>`;
    }
    const nome = meta?.mun?.[cod]?.[0] || cod;
    const cab = html`<p class="dk-nome"><b>${nome}</b> <span>${uf}</span></p>${!m && html`<p class="dk-nota">Sem contorno na malha do IBGE: não aparece no mapa</p>`}`;
    if (!fonte) return html`${cab}<p class="dk-nota">${turno === 2 ? "Aguardando o TSE · 25/10 a partir das 17h" : "Carregando…"}</p>`;
    if (pontoUF?.uf) {
      const r = linhaSerie(pontoUF.uf[uf], listaPres);
      const p = pontoUF.ufDe ? serie.find((x) => x.ht === pontoUF.ufDe) || pontoUF : pontoUF;
      return html`${cab}<p class="dk-nota">${UF_NOME[uf]} em ${p.d ? p.d + " " : ""}${p.ht}${r ? ` · ${pct(r.pst, 1)}% apurado` : ""}</p>
        ${r && html`<ul class="dk-l">${r.cands.map((c) => html`<li><${Sw} sg=${c.sg} /><span>${c.nome} <small>${c.sg}</small></span><b>${pct(c.p * 100, 1)}%</b></li>`)}</ul>`}`;
    }
    const r = linha(cargo, fonte.mu?.[cod], lista(uf));
    if (!r) return html`${cab}<p class="dk-nota">Sem dados deste município.</p>`;
    if (r.vazio) return html`${cab}<p class="dk-nota">Nenhuma seção apurada ainda${turno === 2 ? ` · ${pct(pstMun(cod), 1)}% das seções` : ""}</p>`;
    if (r.dep) return html`${cab}<p class="dk-nota">${CARGO_NOME[cargo]} · partido mais votado</p>
      <p class="dk-part"><${Sw} sg=${r.sg} /><b>${r.sg}</b> ${pct(r.partidoP * 100, 1)}% <small>${int(r.partidoV)} votos nominais</small></p>
      <ul class="dk-l">${r.cands.map((c) => html`<li><${Sw} sg=${c.sg} /><span>${c.nome} <small>${c.sg}</small></span><b>${int(c.v)}</b></li>`)}</ul>
      <p class="dk-nota">${int(r.validos)} votos válidos</p>`;
    return html`${cab}<p class="dk-nota">${CARGO_NOME[cargo]}${cargo !== "presidente" ? " · " + UF_NOME[uf] : ""}</p>
      ${listaDica(r)}
      <p class="dk-nota">Comparecimento ${pct(r.pc * 100, 1)}% · ${int(r.validos)} válidos</p>`;
  };
  /** top 3 por votos (sub judice entra com % e etiqueta, regra do TSE) */
  const listaDica = (r) => html`<ul class="dk-l">${r.cands.slice(0, 3).map((c) => html`<li><${Sw} sg=${c.sg} /><span>${c.nome} <small>${c.sg}${c.sj ? html` · <span class="tag-sj">sub judice</span>` : null}</small></span><b>${pct(c.p * 100, 1)}%</b><small class="v">${int(c.v)}</small></li>`)}</ul>`;

  // textos
  const status = useMemo(() => {
    if (turno === 2) return situacaoVivo(vivo);
    if (ponto) return { cls: "", txt: `Revendo ${ponto.d ? ponto.d + " " : ""}${ponto.ht} · ${pct(ponto.pst, 1)}%` };
    return { cls: "", txt: meta ? `${meta.dg?.slice(0, 5)} ${meta.ht?.slice(0, 5).replace(":", "h")} · 100% apurado` : "Carregando…", curto: meta ? "100% apurado" : null };
  }, [turno, vivo, ponto, meta]);

  const legenda = useMemo(() => {
    if (!geo || !fonte) return null;
    if (modo === "apurado") return "Mais escuro = menos seções apuradas";
    if (modo === "divergencia" && !(modo === "estados" || pontoUF || geo.soUF)) {
      if (!diverg) return "Carregando a divergência…";
      if (!diverg.mu) return "Divergência indisponível: os dados da Análise ainda não foram publicados";
      const c = cargoDivergencia(cargo), { n, t, empates } = contaDivergencia(diverg.mu, cargo);
      return html`<span><b>${int(n)}</b> de ${int(t)} municípios com lados diferentes: presidente × ${CARGO_NOME[c]}${empates ? ` (${int(empates)} ${empates === 1 ? "empate" : "empates"} para presidente ${empates === 1 ? "fica" : "ficam"} de fora)` : ""}</span>
        ${["L", "F", "C"].map((l) => html`<span class="lg"><i class="sw" style=${{ "--c": `var(${LADO_TOKEN[l]})` }} aria-hidden="true"></i>${CARGO_NOME[c]} no ${LADO_NOME[l]}</span>`)}
        <span class="und">apagado = mesmo lado · <a href="/analise/#divergencias">entenda</a></span>`;
    }
    const cont = {};
    if (modo === "estados" || pontoUF || geo.soUF) { for (const uf of UFS) { const r = resultadoUF(uf); if (r?.lider) cont[r.lider.sg] = (cont[r.lider.sg] || 0) + 1; } }
    else geo.muns.forEach((m) => { const r = linha(cargo, fonte.mu?.[m.cod], lista(m.uf)); if (r?.lider) cont[r.lider.sg] = (cont[r.lider.sg] || 0) + 1; });
    const rk = Object.entries(cont).sort((a, b) => b[1] - a[1]).slice(0, 4);
    if (!rk.length) return null; // ninguém lidera em lugar nenhum (nenhum voto apurado): sem legenda vazia
    const und = modo === "estados" || pontoUF || geo.soUF ? "estados" : "municípios";
    return html`${rk.map(([sg, n]) => html`<span class="lg"><${Sw} sg=${sg} /><b>${sg}</b> ${int(n)}</span>`)}<span class="und">${und}${modo === "vantagem" ? " · cor forte = vantagem maior" : ""}</span>`;
  }, [geo, fonte, modo, cargo, pontoUF, resultadoUF, lista, diverg]);

  const resumo = useMemo(() => (f2.erro && turno === 2
    ? `Não deu para carregar a leitura das ${tSel}.`
    : resumoLeitor({ turno, temVivo: !!vivo.dados, fonte, meta, cargo, ponto, pontoUF, ufSel, lista: listaPres })),
  [turno, vivo.dados, fonte, meta, cargo, ponto, pontoUF, listaPres, ufSel, f2.erro, tSel]);

  // ---------- painel esquerdo
  let esq;
  if (erro && !meta) esq = html`<div class="vazio"><p class="kicker">Erro</p><h1 class="manchete pequena">Não deu para carregar os resultados</h1><p class="vazio-txt">Recarregue a página em instantes. Se persistir, o <a href="/">resultado final</a> continua disponível.</p></div>`;
  else if (turno === 2 && !vivo.dados) esq = html`<div class="vazio">
      <p class="kicker">Presidente · 2º turno</p>
      <h1 class="manchete"><${Nome} c=${{ nome: "Flávio Bolsonaro", sg: "PL" }} /> × <${Nome} c=${{ nome: "Lula", sg: "PT" }} /></h1>
      <p class="aguarda"><i class="dot" aria-hidden="true"></i>${vivo.status === "erro" ? "TSE sem resposta" : "Aguardando o TSE"} · 25/10 a partir das 17h</p>
      <p class="vazio-txt">O mapa por município começa a se colorir quando o TSE publicar as primeiras seções apuradas. Esta página atualiza sozinha.</p>
      <button type="button" class="bt" onClick=${() => setTurnoX(1)}>Ver o 1º turno</button></div>`;
  else if (turno === 2 && cargo === "presidente" && f2.erro) esq = html`<div class="vazio">
      <p class="kicker">Presidente · 2º turno · leitura das ${tSel}</p>
      <h1 class="manchete pequena">Não deu para carregar a leitura das ${tSel}</h1>
      <p class="vazio-txt">A linha do tempo continua neste minuto. O resultado ao vivo não foi trocado por ele.</p>
      <p><button type="button" class="bt" onClick=${() => setTentarMinuto((x) => x + 1)}>Tentar de novo</button> <button type="button" class="link" onClick=${() => setIdx(null)}>Voltar ao ao vivo</button></p></div>`;
  else if (!meta || !fonte) esq = html`<p class="vazio-txt">${f2.carregando && tSel ? `Carregando a leitura das ${tSel}…` : "Carregando resultados…"}</p>`;
  else if (cargo === "presidente") {
    const r0 = ufSel ? linha("presidente", fonte.uf?.[ufSel], listaPres) : linha("presidente", fonte.br, listaPres);
    // linha do tempo: com UF escolhida, a leitura daquela UF (nunca o número nacional com o nome da UF)
    let r = r0, pontoP = null, semLeitura = false;
    if (ponto && ufSel) {
      const u = pontoUF?.uf?.[ufSel];
      if (u) { r = linhaSerie(u, listaPres); pontoP = { ...ponto, pst: u[0], ht: pontoUF.ufDe || ponto.ht }; } else semLeitura = true;
    } else if (ponto) { r = linhaSerie([ponto.pst, ponto.f, ponto.l], listaPres); pontoP = ponto; }
    else if (turno === 2) pontoP = null;
    esq = semLeitura ? html`<div class="cab"><p class="kicker">Presidente · ${UF_NOME[ufSel]}</p><button type="button" class="link" onClick=${voltar}>← Brasil</button></div>
      <h1 class="manchete pequena">Sem leitura desta UF neste momento</h1><p class="vazio-txt">O TSE não tinha publicado ${UF_NOME[ufSel]} às ${ponto.ht}. Arraste a linha do tempo para outra leitura.</p>` : html`<${Placar} cargo="presidente" r=${r} turno=${turno} pst=${turno === 2 ? (ufSel ? pstUF(ufSel) : fonte?.pst ?? 0) : 100} ponto=${pontoP}
      pend=${turno === 2 ? fonte?.pend : null} atualizado=${turno === 2 ? (idx == null ? status.longo : fonte?.t ? `leitura das ${fonte.t.replace(":", "h")}` : null) : null} eleito=${turno === 2 && !ufSel ? eleitoTurno2(fonte, listaPres) : null}
      kicker=${`Presidente · ${turno}º turno · ${ufSel ? UF_NOME[ufSel] : "Brasil"}`} selo=${turno === 1 ? "2º turno em 25/10" : null}
      of=${turno === 1 && !ufSel ? oficial(situacao, "presidente", null, listaPres) : null}
      onVoltar=${ufSel ? voltar : null} serie=${!ufSel ? (turno === 1 ? serie : serie2) : null} idx=${idx} />`;
  } else if (ehDep(cargo)) esq = html`<${ResumoDep} cargo=${cargo} res=${fonte} uf=${ufSel} onUF=${escolherUF} onVoltar=${voltar} geo=${geo} />`;
  else if (ufSel) esq = html`<${Placar} cargo=${cargo} r=${linha(cargo, fonte.uf?.[ufSel], lista(ufSel))} pst=${pstUF(ufSel)} of=${oficial(situacao, cargo, ufSel, lista(ufSel))} kicker=${`${CARGO_NOME[cargo]} · ${UF_NOME[ufSel]}`} onVoltar=${voltar} />`;
  else esq = html`<${ResumoUFs} cargo=${cargo} res=${fonte} meta=${meta} onUF=${escolherUF} status=${situacao} pst=${turno === 1 ? 100 : fonte?.pst} />`;

  const linhaAtiva = cargo === "presidente" && (turno === 1 ? serie.length > 1 : serie2.length > 1);
  const motivoLinha = turno === 2 ? "A linha do tempo do 2º turno começa com as primeiras leituras do TSE" : "Linha do tempo: só para presidente (o TSE não publica a noite dos outros cargos)";
  const travado = pontoUF && modo === "estados" ? `Por estado: o TSE não publica a noite por município${pontoUF.ufDe && pontoUF.ufDe !== pontoUF.ht ? ` · estados às ${pontoUF.ufDe}` : ""}` : null;

  // tabela alternativa (leitor de tela)
  const tabela = useMemo(() => {
    if (!fonte || !meta) return null;
    const linhas = UFS.map((uf) => ({ uf, r: resultadoUF(uf) })).filter((x) => x.r && (x.r.dep || x.r.lider));
    return html`<table class="sr-only"><caption>${CARGO_NOME[cargo]}, ${turno}º turno: resultado por estado${ponto ? ` às ${ponto.ht}` : ""}</caption>
      <thead><tr><th scope="col">Estado</th><th scope="col">${ehDep(cargo) ? "Partido mais votado" : "1º colocado"}</th><th scope="col">% dos válidos</th><th scope="col">${ehDep(cargo) ? "Candidato mais votado" : "2º colocado"}</th></tr></thead>
      <tbody>${linhas.map(({ uf, r }) => html`<tr><th scope="row">${UF_NOME[uf]}</th>
        <td>${r.dep ? r.sg : comSigla(r.lider)}</td><td>${pct(r.p1 * 100, 1)}%</td>
        <td>${r.dep ? (r.cands[0] ? comSigla(r.cands[0]) : "–") : r.segundo ? `${comSigla(r.segundo)} ${pct(r.segundo.p * 100, 1)}%` : "–"}</td></tr>`)}</tbody></table>`;
  }, [fonte, meta, cargo, turno, resultadoUF, ponto]);

  return html`
    <div class=${"hud" + (turno === 2 && !vivo.dados ? " t2-vazio" : "")}>
      <${Topo} turno=${turno} setTurno=${setTurnoX} cargo=${cargo} setCargo=${setCargo} status=${status}
        onBusca=${() => setBusca(true)} onExterior=${() => setExt(true)} cheia=${cheia}
        onCheia=${() => (document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen?.().catch(() => {}))} />
      <main id="conteudo" class="palco">
        <aside class="esq painel" aria-label="Resultado"><${Seguro}>${esq}<//></aside>
        <section class="centro" aria-label="Mapa">
          <${Modos} modo=${modo} setModo=${setModo} turno=${turno} semApurado=${turno === 2 && fonte && !fonte.pm} legenda=${legenda} travado=${travado} />
          <div class="mapa" ref=${mapaEl}>
            ${!geo && html`<p class="mapa-msg">${erro ? "Mapa indisponível no momento." : "Carregando o mapa dos 5.570 municípios…"}</p>`}
          </div>
          <div class="zoom" role="group" aria-label="Zoom do mapa">
            <button type="button" class="bt ic" aria-label="Aproximar" onClick=${() => mapa.current?.zoomCentro(1.6)}>${Ic.mais}</button>
            <button type="button" class="bt ic" aria-label="Afastar" onClick=${() => mapa.current?.zoomCentro(1 / 1.6)}>${Ic.menos}</button>
            ${zoom > 1.05 && html`<button type="button" class="bt ic" aria-label="Ver o Brasil inteiro" onClick=${() => { setUfSel(null); mapa.current?.ajustar(true); }}>${Ic.brasil}</button>`}
          </div>
          ${tabela}
        </section>
        <aside class="dir painel" aria-label="Regiões e atualizações">
          <section class="bloco"><div class="cab"><h2 class="kicker">Por região</h2><span class="sub">${cargo === "presidente" ? "quem lidera" : "partido na frente"}${ponto ? ` · aprox. ${ponto.d ? ponto.d + " " : ""}${ponto.ht}` : ""}</span></div>
            <${Seguro}><${PorRegiao} cargo=${cargo} res=${meta ? fonte : null} meta=${meta} lista=${listaPres} ponto=${pontoUF} geo=${geo} turno=${turno} msg=${f2.erro ? `Sem a leitura das ${tSel}.` : f2.carregando && tSel ? `Carregando a leitura das ${tSel}…` : null} /><//></section>
          ${destaques?.length > 0 && html`<section class="bloco analise-b"><div class="cab"><h2 class="kicker">Análise</h2><a class="sub" href="/analise/">ver tudo →</a></div>
            <ul class="dest">${destaques.slice(0, 3).map((c) => html`<li><a href=${"/analise/" + (c.ancora || "")}><b>${c.numero}</b><span>${textoComSigla(c.titulo, listaPres)}${c.est ? html` <span class="tag-est">estimativa</span>` : null}</span></a></li>`)}</ul></section>`}
          <section class="bloco feed-b"><div class="cab"><h2 class="kicker">Últimas atualizações</h2></div>
            ${turno === 2 ? (feed2?.length ? html`<${Feed} itens=${feed2} lista=${listaPres} onUF=${(uf) => { escolherUF(uf); }} />` : html`<p class="vazio-txt">O feed do 2º turno começa quando o TSE publicar as primeiras seções.</p>`) : html`<${Feed} itens=${feed} lista=${listaPres} onUF=${(uf) => { escolherUF(uf); }} />`}</section>
          <p class="fonte">Dados públicos do <a href="https://resultados.tse.jus.br/oficial/app/index.html" rel="noopener">TSE</a> e malha do IBGE. Não é site oficial da Justiça Eleitoral. <a href="/">Resultado final</a> · <a href="/apuracao/">Histórico</a> · <a href="/#metodo">Método</a> · <a href="https://vitorpereira.ia.br/privacidade">Privacidade</a> · <button type="button" class="link" onClick=${() => window.dispatchEvent(new CustomEvent("consent:reopen"))}>Cookies</button></p>
        </aside>
        <${LinhaDoTempo} serie=${turno === 1 ? serie : serie2} idx=${idx} setIdx=${setIdx} ativa=${linhaAtiva} motivo=${motivoLinha} turno=${turno} vivo=${status.aoVivo ? "ok" : vivo.status === "ok" ? "parado" : vivo.status} />
      </main>
      <p class="sr-only" aria-live="polite">${resumo}</p>
      <footer class="hud-pe"><span>Dados públicos do <a href="https://resultados.tse.jus.br/oficial/app/index.html" rel="noopener">TSE</a> e malha do <a href="https://www.ibge.gov.br/" rel="noopener">IBGE</a>. Não é um site oficial da Justiça Eleitoral.</span>
        <span><a href="/">Resultado final</a> · <a href="/apuracao/">Histórico</a> · <a href="/#metodo">Método</a> · <a href="https://vitorpereira.ia.br/privacidade">Privacidade</a> · <button type="button" class="link" onClick=${() => window.dispatchEvent(new CustomEvent("consent:reopen"))}>Cookies</button></span></footer>
      <${Dica} conteudo=${conteudoDica} />
      <${Busca} aberto=${busca} fechar=${() => setBusca(false)} meta=${meta} geo=${geo} onEscolha=${onEscolha} />
      <${Exterior} aberto=${ext} fechar=${() => setExt(false)} meta=${meta} res=${turno === 2 ? vivo.dados : res.presidente} lista=${listaPres} turno=${turno} />
    </div>`;
}

const raiz = document.getElementById("hud");
raiz.textContent = ""; // descarta o HTML do pré-render (o resumo para buscadores fica fora daqui)
render(html`<${App} />`, raiz);
