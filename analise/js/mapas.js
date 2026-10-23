// Mapa por município da Análise: reaproveita o mapa do HUD (/hud/mapa.js) e a malha do IBGE (/geo/municipios.topo.json).
// Carrega só quando o mapa chega perto da tela (a malha tem alguns MB).
import { html, useState, useEffect, useRef } from "/vendor/preact-htm.module.js";
import { Mapa } from "/hud/mapa.js";
import { decodificar } from "/hud/topo.js";
import { malha } from "/hud/dados.js";
import { token, misturar, limparCache } from "/hud/partidos.js";
import { LADO_TOKEN } from "./calc.js";
import { mostrarDica, esconderDica } from "./graficos.js";

let geoP = null;
const carregarGeo = () => (geoP ||= malha().then(decodificar).catch((e) => { geoP = null; throw e; }));

/** cor de canvas de um lado (t = 1 cor pura, 0 = fundo) */
export const corLado = (lado, t = 0.9) => misturar(token(LADO_TOKEN[lado] || "--outros"), token("--bg"), t);
export const corApagada = () => misturar(token("--neutral"), token("--bg"), 0.35);

/**
 * corDe(cod) → cor CSS ou null (sem dado); dica(cod) → conteúdo; chave muda quando as cores mudam.
 */
export function MapaMun({ corDe, dica, chave, uf, rotulo }) {
  const el = useRef(), mapa = useRef(null);
  const [geo, setGeo] = useState(null), [erro, setErro] = useState(false), [tema, setTema] = useState(0);
  const dicaR = useRef(dica); dicaR.current = dica; // a dica lê sempre a função mais nova sem recriar o mapa
  useEffect(() => {
    const alvo = el.current; if (!alvo) return;
    const io = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting)) { io.disconnect(); carregarGeo().then(setGeo).catch(() => setErro(true)); }
    }, { rootMargin: "400px" });
    io.observe(alvo);
    const mq = matchMedia("(prefers-color-scheme: light)");
    const f = () => { limparCache(); setTema((t) => t + 1); };
    mq.addEventListener("change", f);
    const mo = new MutationObserver(f); // botão de tema (data-theme no <html>)
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => { io.disconnect(); mq.removeEventListener("change", f); mo.disconnect(); };
  }, []);
  useEffect(() => {
    if (!geo || !el.current || mapa.current) return;
    const M = new Mapa(el.current, geo, {
      rolagemLivre: true,
      onHover: (i, x, y) => { if (i >= 0) mostrarDica(x, y, dicaR.current(geo.muns[i].cod)); else esconderDica(); },
      onClick: (i, x, y) => { M.setSelecao(i); if (i >= 0) mostrarDica(x, y, dicaR.current(geo.muns[i].cod)); else esconderDica(); },
    });
    M.cv.setAttribute("aria-label", rotulo + " Setas movem, + e − aproximam, 0 volta ao Brasil inteiro. A tabela abaixo traz os números.");
    mapa.current = M;
  }, [geo]);
  useEffect(() => {
    const M = mapa.current; if (!M || !geo) return;
    M.setCores(geo.muns.map((m) => corDe(m.cod)));
  }, [geo, chave, tema]);
  useEffect(() => {
    const M = mapa.current; if (!M) return;
    M.setUF(uf === "BR" ? null : uf);
    if (uf === "BR") M.ajustar(true); else M.enquadrarUF(uf);
  }, [uf, geo]);
  return html`<div class="mapa-box">
    <div class="mapa" ref=${el}>${!geo && html`<p class="mapa-msg">${erro ? "Mapa indisponível no momento." : "Carregando o mapa dos municípios…"}</p>`}</div>
    <div class="zoom" role="group" aria-label="Zoom do mapa">
      <button type="button" class="bt ic" aria-label="Aproximar" onClick=${() => mapa.current?.zoomCentro(1.6)}>+</button>
      <button type="button" class="bt ic" aria-label="Afastar" onClick=${() => mapa.current?.zoomCentro(1 / 1.6)}>−</button>
    </div>
  </div>`;
}
