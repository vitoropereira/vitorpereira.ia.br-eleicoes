// Checagem do debate: filtro por candidato e por veredito. Sem JS a lista fica inteira e o filtro, escondido.
(function () {
  var form = document.querySelector(".db-filtro");
  if (!form) return;
  var cartoes = document.querySelectorAll(".db-af");
  var saida = form.querySelector("output");
  form.hidden = false;
  function aplicar() {
    var cand = form.elements.candidato.value, ver = form.elements.veredito.value, n = 0;
    cartoes.forEach(function (a) {
      var ok = (!cand || a.dataset.candidato === cand) && (!ver || a.dataset.veredito === ver);
      a.hidden = !ok;
      if (ok) n++;
    });
    document.querySelectorAll(".db-tema").forEach(function (s) {
      s.hidden = !s.querySelector(".db-af:not([hidden])");
    });
    saida.textContent = n + " de " + cartoes.length + " afirmações";
  }
  form.addEventListener("change", aplicar);
  form.addEventListener("submit", function (e) { e.preventDefault(); });
})();
