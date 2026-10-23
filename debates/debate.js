// Checagem do debate: filtro das afirmações (quem falou, tema e veredito) e das frases da retórica (quem e etiqueta).
// Sem JS as listas ficam inteiras e os filtros, escondidos.
(function () {
  function filtro(form, itens, campos, nome, depois) {
    if (!form) return;
    var saida = form.querySelector("output");
    form.hidden = false;
    function aplicar() {
      var n = 0;
      itens.forEach(function (a) {
        var ok = campos.every(function (c) {
          var v = form.elements[c].value;
          return !v || a.dataset[c] === v;
        });
        a.hidden = !ok;
        if (ok) n++;
      });
      if (depois) depois();
      saida.textContent = n + " de " + itens.length + " " + nome;
    }
    form.addEventListener("change", aplicar);
    form.addEventListener("submit", function (e) { e.preventDefault(); });
  }
  filtro(document.querySelector(".db-filtro"), document.querySelectorAll(".db-af"), ["candidato", "tema", "veredito"],
    "afirmações", function () {
      document.querySelectorAll(".db-tema").forEach(function (s) {
        s.hidden = !s.querySelector(".db-af:not([hidden])");
      });
    });
  filtro(document.querySelector(".db-rt-filtro"), document.querySelectorAll(".db-rt li"), ["candidato", "etiqueta"],
    "frases");
  var topo = document.querySelector(".db-topo");
  if (topo) {
    topo.classList.add("flutua");
    var atualizar = function () { topo.hidden = window.scrollY <= window.innerHeight; };
    window.addEventListener("scroll", atualizar, { passive: true });
    atualizar();
  }
})();
