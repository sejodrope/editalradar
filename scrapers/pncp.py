"""
Scraper para o PNCP (Portal Nacional de Contratações Públicas).

NOTA: A API REST pública /v1/contratacoes/publicacoes foi descontinuada pelo PNCP.
O módulo mantém a estrutura para quando a API for restabelecida ou migrada,
mas retorna resultados vazios sem erro para não quebrar o fluxo de busca.
O Claude Search (scrapers/claude_search.py) cobre o PNCP via busca web.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import requests
from sqlalchemy.orm import Session

import crud
from models import Edital, Perfil

logger = logging.getLogger(__name__)

BASE_URL = "https://pncp.gov.br/api/pncp/v1"
MAX_PAGINAS = 5
ITENS_POR_PAGINA = 50
TIMEOUT_SEGUNDOS = 15
PAUSA_ENTRE_PAGINAS = 0.5  # respeita rate limit da API


# ---------------------------------------------------------------------------
# Funções de baixo nível — chamadas HTTP
# ---------------------------------------------------------------------------

def _get(endpoint: str, params: dict) -> Optional[dict]:
    """
    Executa GET na API do PNCP e retorna o JSON ou None em caso de erro.
    Trata timeout, erros HTTP e JSON inválido sem propagar exceção.
    """
    url = f"{BASE_URL}{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT_SEGUNDOS)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        logger.warning("PNCP timeout em %s params=%s", url, params)
    except requests.exceptions.HTTPError as exc:
        logger.warning("PNCP HTTP %s em %s", exc.response.status_code, url)
    except requests.exceptions.RequestException as exc:
        logger.warning("PNCP erro de rede em %s: %s", url, exc)
    except ValueError:
        logger.warning("PNCP resposta não é JSON válido: %s", url)
    return None


def buscar_publicacoes(
    data_inicial: str,
    data_final: str,
    pagina: int = 1,
    codigo_modalidade: Optional[int] = None,
) -> Optional[dict]:
    """
    Chama /contratacoes/publicacoes e retorna o payload bruto ou None.

    Args:
        data_inicial: formato YYYYMMDD
        data_final:   formato YYYYMMDD
        pagina:       número da página (começa em 1)
        codigo_modalidade: código da modalidade (ex: 6 = Pregão Eletrônico); None = todas
    """
    params: dict = {
        "dataInicial": data_inicial,
        "dataFinal": data_final,
        "pagina": pagina,
        "tamanhoPagina": ITENS_POR_PAGINA,
    }
    if codigo_modalidade is not None:
        params["codigoModalidadeContratacao"] = codigo_modalidade

    return _get("/contratacoes/publicacoes", params)


# ---------------------------------------------------------------------------
# Parsing de registros PNCP → dict normalizado
# ---------------------------------------------------------------------------

def _parse_data(valor: Optional[str]) -> Optional[datetime]:
    """Converte string de data do PNCP (ISO 8601) para datetime ou None."""
    if not valor:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(valor[:19], fmt)
        except ValueError:
            continue
    return None


def _extrair_campos(item: dict) -> dict:
    """
    Mapeia um registro bruto da API PNCP para os campos do modelo Edital.
    Campos ausentes resultam em None sem lançar exceção.
    """
    orgao = item.get("orgaoEntidade") or {}
    unidade = item.get("unidadeOrgao") or {}

    titulo = item.get("objetoCompra") or item.get("objeto") or ""
    orgao_nome = (
        unidade.get("nomeUnidade")
        or orgao.get("razaoSocial")
        or ""
    )

    # Monta URL canônica do PNCP para o edital
    cnpj = orgao.get("cnpj", "")
    ano = item.get("anoCompra") or item.get("ano") or ""
    seq = item.get("sequencialCompra") or item.get("sequencial") or ""
    url = (
        item.get("linkSistemaOrigem")
        or (f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}" if cnpj and ano and seq else "")
    )

    return {
        "titulo": titulo[:500],
        "descricao_completa": titulo,
        "orgao_publicador": orgao_nome[:300],
        "fonte": "PNCP",
        "url_original": url[:2000],
        "data_publicacao": _parse_data(item.get("dataPublicacaoPncp")),
        "data_abertura": _parse_data(item.get("dataAberturaProposta")),
        "data_encerramento": _parse_data(item.get("dataEncerramentoProposta")),
        "valor_total": item.get("valorTotalEstimado"),
        "modalidade": item.get("modalidadeNome") or "",
    }


# ---------------------------------------------------------------------------
# Lógica de relevância por palavras-chave
# ---------------------------------------------------------------------------

def _e_relevante(item: dict, palavras_chave: list[str]) -> bool:
    """
    Retorna True se alguma palavra-chave do perfil aparecer no texto do edital.
    Busca case-insensitive nos campos objeto, descrição e órgão.
    """
    campos_texto = " ".join(filter(None, [
        item.get("objetoCompra", ""),
        item.get("objeto", ""),
        item.get("informacaoComplementar", ""),
        (item.get("orgaoEntidade") or {}).get("razaoSocial", ""),
        (item.get("unidadeOrgao") or {}).get("nomeUnidade", ""),
    ])).lower()

    return any(kw.lower() in campos_texto for kw in palavras_chave)


# ---------------------------------------------------------------------------
# Função principal: busca e salva no banco
# ---------------------------------------------------------------------------

def buscar_e_salvar_pncp(
    db: Session,
    perfil: Perfil,
    dias_retroativos: int = 30,
) -> list[Edital]:
    """
    Busca publicações do PNCP dos últimos `dias_retroativos` dias,
    filtra pelas palavras-chave do perfil e persiste editais novos no banco.

    Args:
        db:              Session do SQLAlchemy
        perfil:          Perfil de busca com palavras_chave populadas
        dias_retroativos: Quantos dias atrás iniciar a busca (padrão 30)

    Returns:
        Lista de Edital objetos recém-criados (apenas os novos, sem duplicatas).
    """
    if not perfil.palavras_chave:
        logger.info("PNCP: perfil '%s' sem palavras-chave, pulando.", perfil.nome)
        return []

    hoje = datetime.now()
    # API PNCP usa formato YYYYMMDD (sem traços)
    data_inicial = (hoje - timedelta(days=dias_retroativos)).strftime("%Y%m%d")
    data_final = hoje.strftime("%Y%m%d")

    logger.info(
        "PNCP: API pública descontinuada — buscas cobertas pelo Claude Search | perfil '%s'",
        perfil.nome,
    )
    return []  # API descontinuada; Claude Search cobre via web

    logger.info(  # noqa: unreachable — mantido para referência futura
        "PNCP: iniciando busca para perfil '%s' | %s → %s",
        perfil.nome, data_inicial, data_final,
    )

    novos: list[Edital] = []
    vistos_urls: set[str] = set()  # deduplicação dentro da sessão de busca

    for pagina in range(1, MAX_PAGINAS + 1):
        payload = buscar_publicacoes(data_inicial, data_final, pagina=pagina)

        if payload is None:
            logger.warning("PNCP: falha ao buscar página %s, abortando.", pagina)
            break

        # A API pode retornar lista direta ou wrapper com 'data'/'items'
        if isinstance(payload, list):
            items = payload
            total_paginas = 1
        else:
            items = payload.get("data") or payload.get("items") or []
            total_paginas = payload.get("totalPaginas") or payload.get("totalPages") or 1

        if not items:
            logger.debug("PNCP: página %s sem resultados, encerrando.", pagina)
            break

        for item in items:
            if not _e_relevante(item, perfil.palavras_chave):
                continue

            campos = _extrair_campos(item)
            url = campos.get("url_original", "")

            # Pula se URL já vista nesta sessão ou já existe no banco
            if url and url in vistos_urls:
                continue
            if url and crud.edital_existe_por_url(db, url, perfil.id):
                continue

            if url:
                vistos_urls.add(url)

            try:
                edital = crud.criar_edital(
                    db,
                    perfil_id=perfil.id,
                    **campos,
                )
                novos.append(edital)
                logger.info("PNCP: novo edital salvo id=%s '%s'", edital.id, edital.titulo[:60])
            except Exception as exc:
                logger.error("PNCP: erro ao salvar edital '%s': %s", campos.get("titulo", ""), exc)

        if pagina >= total_paginas:
            break

        time.sleep(PAUSA_ENTRE_PAGINAS)

    logger.info(
        "PNCP: busca concluída para '%s' — %s novo(s) edital(is)",
        perfil.nome, len(novos),
    )
    return novos
