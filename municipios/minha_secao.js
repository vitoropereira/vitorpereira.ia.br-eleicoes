// "Minha seção" (/minha-secao/, issue #155): onde a pessoa vota e quem ganhou ali (presidente). Tudo no navegador:
// lê só arquivos do próprio site (/minha-secao/indice.json, /minha-secao/cep/<pp>.json e /geo/locais/<arquivo>.json,
// gerados por municipios/minha_secao.py e montar_secao.py). A posição do "perto de mim" só serve para calcular a
// distância aqui: nunca vai para URL, armazenamento ou rede. Sem dependência; funções puras em globalThis.MinhaSecao.
(function () {
  "use strict";
  var TOKEN = { PL: "var(--flavio)", PT: "var(--lula)" };

  function escapar(t) {
    return String(t == null ? "" : t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function digitos(q) {
    return String(q == null ? "" : q).replace(/\D/g, "");
  }

  // CEP de 5 ou 8 dígitos (com ou sem hífen) -> os 5 primeiros; qualquer outra coisa -> null
  function cep5(q) {
    var d = digitos(q);
    return d.length === 5 || d.length === 8 ? d.slice(0, 5) : null;
  }

  // distância em km (haversine)
  function distancia(lat1, lon1, lat2, lon2) {
    var r = Math.PI / 180, dl = (lat2 - lat1) * r, dn = (lon2 - lon1) * r;
    var a = Math.sin(dl / 2) * Math.sin(dl / 2) + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(dn / 2) * Math.sin(dn / 2);
    return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  function turnos(reg) {
    return Object.keys(reg.t).sort();
  }

  // locais do município com os turnos juntos: [{lat, lon, nome, bairro, cep, t: {turno: local}}]
  function locais(reg) {
    var por = {}, lista = [];
    turnos(reg).forEach(function (t) {
      reg.t[t].forEach(function (lc) {
        var k = [lc[0], lc[1], lc[2], lc[3], lc[4]].join("|");
        if (!por[k]) {
          por[k] = { lat: lc[0], lon: lc[1], nome: lc[2], bairro: lc[3], cep: lc[4], t: {} };
          lista.push(por[k]);
        }
        por[k].t[t] = lc;
      });
    });
    return lista;
  }

  // a seção (zona, número) em cada turno: [{turno, local, secao}] (vazio se não existir)
  function acharSecao(reg, zona, secao) {
    var z = +zona, s = +secao, achados = [];
    turnos(reg).forEach(function (t) {
      reg.t[t].forEach(function (lc) {
        lc[9].forEach(function (sc) {
          if (sc[0] === z && sc[1] === s) achados.push({ turno: t, local: lc, secao: sc });
        });
      });
    });
    return achados;
  }

  function porCep(reg, cep) {
    return locais(reg).filter(function (l) { return l.cep === cep; });
  }

  // municípios (linhas do indice.json) com centro mais perto do ponto
  function municipiosPerto(mun, lat, lon, n) {
    return mun.filter(function (m) { return m[4] != null && m[5] != null; })
      .map(function (m) { return { m: m, km: distancia(lat, lon, m[4], m[5]) }; })
      .sort(function (a, b) { return a.km - b.km; }).slice(0, n).map(function (x) { return x.m; });
  }

  // locais com coordenada, do mais perto ao mais longe: [{l, km}]
  function pertoDe(lista, lat, lon, n) {
    return lista.filter(function (l) { return l.lat != null && l.lon != null; })
      .map(function (l) { return { l: l, km: distancia(lat, lon, l.lat, l.lon) }; })
      .sort(function (a, b) { return a.km - b.km; }).slice(0, n);
  }

  // votos (na ordem de cand, sem os zeros do fim) -> {linhas: [{nr, nome, sg, v, p}] do mais votado ao menos, validos};
  // null quando o voto por candidato foi omitido (piso de privacidade)
  function ranking(cand, votos, part) {
    if (!votos) return null;
    var linhas = cand.map(function (c, i) { return { nr: c[0], nome: c[1], sg: (part || {})[c[0]] || "", v: votos[i] || 0, i: i }; });
    var validos = linhas.reduce(function (s, x) { return s + x.v; }, 0);
    linhas.forEach(function (x) { x.p = validos ? (100 * x.v) / validos : 0; });
    linhas.sort(function (a, b) { return b.v - a.v || a.i - b.i; });
    return { linhas: linhas, validos: validos };
  }

  // quem ganhou: {linhas: [vencedor]} ou, em empate no topo, {linhas: [empatados], empate: true}; null sem voto válido
  function vencedor(rk) {
    if (!rk || !rk.validos) return null;
    var topo = rk.linhas.filter(function (x) { return x.v === rk.linhas[0].v; });
    return { linhas: topo, empate: topo.length > 1 };
  }

  function nf(n) {
    return Number(n).toLocaleString("pt-BR");
  }

  function pc(p) {
    return p.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + "%";
  }

  function rotulo(x) {
    return escapar(x.nome) + (x.sg ? " (" + escapar(x.sg) + ")" : "");
  }

  function cor(sg) {
    return TOKEN[sg] || "var(--outros)";
  }

  // um bloco de resultado (seção ou local inteiro, num turno)
  function bloco(titulo, cand, votos, bn, aptos, comp, part, piso) {
    var h = '<div class="ms-turno"><h4><span>' + escapar(titulo) + "</span><span>" + nf(comp) + " de " + nf(aptos) + " aptos votaram</span></h4>";
    var rk = ranking(cand, votos, part);
    if (!rk) {
      return h + '<p class="ms-sig">' + (comp < piso
        ? "Menos de " + piso + " eleitores compareceram: sem voto por candidato, para proteger o sigilo do voto."
        : "Voto por candidato omitido: com ele, o voto de uma seção ou local pequeno daria para deduzir pela diferença do total.") + "</p></div>";
    }
    var v = vencedor(rk);
    if (v) {
      h += '<p class="ms-venc">' + (v.empate
        ? "Empate entre " + v.linhas.map(function (x) { return "<b>" + rotulo(x) + "</b>"; }).join(" e ") + ", com " + pc(v.linhas[0].p) + " dos válidos cada"
        : "<b>" + rotulo(v.linhas[0]) + "</b> ganhou aqui, com " + pc(v.linhas[0].p) + " dos votos válidos") + "</p>";
    }
    h += '<ul class="ms-cands">' + rk.linhas.filter(function (x) { return x.v > 0; }).map(function (x) {
      return '<li style="--c:' + cor(x.sg) + '"><span>' + rotulo(x) + "<b>" + nf(x.v) + " · " + pc(x.p) + '</b></span><i style="width:' + x.p.toFixed(2) + '%"></i></li>';
    }).join("") + "</ul>";
    return h + '<p class="ms-num">Válidos ' + nf(rk.validos) + " · brancos e nulos " + nf(bn || 0) + "</p></div>";
  }

  function nomeTurno(t) {
    return t + "º turno";
  }

  // cartão de um local (de locais()); opc.secao = [zona, secao] destaca a seção; opc.km = distância; opc.mun = "Cidade/UF"
  function cartao(l, reg, part, piso, opc) {
    opc = opc || {};
    var onde = [l.bairro, l.cep ? "CEP " + l.cep.slice(0, 5) + "-xxx" : null, opc.mun,
      opc.km != null ? (opc.km < 1 ? Math.round(opc.km * 1000) + " m daqui" : opc.km.toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " km daqui") : null]
      .filter(Boolean).map(escapar).join(" · ");
    var h = '<article class="ms-local' + (opc.secao ? " ms-secao" : "") + '"><h3>' + escapar(l.nome || "Local sem nome no TSE") + "</h3>" +
      (onde ? '<p class="ms-onde">' + onde + "</p>" : "");
    Object.keys(l.t).sort().forEach(function (t) {
      var lc = l.t[t], cand = reg.cand[t];
      if (opc.secao) {
        lc[9].forEach(function (sc) {
          if (sc[0] === opc.secao[0] && sc[1] === opc.secao[1]) {
            h += bloco("Sua seção (zona " + sc[0] + ", seção " + sc[1] + ") · " + nomeTurno(t), cand, sc[4], sc[5], sc[2], sc[3], part, piso);
          }
        });
      }
      h += bloco((opc.secao ? "Local inteiro · " : "") + nomeTurno(t) + (lc[9].length > 1 ? " · " + lc[9].length + " seções" : ""), cand, lc[7], lc[8], lc[5], lc[6], part, piso);
    });
    return h + "</article>";
  }

  // ---- mapa dos locais do município (#156): pontos em canvas sobre o contorno (/minha-secao/contorno/<ibge>.json),
  // cor do vencedor no local (só tokens de partido da brand.css), área do ponto proporcional aos aptos. Sem tiles.
  var RAIO_MIN = 2.5;

  function turnoMapa(reg) {
    var ts = turnos(reg);
    return ts[ts.length - 1];
  }

  // um ponto por local com coordenada no turno: {lat, lon, aptos, est, sg, p, l}; est = "venc" | "empate" | "sem"
  // (nenhum voto válido) | "sigilo" (voto por candidato omitido pelo piso: o ponto não leva voto nenhum)
  function pontosMapa(reg, t, part) {
    var cand = reg.cand[t];
    return locais(reg).filter(function (l) { return l.t[t] && l.lat != null && l.lon != null; }).map(function (l) {
      var lc = l.t[t], pt = { lat: l.lat, lon: l.lon, aptos: lc[5], est: "sigilo", sg: "", p: null, l: l };
      var v = vencedor(ranking(cand, lc[7], part));
      if (lc[7]) pt.est = !v ? "sem" : v.empate ? "empate" : "venc";
      if (pt.est === "venc") { pt.sg = v.linhas[0].sg; pt.p = v.linhas[0].p; pt.nome = v.linhas[0].nome; }
      return pt;
    });
  }

  function semCoordenada(reg, t) {
    return locais(reg).filter(function (l) { return l.t[t] && (l.lat == null || l.lon == null); }).length;
  }

  // cor de preenchimento (token) ou null: sigilo é um anel vazado, sem cor de candidato
  function corPonto(pt) {
    if (pt.est === "venc") return cor(pt.sg);
    return pt.est === "sigilo" ? null : "var(--neutral)";
  }

  // projeção plana (lon × cos da latitude média) do bbox [lon0, lat0, lon1, lat1] na largura w, altura até hMax
  function enquadrar(bb, w, hMax, pad) {
    var k = Math.cos(((bb[1] + bb[3]) / 2) * Math.PI / 180);
    var dx = Math.max((bb[2] - bb[0]) * k, 1e-6), dy = Math.max(bb[3] - bb[1], 1e-6);
    var s = Math.min((w - 2 * pad) / dx, (hMax - 2 * pad) / dy);
    var h = Math.min(hMax, Math.ceil(dy * s + 2 * pad)), ox = pad + ((w - 2 * pad) - dx * s) / 2;
    return {
      h: h,
      x: function (lon) { return ox + (lon - bb[0]) * k * s; },
      y: function (lat) { return pad + (bb[3] - lat) * s; },
    };
  }

  function raioMax(n) {
    return Math.max(4, Math.min(14, 160 / Math.sqrt(Math.max(n, 1))));
  }

  // área do ponto proporcional aos aptos; nunca abaixo de RAIO_MIN
  function raio(aptos, max, rMax) {
    return RAIO_MIN + (rMax - RAIO_MIN) * Math.sqrt(Math.max(aptos, 0) / Math.max(max, 1));
  }

  // índice do ponto ({x, y, r}) mais perto de (x, y) a no máximo r + folga; -1 se nenhum
  function tocado(pts, x, y, folga) {
    var melhor = -1, dm = Infinity;
    for (var i = 0; i < pts.length; i++) {
      var p = pts[i], d = Math.hypot(p.x - x, p.y - y);
      if (d <= p.r + folga && d < dm) { dm = d; melhor = i; }
    }
    return melhor;
  }

  globalThis.MinhaSecao = {
    escapar: escapar, cep5: cep5, distancia: distancia, locais: locais, acharSecao: acharSecao, porCep: porCep,
    municipiosPerto: municipiosPerto, pertoDe: pertoDe, ranking: ranking, vencedor: vencedor, bloco: bloco, cartao: cartao,
    turnoMapa: turnoMapa, pontosMapa: pontosMapa, semCoordenada: semCoordenada, corPonto: corPonto, enquadrar: enquadrar,
    raio: raio, raioMax: raioMax, tocado: tocado, RAIO_MIN: RAIO_MIN,
  };
  if (typeof document === "undefined") return;

  var app = document.getElementById("ms-app");
  if (!app) return;
  var res = document.getElementById("ms-res");
  var selUf = document.getElementById("ms-uf"), selMun = document.getElementById("ms-mun");
  var idx = null, cache = {};

  function ler(caminho) {
    return fetch(caminho).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
  }

  // registro do município: o arquivo é por município (<ibge>.json) ou por UF (<UF>.json com {ibge: registro})
  function registro(m) {
    if (!cache[m[3]]) cache[m[3]] = ler("/geo/locais/" + m[3] + ".json");
    return cache[m[3]].then(function (o) { return m[3] === m[0] ? o : o[m[0]]; });
  }

  function mostrar(h) {
    res.innerHTML = h;
  }

  function msg(t) {
    esconderMapa();
    mostrar('<p class="ms-msg">' + t + "</p>");
  }

  function falhou() {
    msg("Não foi possível carregar os dados agora. Tente de novo em instantes.");
  }

  function munDe(ibge) {
    return idx.mun.filter(function (m) { return m[0] === ibge; })[0];
  }

  function onde(m) {
    return m[1] + "/" + m[2];
  }

  function opcoes(sel, itens) {
    sel.innerHTML = itens.map(function (x) { return '<option value="' + escapar(x[0]) + '">' + escapar(x[1]) + "</option>"; }).join("");
  }

  function encherMun() {
    opcoes(selMun, idx.mun.filter(function (m) { return m[2] === selUf.value; }).map(function (m) { return [m[0], m[1]]; }));
  }


  // ---- mapa (#156): desenha o município do resultado; toque/clique num ponto mostra o cartão do local (que respeita o piso)
  var mp = {
    el: document.getElementById("ms-mapa"), cv: document.getElementById("ms-mapa-c"), sub: document.getElementById("ms-mapa-sub"),
    turnos: document.getElementById("ms-mapa-turnos"), leg: document.getElementById("ms-mapa-leg"),
    nota: document.getElementById("ms-mapa-nota"), info: document.getElementById("ms-mapa-info"),
  };
  var est = null;

  function chave(l) {
    return [l.lat, l.lon, l.nome, l.cep].join("|");
  }

  function token(v, css) {
    var m = /^var\((--[a-z0-9-]+)\)$/.exec(v || "");
    return m ? css.getPropertyValue(m[1]).trim() : v;
  }

  function esconderMapa() {
    est = null;
    mp.el.hidden = true;
  }

  // m = linha do indice.json; destaque = locais (de locais()) a marcar com um anel
  function mostrarMapa(m, reg, destaque) {
    var meu = est = { m: m, reg: reg, t: turnoMapa(reg), dest: (destaque || []).map(chave), sel: null, cont: null };
    mp.info.innerHTML = "";
    ler("/minha-secao/contorno/" + m[0] + ".json").catch(function () { return null; }).then(function (c) {
      if (est !== meu) return;
      est.cont = c;
      montarMapa();
    });
  }

  function montarMapa() {
    var reg = est.reg, ts = turnos(reg);
    est.pts = pontosMapa(reg, est.t, idx.part);
    if (!est.pts.length) { esconderMapa(); return; }
    mp.el.hidden = false;
    mp.sub.innerHTML = escapar(onde(est.m)) + " · " + nomeTurno(est.t) + ". Toque num ponto para ver o local e o resultado.";
    mp.turnos.innerHTML = ts.length > 1 ? ts.map(function (t) {
      return '<button type="button" data-t="' + escapar(t) + '" aria-pressed="' + (t === est.t) + '">' + nomeTurno(t) + "</button>";
    }).join("") : "";
    var vistos = {}, leg = [];
    est.pts.forEach(function (p) {
      var k = p.est === "venc" ? "v" + p.sg + "|" + p.nome : p.est === "sigilo" ? "s" : "e";
      if (vistos[k]) return;
      vistos[k] = 1;
      leg.push(p.est === "venc" ? [0, '<li><i style="--c:' + corPonto(p) + '"></i>' + escapar(p.nome) + (p.sg ? " (" + escapar(p.sg) + ")" : "") + " ganhou</li>"]
        : p.est === "sigilo" ? [2, '<li><i class="ms-vaz"></i>Voto oculto (sigilo)</li>'] : [1, '<li><i style="--c:var(--neutral)"></i>Empate ou sem voto válido</li>']);
    });
    mp.leg.innerHTML = leg.sort(function (a, b) { return a[0] - b[0]; }).map(function (x) { return x[1]; }).join("");
    var fora = semCoordenada(reg, est.t);
    mp.nota.textContent = "Área do ponto proporcional aos eleitores aptos do local. " + nf(est.pts.length) + (est.pts.length === 1 ? " local" : " locais") + " no mapa" +
      (fora ? "; " + nf(fora) + (fora === 1 ? " local sem coordenada" : " locais sem coordenada") + " no arquivo do TSE " + (fora === 1 ? "fica" : "ficam") + " fora" : "") + ".";
    mp.cv.setAttribute("aria-label", "Mapa de " + est.pts.length + " locais de votação em " + onde(est.m) + ", cor pelo vencedor de cada local no " + nomeTurno(est.t));
    desenharMapa();
  }

  function desenharMapa() {
    if (!est || !est.pts || mp.el.hidden) return;
    performance.mark("ms-mapa-0");
    var cv = mp.cv, w = cv.clientWidth, pts = est.pts, c = est.cont, css = getComputedStyle(document.documentElement);
    if (!w) return;
    var bb = c ? c.bb.slice() : [Infinity, Infinity, -Infinity, -Infinity];
    pts.forEach(function (p) {
      bb[0] = Math.min(bb[0], p.lon); bb[1] = Math.min(bb[1], p.lat); bb[2] = Math.max(bb[2], p.lon); bb[3] = Math.max(bb[3], p.lat);
    });
    var e = enquadrar(bb, w, Math.min(560, Math.round(w * 1.25)), 10), dpr = Math.min(window.devicePixelRatio || 1, 3);
    cv.style.height = e.h + "px";
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(e.h * dpr);
    var ctx = cv.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, e.h);
    if (c) {
      ctx.beginPath();
      c.an.forEach(function (a) {
        ctx.moveTo(e.x(a[0]), e.y(a[1]));
        for (var i = 2; i < a.length; i += 2) ctx.lineTo(e.x(a[i]), e.y(a[i + 1]));
        ctx.closePath();
      });
      ctx.fillStyle = token("var(--soft)", css);
      ctx.fill("evenodd");
      ctx.strokeStyle = token("var(--muted)", css);
      ctx.lineWidth = 1;
      ctx.stroke();
    }
    var max = 0, rm = raioMax(pts.length), cores = {}, fundo = token("var(--bg)", css), vaz = token("var(--muted)", css);
    pts.forEach(function (p) { if (p.aptos > max) max = p.aptos; });
    pts.forEach(function (p) { p.x = e.x(p.lon); p.y = e.y(p.lat); p.r = raio(p.aptos, max, rm); });
    // maiores primeiro: o local pequeno fica por cima e continua tocável
    pts.slice().sort(function (a, b) { return b.r - a.r; }).forEach(function (p) {
      var cp = corPonto(p);
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, 2 * Math.PI);
      if (cp) {
        ctx.globalAlpha = 0.85;
        ctx.fillStyle = cores[cp] || (cores[cp] = token(cp, css));
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.lineWidth = 0.75;
        ctx.strokeStyle = fundo;
      } else {
        ctx.lineWidth = 1.25;
        ctx.strokeStyle = vaz;
      }
      ctx.stroke();
    });
    ctx.strokeStyle = token("var(--ink)", css);
    ctx.lineWidth = 2;
    pts.forEach(function (p) {
      if (p === est.sel || est.dest.indexOf(chave(p.l)) >= 0) {
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r + 3, 0, 2 * Math.PI);
        ctx.stroke();
      }
    });
    performance.measure("ms-mapa", "ms-mapa-0");
  }

  mp.cv.addEventListener("click", function (ev) {
    if (!est || !est.pts) return;
    var r = mp.cv.getBoundingClientRect(), i = tocado(est.pts, ev.clientX - r.left, ev.clientY - r.top, 10);
    est.sel = i >= 0 ? est.pts[i] : null;
    mp.info.innerHTML = est.sel ? cartao(est.sel.l, est.reg, idx.part, idx.piso, { mun: onde(est.m) }) : "";
    desenharMapa();
  });

  mp.turnos.addEventListener("click", function (ev) {
    var t = ev.target.getAttribute && ev.target.getAttribute("data-t");
    if (!est || !t || t === est.t) return;
    est.t = t;
    est.sel = null;
    mp.info.innerHTML = "";
    montarMapa();
  });

  var pendente = false;
  function redesenhar() {
    if (pendente) return;
    pendente = true;
    requestAnimationFrame(function () { pendente = false; desenharMapa(); });
  }
  window.addEventListener("resize", redesenhar);
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: light)");
    if (mq.addEventListener) mq.addEventListener("change", redesenhar);
  }
  if (window.MutationObserver) new MutationObserver(redesenhar).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  document.getElementById("ms-f-secao").addEventListener("submit", function (ev) {
    ev.preventDefault();
    var m = munDe(selMun.value), z = +digitos(document.getElementById("ms-zona").value), s = +digitos(document.getElementById("ms-secao").value);
    if (!m || !z || !s) { msg("Escolha o município e digite os números da zona e da seção."); return; }
    msg("Carregando…");
    registro(m).then(function (reg) {
      var achados = acharSecao(reg, z, s);
      if (!achados.length) {
        msg("Não achamos a zona " + z + ", seção " + s + " em " + escapar(onde(m)) + ". Confira os números no título ou no e-Título. " +
          "Seção agregada a outra aparece pelo número da seção principal; seção com poucos eleitores pode ter ficado sem local no arquivo do TSE.");
        return;
      }
      var lc = achados[0].local, l = locais(reg).filter(function (x) { return x.nome === lc[2] && x.cep === lc[4] && x.lat === lc[0] && x.lon === lc[1]; })[0];
      mostrar('<p class="ms-res-t">Seu local de votação · ' + escapar(onde(m)) + "</p>" + cartao(l, reg, idx.part, idx.piso, { secao: [z, s], mun: onde(m) }));
      mostrarMapa(m, reg, [l]);
    }, falhou);
  });

  document.getElementById("ms-f-cep").addEventListener("submit", function (ev) {
    ev.preventDefault();
    var c = cep5(document.getElementById("ms-cep").value);
    if (!c) { msg("Digite um CEP com 8 dígitos (ou só os 5 primeiros)."); return; }
    msg("Carregando…");
    ler("/minha-secao/cep/" + c.slice(0, 2) + ".json").catch(function () { return {}; }).then(function (d) {
      var ms = (d[c] || []).map(munDe).filter(Boolean);
      if (!ms.length) { msg("Nenhum local de votação com CEP começando em " + c + "."); return; }
      return Promise.all(ms.map(registro)).then(function (regs) {
        var h = "", n = 0;
        regs.forEach(function (reg, i) {
          porCep(reg, c).forEach(function (l) { n++; h += cartao(l, reg, idx.part, idx.piso, { mun: onde(ms[i]) }); });
        });
        mostrar('<p class="ms-res-t">' + n + (n === 1 ? " local" : " locais") + " com CEP " + c + "-xxx</p>" + h);
        mostrarMapa(ms[0], regs[0], porCep(regs[0], c));
      });
    }).catch(falhou);
  });

  document.getElementById("ms-perto").addEventListener("click", function () {
    var bt = this;
    if (!navigator.geolocation) { msg("Seu navegador não oferece localização. Use a busca pelo título ou pelo CEP."); return; }
    bt.disabled = true;
    msg("Pedindo a sua localização ao navegador…");
    navigator.geolocation.getCurrentPosition(function (pos) {
      var lat = pos.coords.latitude, lon = pos.coords.longitude;
      var ms = municipiosPerto(idx.mun, lat, lon, 3);
      if (!ms.length) { bt.disabled = false; msg("Sem coordenadas dos locais de votação para calcular a distância."); return; }
      Promise.all(ms.map(registro)).then(function (regs) {
        var todos = [];
        regs.forEach(function (reg, i) { locais(reg).forEach(function (l) { todos.push({ l: l, reg: reg, m: ms[i] }); }); });
        var perto = pertoDe(todos.map(function (x) { return x.l; }), lat, lon, 8);
        mostrar('<p class="ms-res-t">Locais de votação mais perto (distância em linha reta)</p>' + perto.map(function (p) {
          var x = todos.filter(function (y) { return y.l === p.l; })[0];
          return cartao(p.l, x.reg, idx.part, idx.piso, { km: p.km, mun: onde(x.m) });
        }).join(""));
        var x0 = perto.length ? todos.filter(function (y) { return y.l === perto[0].l; })[0] : null;
        if (x0) mostrarMapa(x0.m, x0.reg, perto.filter(function (p) { return todos.some(function (y) { return y.l === p.l && y.m === x0.m; }); }).map(function (p) { return p.l; }));
        else esconderMapa();
        bt.disabled = false;
      }, function () { bt.disabled = false; falhou(); });
    }, function () {
      bt.disabled = false;
      msg("Não deu para obter a sua localização (permissão negada ou sinal fraco). Use a busca pelo título ou pelo CEP.");
    }, { enableHighAccuracy: false, timeout: 15000, maximumAge: 600000 });
  });

  ler("/minha-secao/indice.json").then(function (d) {
    idx = d;
    var ufs = [];
    d.mun.forEach(function (m) { if (ufs.indexOf(m[2]) < 0) ufs.push(m[2]); });
    opcoes(selUf, ufs.sort().map(function (u) { return [u, u]; }));
    selUf.addEventListener("change", encherMun);
    encherMun();
    app.hidden = false;
  }, function () {
    app.hidden = false;
    falhou();
  });
})();
