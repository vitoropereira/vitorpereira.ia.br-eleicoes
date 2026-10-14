(function(){
  var C="consent";
  function ler(){var m=document.cookie.match(/(?:^|;\s*)consent=(accepted|rejected)/);return m?m[1]:null}
  function gravar(v){document.cookie=C+"="+v+"; path=/; max-age=31536000; SameSite=Lax"}
  function carregar(){
    if(window.__medindo)return;window.__medindo=true;
    var GA="G-N6J962GXT3";
    var g=document.createElement("script");g.async=true;g.src="https://www.googletagmanager.com/gtag/js?id="+GA;document.head.appendChild(g);
    window.dataLayer=window.dataLayer||[];window.gtag=function(){dataLayer.push(arguments)};gtag("js",new Date());gtag("config",GA,{anonymize_ip:true});
    var CL="tp8n6kanob";
    window.clarity=window.clarity||function(){(window.clarity.q=window.clarity.q||[]).push(arguments)};
    var c=document.createElement("script");c.async=true;c.src="https://www.clarity.ms/tag/"+CL;document.head.appendChild(c);
  }
  var v=ler();
  if(v==="accepted")carregar();
  window.addEventListener("consent:reopen",mostrar);
  if(!v)mostrar();
  function mostrar(ev){
  if(document.querySelector(".consent"))return;
  var b=document.createElement("div");b.className="consent";b.setAttribute("role","dialog");b.setAttribute("aria-live","polite");b.setAttribute("aria-label","Cookies");
  b.innerHTML='<div class="in"><p>Usamos cookies pra entender como o site é usado e melhorar sua experiência. Você pode aceitar ou recusar. <a href="https://vitorpereira.ia.br/privacidade" rel="noopener">Política de privacidade</a></p><div class="bt"><button type="button" data-v="rejected">Recusar</button><button type="button" class="ok" data-v="accepted">Aceitar</button></div></div>';
  b.addEventListener("click",function(e){var x=e.target.getAttribute&&e.target.getAttribute("data-v");if(!x)return;
    // GA e Clarity não descarregam: quem revoga depois de aceitar recarrega a página sem eles
    var antes=ler();gravar(x);b.remove();if(x==="accepted")carregar();else if(antes==="accepted")location.reload()});
  document.body.appendChild(b);
  if(ev){var ok=b.querySelector("button.ok");if(ok)ok.focus({preventScroll:true})}
  }
})();
