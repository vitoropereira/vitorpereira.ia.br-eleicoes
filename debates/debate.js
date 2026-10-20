// Checagem do debate: filtro por quem falou, tema e veredito. Sem JS a lista fica inteira e o filtro, escondido.
(function () {
  var form = document.querySelector(".db-filtro");
  if (!form) return;
  var cartoes = document.querySelectorAll(".db-af");
  var saida = form.querySelector("output");
  var campos = ["candidato", "tema", "veredito"];
  form.hidden = false;
  function aplicar() {
    var n = 0;
    cartoes.forEach(function (a) {
      var ok = campos.every(function (c) {
        var v = form.elements[c].value;
        return !v || a.dataset[c] === v;
      });
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
