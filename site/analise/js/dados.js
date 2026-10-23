// Único lugar com fetch da Análise: /analise/dados/*.json (gerados por analise/calcular.py).
export const PEQUENOS = ["destaques", "campos", "dividido", "cadeiras", "brancos", "fragmentacao", "legenda", "puxadores", "cenarios", "faq", "lados"];
export const GRANDES = ["divergencias", "comparacao2022", "terra-gente", "mun"]; // um registro por município

async function um(nome) {
  // "mun" = nomes dos municípios (o mesmo meta.json do HUD), só para as dicas dos mapas e da dispersão
  if (nome === "mun") { const r = await fetch("/geo/t1/meta.json"); if (!r.ok) throw new Error("meta.json"); return (await r.json()).mun; }
  const r = await fetch(`/analise/dados/${nome}.json`);
  if (!r.ok) throw new Error(`${nome}.json: HTTP ${r.status}`);
  return r.json();
}

/** baixa tudo; chama aoChegar(D) quando os pequenos chegam e de novo a cada grande. Arquivo que falta fica de fora. */
export async function carregar(aoChegar, nomes = [...PEQUENOS, ...GRANDES]) {
  const D = {};
  const pedir = (n) => um(n).then((d) => { D[n] = d; }).catch(() => {});
  const pequenos = Promise.all(nomes.filter((n) => !GRANDES.includes(n)).map(pedir));
  const grandes = nomes.filter((n) => GRANDES.includes(n)).map((n) => Promise.all([pedir(n), pequenos]).then(() => aoChegar({ ...D })));
  await pequenos;
  aoChegar({ ...D });
  await Promise.all(grandes);
  return D;
}
