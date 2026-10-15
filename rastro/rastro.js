// Rastro do dinheiro: filtro "Só com indício" da tabela de fornecedores. Sem JS a tabela fica inteira e o filtro, escondido.
(function () {
  document.querySelectorAll(".rs-filtro").forEach(function (rotulo) {
    var caixa = rotulo.querySelector("input");
    var bloco = rotulo.closest("details") || document;
    rotulo.hidden = false;
    caixa.addEventListener("change", function () {
      var so = caixa.checked;
      if (so) {
        bloco.open = true;
        bloco.querySelectorAll("details").forEach(function (d) { d.open = true; });
      }
      bloco.querySelectorAll("tr[id^='f-']").forEach(function (tr) {
        tr.hidden = so && !tr.hasAttribute("data-indicio");
      });
    });
  });
})();
