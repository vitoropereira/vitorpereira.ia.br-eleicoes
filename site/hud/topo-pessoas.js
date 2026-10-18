// "Pessoas no site agora" no cabeçalho de todas as páginas (sitebar e topo da Análise: build_site.agora_topo). Mesmo
// canal de presença do HUD (hud/presenca.js), então o número é o total do site. A config vem nos data-* do próprio link
// (url, key = publishable, canal). Sem config, chave geral desligada ou erro: o link continua escondido.
import { assinarPresenca } from "./presenca.js";

export const texto = (n) => (typeof n === "string" ? n : new Intl.NumberFormat("pt-BR").format(n));
export const rotulo = (n) => `${texto(n)} ${n === 1 ? "pessoa" : "pessoas"} no site agora`;

/** liga o contador no elemento; devolve a função que desliga */
export function montar(el, assinar = assinarPresenca) {
  const b = el?.querySelector("b");
  if (!b) return () => {};
  const { url, key, canal } = el.dataset;
  return assinar({ url, key, canal }, (n) => {
    if (n == null) { el.hidden = true; return; }
    b.textContent = texto(n);
    el.setAttribute("aria-label", rotulo(n));
    el.title = rotulo(n);
    el.hidden = false;
  });
}

if (typeof document !== "undefined") {
  const el = document.querySelector("a.agora[data-canal]");
  if (el) montar(el);
}
