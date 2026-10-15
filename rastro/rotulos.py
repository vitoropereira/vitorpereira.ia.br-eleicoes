"""Nomes humanos dos indicadores do Rastro (o nome técnico só aparece como âncora na metodologia) e o peso de destaque,
que só ordena os cartões "O que chama atenção" dentro da página e nunca aparece como número."""

ROTULOS = {
    "mei_acima_teto": "MEI acima do teto",
    "empresa_recem_aberta": "Empresa recém-aberta",
    "atividade_incompativel": "Atividade diferente do serviço",
    "socio_doador": "Sócio também doador",
    "socio_ligado": "Sócio candidato ou de mesmo sobrenome",
    "socio_nomeado": "Sócio com cargo comissionado",
    "multicampanha": "Atende muitas campanhas",
    "situacao_irregular": "Cadastro baixado, inapto ou suspenso",
    "concentracao": "Concentra o gasto",
    "endereco_compartilhado": "Endereço em comum",
    "valores_identicos": "Valores idênticos",
    "preco_fora_da_curva": "Gasto acima do comum",
    "gasto_por_voto": "Custo por voto alto",
    "transferencia_candidato": "Repasse a outro candidato",
    "pessoal_pf": "Muitas pessoas físicas pagas",
    "saque_especie": "Saque em espécie",
    "pagamento_tardio": "Pagamento tardio",
}


def rotulo(nome):
    return ROTULOS.get(nome, nome.replace("_", " ").capitalize())


def peso(nome, cfg):
    """Peso de destaque (3 alto, 2 médio, 1 baixo) de rastro/config.json; indicador sem peso fica com 1."""
    return int((cfg.get("destaque_pesos") or {}).get(nome, 1))
