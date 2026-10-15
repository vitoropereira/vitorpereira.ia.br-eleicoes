// Busca do Rastro do dinheiro: eleito, empresa, CNPJ e sócio. Sem dependência; o índice (/rastro/busca.json, gerado por
// rastro/busca.py) só é baixado quando o campo ganha foco. Sem JS, fica o link para a lista de eleitos da home.
(function () {
  "use strict";
  var MAX = 20;
  var ROTULO = { e: "Eleito(a)", f: "Empresa", s: "Sócio(a)" };
  var PENDENTE = "página ainda não publicada; entra nos próximos lotes";

  // Mesmos passos de normalizar em rastro/busca.py: NFD, sem diacríticos, minúsculas, espaços juntos.
  function normalizar(t) {
    return String(t == null ? "" : t).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
  }

  function escapar(t) {
    return String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // Consulta só de dígitos e pontuação de CNPJ vira dígitos ("33.333.333/0001-91" -> "33333333000191").
  function chave(q) {
    var d = q.replace(/[.\-\/\s]/g, "");
    return /^\d+$/.test(d) ? d : normalizar(q);
  }

  function buscar(itens, q) {
    var k = chave(q);
    if (k.length < 2) return [];
    var ordem = { e: 0, f: 1, s: 2 };
    var achados = [];
    for (var i = 0; i < itens.length; i++) {
      var pos = itens[i].k.indexOf(k);
      if (pos < 0) continue;
      var inicio = pos === 0 ? 0 : itens[i].k.charAt(pos - 1) === " " ? 1 : 2;
      achados.push({ it: itens[i], r: inicio * 10 + ordem[itens[i].t] });
    }
    achados.sort(function (a, b) { return a.r - b.r || (a.it.k < b.it.k ? -1 : a.it.k > b.it.k ? 1 : 0); });
    return achados.slice(0, MAX).map(function (a) { return a.it; });
  }

  // Nome com o trecho buscado em <b>; tudo escapado antes de montar o HTML.
  function destacar(nome, q) {
    var k = normalizar(q);
    var norm = "", mapa = [];
    for (var i = 0; i < nome.length; i++) {
      var c = nome.charAt(i).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
      for (var j = 0; j < c.length; j++) { norm += c.charAt(j); mapa.push(i); }
    }
    var pos = k ? norm.indexOf(k) : -1;
    if (pos < 0) return escapar(nome);
    var a = mapa[pos], b = mapa[pos + k.length - 1] + 1;
    return escapar(nome.slice(0, a)) + "<b>" + escapar(nome.slice(a, b)) + "</b>" + escapar(nome.slice(b));
  }

  function linha(it, q, i) {
    var c = it.t === "e" && it.p === 0 ? it.c + " · " + PENDENTE : it.c;
    return '<li role="option" id="rs-busca-o' + i + '" aria-selected="false"><a href="' + escapar(it.u) + '" tabindex="-1">' +
      '<span class="rs-busca-t">' + escapar(ROTULO[it.t] || "") + "</span>" + destacar(it.n, q) +
      "<small>" + escapar(c) + "</small></a></li>";
  }

  globalThis.RastroBusca = { normalizar: normalizar, escapar: escapar, buscar: buscar, destacar: destacar, linha: linha };
  if (typeof document === "undefined") return;

  var caixa = document.querySelector("[data-rs-busca]");
  if (!caixa) return;
  var input = caixa.querySelector("input");
  var lista = caixa.querySelector("[role=listbox]");
  var sem = caixa.querySelector(".rs-busca-sem");
  caixa.querySelector(".rs-busca-cx").hidden = false;
  if (sem) sem.hidden = true;

  var itens = null, carregando = null, achados = [], ativo = -1;

  function carregar() {
    if (carregando) return carregando;
    var ler = function (url) { return fetch(url).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }); };
    carregando = ler("/rastro/busca.json").then(function (d) {
      if (!d.partes) return d.itens;
      return Promise.all(d.partes.map(ler)).then(function (ps) { return [].concat.apply([], ps.map(function (p) { return p.itens; })); });
    }).then(function (v) { itens = v; mostrar(); }, function () {
      carregando = null;
      lista.innerHTML = '<li class="rs-busca-vazio">Busca indisponível agora. <a href="/rastro/#eleitos">Ver a lista completa de eleitos</a></li>';
      abrir(true);
    });
    return carregando;
  }

  function abrir(sim) {
    lista.hidden = !sim;
    input.setAttribute("aria-expanded", sim ? "true" : "false");
    if (!sim) { ativo = -1; input.removeAttribute("aria-activedescendant"); }
  }

  function mostrar() {
    var q = input.value;
    if (chave(q).length < 2) { abrir(false); return; }
    if (!itens) { carregar(); return; }
    achados = buscar(itens, q);
    ativo = -1;
    input.removeAttribute("aria-activedescendant");
    lista.innerHTML = achados.length ? achados.map(function (it, i) { return linha(it, q, i); }).join("")
      : '<li class="rs-busca-vazio">Nada encontrado.</li>';
    abrir(true);
  }

  function marcar(i) {
    var ops = lista.querySelectorAll("[role=option]");
    if (!ops.length) return;
    ativo = (i + ops.length) % ops.length;
    for (var j = 0; j < ops.length; j++) ops[j].setAttribute("aria-selected", j === ativo ? "true" : "false");
    input.setAttribute("aria-activedescendant", ops[ativo].id);
    ops[ativo].scrollIntoView({ block: "nearest" });
  }

  input.addEventListener("focus", function () { carregar(); if (input.value) mostrar(); });
  input.addEventListener("input", mostrar);
  input.addEventListener("keydown", function (ev) {
    if (ev.key === "ArrowDown") { ev.preventDefault(); if (lista.hidden) mostrar(); marcar(ativo + 1); }
    else if (ev.key === "ArrowUp") { ev.preventDefault(); marcar(ativo - 1); }
    else if (ev.key === "Enter") {
      var alvo = achados[ativo < 0 ? 0 : ativo];
      if (alvo && !lista.hidden) { ev.preventDefault(); location.href = alvo.u; }
    } else if (ev.key === "Escape") { abrir(false); }
  });
  document.addEventListener("click", function (ev) { if (!caixa.contains(ev.target)) abrir(false); });
  document.addEventListener("keydown", function (ev) {
    var t = ev.target, campo = t && (t.isContentEditable || /^(input|textarea|select)$/i.test(t.tagName));
    if (ev.key === "/" && !campo && !ev.ctrlKey && !ev.metaKey && !ev.altKey) { ev.preventDefault(); input.focus(); }
  });
})();
