// Botão "☰ Seções" (painel /ao-vivo/ e /analise/): abre a lista de seções do site (a mesma da sitebar, vinda de
// build_site.secoes()). Teclado: abrir leva o foco ao primeiro link, Esc fecha e devolve o foco ao botão; clicar fora
// ou sair com Tab fecha. A Análise traz o HTML estático do build e é ligada aqui; o painel reaproveita ligarSecoes().

const LIGADO = Symbol("secoes");

/** liga abrir/fechar num `.secoes` (button + nav[hidden]); devolve a função que desliga tudo */
export function ligarSecoes(raiz, doc = globalThis.document) {
  if (!raiz || raiz[LIGADO]) return raiz?.[LIGADO] || (() => {});
  const bt = raiz.querySelector("button"), nav = raiz.querySelector("nav");
  if (!bt || !nav || !doc) return () => {};
  const aberto = () => bt.getAttribute("aria-expanded") === "true";
  const fechar = (devolverFoco) => {
    if (!aberto()) return;
    bt.setAttribute("aria-expanded", "false");
    nav.hidden = true;
    if (devolverFoco) bt.focus();
  };
  const abrir = () => {
    bt.setAttribute("aria-expanded", "true");
    nav.hidden = false;
    nav.querySelector("a")?.focus();
  };
  const noBotao = () => (aberto() ? fechar(false) : abrir());
  const noTeclado = (e) => { if (e.key === "Escape" && aberto()) { e.preventDefault(); fechar(true); } };
  const noClique = (e) => { if (aberto() && !raiz.contains(e.target)) fechar(false); };
  const naSaida = (e) => { if (aberto() && e.relatedTarget && !raiz.contains(e.relatedTarget)) fechar(false); };
  bt.addEventListener("click", noBotao);
  doc.addEventListener("keydown", noTeclado);
  doc.addEventListener("click", noClique);
  raiz.addEventListener("focusout", naSaida);
  const desligar = () => {
    bt.removeEventListener("click", noBotao);
    doc.removeEventListener("keydown", noTeclado);
    doc.removeEventListener("click", noClique);
    raiz.removeEventListener("focusout", naSaida);
    delete raiz[LIGADO];
  };
  raiz[LIGADO] = desligar;
  return desligar;
}

// páginas com o menu estático (Análise): liga o que já está no HTML
if (typeof document !== "undefined") {
  for (const el of document.querySelectorAll(".secoes")) ligarSecoes(el, document);
}
