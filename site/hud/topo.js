// Decodificador mínimo de TopoJSON (sem dependências) + projeção + índice espacial para hit-test.
// Projeção: equiretangular com x escalado por cos(-14°) (centro aproximado do Brasil); y para baixo.

import { bolhasPessoas } from "./calc.js";

export const UF_COD = {
  11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO", 21: "MA", 22: "PI", 23: "CE", 24: "RN",
  25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR", 42: "SC",
  43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF",
};

const K = Math.cos((-14 * Math.PI) / 180);

/** arcos absolutos e projetados: Float64Array [x0,y0,x1,y1,...] */
function arcosProjetados(topo) {
  const t = topo.transform;
  return topo.arcs.map((a) => {
    const out = new Float64Array(a.length * 2);
    let x = 0, y = 0;
    for (let i = 0; i < a.length; i++) {
      if (t) { x += a[i][0]; y += a[i][1]; } else { x = a[i][0]; y = a[i][1]; }
      const lon = t ? x * t.scale[0] + t.translate[0] : x;
      const lat = t ? y * t.scale[1] + t.translate[1] : y;
      out[2 * i] = lon * K;
      out[2 * i + 1] = -lat;
    }
    return out;
  });
}

/** junta os arcos de um anel (índice negativo = arco invertido, ~i) */
function anel(idx, arcs) {
  const pts = [];
  idx.forEach((ai, k) => {
    const rev = ai < 0, a = arcs[rev ? ~ai : ai], n = a.length / 2;
    for (let j = 0; j < n; j++) {
      if (k > 0 && j === 0) continue; // o 1º ponto repete o último do arco anterior
      const p = rev ? n - 1 - j : j;
      pts.push(a[2 * p], a[2 * p + 1]);
    }
  });
  return Float64Array.from(pts);
}

function areaCentro(r) {
  let a = 0, cx = 0, cy = 0;
  const n = r.length / 2;
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const f = r[2 * j] * r[2 * i + 1] - r[2 * i] * r[2 * j + 1];
    a += f; cx += (r[2 * j] + r[2 * i]) * f; cy += (r[2 * j + 1] + r[2 * i + 1]) * f;
  }
  a /= 2;
  return a ? [Math.abs(a), cx / (6 * a), cy / (6 * a)] : [0, r[0], r[1]];
}

function dentro(r, x, y) {
  let c = false;
  const n = r.length / 2;
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const xi = r[2 * i], yi = r[2 * i + 1], xj = r[2 * j], yj = r[2 * j + 1];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c;
  }
  return c;
}

/**
 * @returns {{muns, indice:Map, bbox:number[], ufs:Object, bordasMun:Path2D, bordasUF:Path2D, hit:(x,y)=>number, visiveis:(x0,y0,x1,y1)=>number[]}}
 */
export function decodificar(topo, objeto = "BRMU") {
  const arcs = arcosProjetados(topo);
  const geoms = topo.objects[objeto].geometries;
  const usoArco = new Array(arcs.length); // UFs que usam cada arco
  const muns = [];
  geoms.forEach((g) => {
    const cod = String(g.properties.codarea);
    const uf = UF_COD[cod.slice(0, 2)] || "??";
    const polys = g.type === "Polygon" ? [g.arcs] : g.type === "MultiPolygon" ? g.arcs : [];
    const rings = [];
    polys.forEach((poly) => poly.forEach((idx) => {
      idx.forEach((ai) => { const k = ai < 0 ? ~ai : ai; (usoArco[k] ||= []).push(uf); });
      rings.push({ r: anel(idx, arcs), externo: rings.length === 0 || poly[0] === idx });
    }));
    muns.push({ cod, uf, aneis: rings });
  });
  // bordas: todas (municípios) e só entre UFs diferentes ou com o mar/vizinhos (estados)
  const bordasMun = new Path2D(), bordasUF = new Path2D();
  arcs.forEach((a, k) => {
    const u = usoArco[k] || [];
    const p = new Path2D();
    p.moveTo(a[0], a[1]);
    for (let i = 2; i < a.length; i += 2) p.lineTo(a[i], a[i + 1]);
    bordasMun.addPath(p);
    if (u.length < 2 || u[0] !== u[1]) bordasUF.addPath(p);
  });
  return montar(muns, bordasMun, bordasUF, false);
}

/**
 * Malha leve só com as 27 UFs (modo de aparelho fraco): contornos SVG de relatorio/dados/mapa.json,
 * projetados por relatorio/montar.py (x = (lon+74,2)·cos(15°)·15, y = (5,5−lat)·15) e trazidos para o mesmo
 * sistema da malha municipal, para trocar uma pela outra sem mexer no enquadramento.
 */
export function decodificarUFs(mapa) {
  const C15 = Math.cos((15 * Math.PI) / 180);
  const muns = [];
  const bordas = new Path2D();
  for (const [uf, { d }] of Object.entries(mapa)) {
    if (!UF_NOME_OK.has(uf)) continue;
    const aneis = [];
    for (const parte of d.split("M").filter(Boolean)) {
      const nums = parte.replace(/Z/g, "").split(/[L,]/).map(Number);
      const r = new Float64Array(nums.length);
      for (let i = 0; i < nums.length; i += 2) {
        r[i] = (nums[i] / (C15 * 15) - 74.2) * K;
        r[i + 1] = nums[i + 1] / 15 - 5.5;
      }
      if (r.length >= 6) aneis.push({ r, externo: true });
    }
    muns.push({ cod: "UF-" + uf, uf, aneis });
  }
  muns.forEach((m) => m.aneis.forEach(({ r }) => {
    bordas.moveTo(r[0], r[1]);
    for (let i = 2; i < r.length; i += 2) bordas.lineTo(r[i], r[i + 1]);
    bordas.closePath();
  }));
  return montar(muns, bordas, bordas, true);
}
const UF_NOME_OK = new Set(Object.values(UF_COD));

function montar(brutos, bordasMun, bordasUF, soUF, bbox0) {
  const muns = [];
  const B = bbox0 ? [...bbox0] : [Infinity, Infinity, -Infinity, -Infinity];
  const ufs = {};
  brutos.forEach(({ cod, uf, aneis }) => {
    const rings = [];
    const bb = [Infinity, Infinity, -Infinity, -Infinity];
    let area = 0, cx = 0, cy = 0;
    const path = new Path2D();
    aneis.forEach(({ r, externo }) => {
      rings.push(r);
      path.moveTo(r[0], r[1]);
      for (let i = 0; i < r.length; i += 2) {
        const x = r[i], y = r[i + 1];
        if (i) path.lineTo(x, y);
        if (x < bb[0]) bb[0] = x; if (y < bb[1]) bb[1] = y; if (x > bb[2]) bb[2] = x; if (y > bb[3]) bb[3] = y;
      }
      path.closePath();
      if (externo) { const [a, x, y] = areaCentro(r); area += a; cx += x * a; cy += y * a; }
    });
    const m = { cod, uf, rings, bbox: bb, path, area, cx: area ? cx / area : (bb[0] + bb[2]) / 2, cy: area ? cy / area : (bb[1] + bb[3]) / 2 };
    muns.push(m);
    B[0] = Math.min(B[0], bb[0]); B[1] = Math.min(B[1], bb[1]); B[2] = Math.max(B[2], bb[2]); B[3] = Math.max(B[3], bb[3]);
    const u = (ufs[uf] ||= { uf, bbox: [Infinity, Infinity, -Infinity, -Infinity], area: 0, sx: 0, sy: 0, lista: [] });
    u.lista.push(muns.length - 1);
    u.area += area; u.sx += m.cx * area; u.sy += m.cy * area;
    u.bbox = [Math.min(u.bbox[0], bb[0]), Math.min(u.bbox[1], bb[1]), Math.max(u.bbox[2], bb[2]), Math.max(u.bbox[3], bb[3])];
  });
  Object.values(ufs).forEach((u) => { u.cx = u.area ? u.sx / u.area : (u.bbox[0] + u.bbox[2]) / 2; u.cy = u.area ? u.sy / u.area : (u.bbox[1] + u.bbox[3]) / 2; });

  // grade para hit-test e recorte da área visível
  const G = 128, gw = (B[2] - B[0]) / G, gh = (B[3] - B[1]) / G;
  const grade = Array.from({ length: G * G }, () => []);
  const cel = (x, y) => [Math.min(G - 1, Math.max(0, Math.floor((x - B[0]) / gw))), Math.min(G - 1, Math.max(0, Math.floor((y - B[1]) / gh)))];
  muns.forEach((m, i) => {
    const [a, b] = cel(m.bbox[0], m.bbox[1]), [c, d] = cel(m.bbox[2], m.bbox[3]);
    for (let y = b; y <= d; y++) for (let x = a; x <= c; x++) grade[y * G + x].push(i);
  });

  function hit(x, y) {
    if (x < B[0] || x > B[2] || y < B[1] || y > B[3]) return -1;
    const [cx, cy] = cel(x, y);
    for (const i of grade[cy * G + cx]) {
      const m = muns[i], bb = m.bbox;
      if (x < bb[0] || x > bb[2] || y < bb[1] || y > bb[3]) continue;
      let c = false;
      for (const r of m.rings) if (dentro(r, x, y)) c = !c;
      if (c) return i;
    }
    return -1;
  }

  function visiveis(x0, y0, x1, y1) {
    const [a, b] = cel(x0, y0), [c, d] = cel(x1, y1);
    const s = new Set();
    for (let y = b; y <= d; y++) for (let x = a; x <= c; x++) for (const i of grade[y * G + x]) s.add(i);
    return [...s];
  }

  const indice = new Map(muns.map((m, i) => [m.cod, i]));
  return { muns, indice, bbox: B, ufs, bordasMun, bordasUF, hit, visiveis, soUF };
}

/**
 * Modo "Pessoas": um círculo por município, com área ∝ eleitorado (posições pré-calculadas em geo/pessoas.json por
 * municipios/pessoas.py). Devolve um geo com os MESMOS índices de `geo.muns`, para cores, seleção e dica servirem sem
 * mudança. O anel poligonal serve ao hit-test e à bbox; o desenho usa o círculo exato (Path2D.arc). Município sem
 * bolha (ex.: 5101837) fica com anel degenerado dentro do próprio contorno: não aparece nem recebe hit. O contorno
 * das UFs da malha vira `fundo`, desenhado por baixo pelo Mapa.
 */
export function decodificarPessoas(geo, pessoas) {
  const bolhas = bolhasPessoas(geo.muns, pessoas);
  const brutos = geo.muns.map((m, i) => {
    const b = bolhas[i];
    if (!b) return { cod: m.cod, uf: m.uf, aneis: [{ r: Float64Array.of(m.cx, m.cy, m.cx, m.cy, m.cx, m.cy), externo: true }] };
    const n = Math.min(48, Math.max(24, Math.ceil(12 + 40 * b.r)));
    const r = new Float64Array(2 * n);
    for (let j = 0; j < n; j++) { const a = (2 * Math.PI * j) / n; r[2 * j] = b.x + b.r * Math.cos(a); r[2 * j + 1] = b.y + b.r * Math.sin(a); }
    return { cod: m.cod, uf: m.uf, aneis: [{ r, externo: true }] };
  });
  const uniao = new Path2D();
  bolhas.forEach((b) => { if (b) { uniao.moveTo(b.x + b.r, b.y); uniao.arc(b.x, b.y, b.r, 0, 2 * Math.PI); } });
  const g = montar(brutos, uniao, new Path2D(), false, geo.bbox);
  g.muns.forEach((m, i) => {
    const b = bolhas[i];
    m.path = new Path2D();
    if (b) { m.path.moveTo(b.x + b.r, b.y); m.path.arc(b.x, b.y, b.r, 0, 2 * Math.PI); }
  });
  return { ...g, fundo: geo.bordasUF, pessoas: true };
}
