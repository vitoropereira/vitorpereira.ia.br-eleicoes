// Textos fixos da Análise: "Entenda" (didático, neutro) e linha de fonte de cada seção.
import { html } from "/vendor/preact-htm.module.js";

const TSE = html`<a href="https://resultados.tse.jus.br/oficial/app/index.html" rel="noopener">TSE</a>`;
const CALC = html`<a href="/analise/codigo/">cálculo aberto</a>`;

export const FONTE = {
  campos: html`Fonte: ${TSE}, 1º turno de 2026, votos nominais e de legenda por partido. Lados: classificação em <a href="#metodo">Método</a>.`,
  "voto-dividido": html`Fonte: ${TSE}, resultado por município. Estimativa própria (${CALC}); não é contagem oficial.`,
  "votos-cadeiras": html`Fonte: ${TSE}, eleitos e votos do 1º turno de 2026.`,
  divergencias: html`Fonte: ${TSE}, partido/candidato mais votado por município; malha do <a href="https://www.ibge.gov.br/" rel="noopener">IBGE</a>.`,
  "comparacao-2022": html`Fonte: ${TSE}, resultados de 2022 e de 2026 por município. Em 2022, o outro lado é Jair Bolsonaro.`,
  "cenarios-2-turno": html`Fonte: ${TSE} (votos do 1º turno) e pesquisas registradas no TSE, com link para cada uma. Cenário, não previsão.`,
  "brancos-nulos": html`Fonte: ${TSE}, 1º turno de 2026.`,
  fragmentacao: html`Fonte: ${TSE}, eleitos do 1º turno de 2026. Índice de Laakso-Taagepera.`,
  legenda: html`Fonte: ${TSE}, votos nominais e de legenda.`,
  puxadores: html`Fonte: ${TSE}. "Puxados" é estimativa a partir do quociente eleitoral.`,
};

export const ENTENDA = {
  campos: html`
    <p>Cada partido foi posto em um de três <b>campos</b> pelo apoio declarado no 2º turno presidencial: o de Lula, o de Flávio ou o centro (quem não declarou apoio, com prova, fica no centro). A lista de partidos e as provas estão em <a href="#metodo">Método</a>.</p>
    <p>Somamos os votos de cada campo em cada cargo. Para presidente, contam os candidatos; para deputado, os votos no candidato e na legenda do partido.</p>
    <p><b>Senado:</b> em 2026 cada eleitor votou em dois senadores, então os votos somam o dobro do número de eleitores. As porcentagens comparam campos entre si, não pessoas.</p>`,
  "voto-dividido": html`
    <p>O voto é secreto: ninguém sabe em quem cada pessoa votou. Mas dá para <b>estimar</b> olhando os municípios. Onde Lula foi bem e os deputados do campo dele foram mal, parte dos eleitores de Lula votou em deputado de outro campo.</p>
    <p>A técnica se chama <b>inferência ecológica</b>: um modelo estatístico cruza os resultados dos 5.571 municípios e estima quanto de cada voto para presidente foi para cada campo nos outros cargos. A faixa é a de 90% do erro estatístico; não cobre as limitações do método (por exemplo, o comportamento pode variar dentro do município). No DF, com um município só, não há como estimar.</p>
    <p>No gráfico de pontos, cada ponto é um município. Pontos abaixo da linha tracejada são lugares onde Lula teve mais votos que o campo dele para deputado federal.</p>`,
  "votos-cadeiras": html`
    <p>Deputados são eleitos pelo sistema <b>proporcional</b>: o total de votos válidos é dividido pelo número de vagas, o que dá o <b>quociente eleitoral</b>. Cada partido ou federação ganha tantas vagas quantas vezes atinge o quociente, e as sobras são distribuídas pelas maiores médias.</p>
    <p>Por isso a fatia de cadeiras pode ficar acima ou abaixo da fatia de votos: partidos que não atingem o quociente têm mais dificuldade de conseguir vaga, mesmo depois que o STF abriu a última fase das sobras a todos os partidos (ADIs 7228, 7263 e 7325), decisão que vale desde a eleição de 2022.</p>
    <p>O <b>Senado</b> é majoritário: em cada estado, quem tem mais votos leva a vaga, mesmo com pouca vantagem. Por isso a distância entre votos e cadeiras costuma ser maior lá.</p>`,
  divergencias: html`
    <p>Para cada município, comparamos quem teve mais votos para presidente entre Lula e Flávio com o campo que teve mais votos no cargo escolhido. Quando são diferentes (inclusive quando o centro venceu no cargo), o município entra como <b>divergente</b>. Municípios com empate entre Lula e Flávio ficam fora.</p>
    <p>Isso é contagem, não estimativa: mostra onde a preferência para presidente e para o outro cargo não coincidem. Não diz quantas pessoas dividiram o voto (para isso, veja a estimativa de voto dividido).</p>
    <p>No mapa, municípios divergentes aparecem com a cor do campo que venceu no cargo escolhido; os que concordam ficam apagados.</p>`,
  "comparacao-2022": html`
    <p>A comparação é <b>1º turno × 1º turno</b>: em cada município, vemos quem teve mais votos entre Lula e o adversário (Jair Bolsonaro em 2022, Flávio Bolsonaro em 2026). Uma <b>virada</b> é um município em que esse vencedor mudou de lado entre as duas eleições. Empates ficam fora da contagem.</p>
    <p>A comparação usa os mesmos critérios de campo nas duas eleições (classificação de 2022 em <a href="#metodo">Método</a>). Os municípios são casados pelo código do IBGE.</p>`,
  "cenarios-2-turno": html`
    <p>No 2º turno ficam só dois candidatos. Os votos de quem foi eliminado podem ir para um deles, virar branco/nulo ou abstenção. Calculamos <b>quanto cada um precisa</b> desses votos para passar de 50%, supondo que os eleitores dos dois finalistas repitam o voto.</p>
    <p>Os <b>cenários</b> mostram resultados possíveis sob hipóteses explícitas (por exemplo, eliminados se dividindo como em 2022). As pesquisas são de institutos registrados no TSE, com link. Nada aqui é previsão.</p>`,
  "brancos-nulos": html`
    <p><b>Branco</b> e <b>nulo</b> não contam para nenhum candidato: só os votos válidos entram na conta do resultado. Ao contrário de um mito comum, muitos votos nulos não anulam a eleição.</p>
    <p>A porcentagem usa como base os votos possíveis: o comparecimento, e no <b>Senado</b> o dobro dele, porque cada eleitor teve 2 votos.</p>`,
  fragmentacao: html`
    <p>O <b>número efetivo de partidos</b> (índice de Laakso-Taagepera) mede quantos partidos "de verdade" dividem as cadeiras, pesando cada um pelo tamanho. Se 2 partidos tivessem metade cada, o índice seria 2; muitos partidos pequenos fazem o índice subir.</p>
    <p>O <b>centro</b> aqui é o grupo de partidos sem lado declarado no 2º turno.</p>`,
  legenda: html`
    <p>Para deputado, o eleitor pode votar no número de um candidato (voto nominal) ou só no número do partido (<b>voto de legenda</b>). Os dois contam para o partido ou federação na divisão das vagas.</p>
    <p>A porcentagem mostra a parte dos votos de cada campo que foi só para a legenda.</p>`,
  puxadores: html`
    <p>Um candidato muito votado pode eleger colegas: os votos dele contam para o partido, e cada <b>quociente eleitoral</b> atingido vale uma vaga. Quem passa muito do quociente "puxa" outros nomes da lista.</p>
    <p>Desde 2015, cada eleito precisa de ao menos 10% do quociente em votos nominais, o que limita o efeito. O número de puxados é uma <b>estimativa</b>: as sobras e as federações mudam a conta.</p>`,
};

export const METODO = html`
  <p>Os números vêm dos arquivos públicos de divulgação do ${TSE}. Contagens (votos, cadeiras, municípios) são oficiais; tudo que tem o selo <span class="badge">estimativa</span> é cálculo nosso, com método e faixa de incerteza.</p>
  <p>A classificação dos partidos em campos segue o apoio declarado no 2º turno presidencial, com prova (nota oficial, coligação registrada, declaração pública de dirigente ou imprensa reconhecida). Declaração de diretório estadual vale só para aquele estado. Partido sem declaração com prova fica no centro.</p>`;
