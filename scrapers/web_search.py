"""
Scraper de editais via busca web usando DuckDuckGo (duckduckgo_search).
Gera queries combinando palavras-chave do perfil com termos de edital.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy.orm import Session

import crud
from models import Edital, Perfil

logger = logging.getLogger(__name__)

MAX_RESULTS_POR_QUERY = 10
PAUSA_ENTRE_QUERIES = 1.5   # DuckDuckGo rejeita rafagas rápidas
MAX_QUERIES_POR_PERFIL = 15  # teto para não sobrecarregar


# ---------------------------------------------------------------------------
# Geração de queries
# ---------------------------------------------------------------------------

def _gerar_queries(perfil: Perfil) -> list[str]:
    """
    Gera lista de queries de busca para o perfil combinando palavras-chave
    com termos típicos de editais e chamadas públicas brasileiras.
    """
    ano = datetime.utcnow().year
    palavras = perfil.palavras_chave or []
    fontes = perfil.fontes_priorizadas or []
    queries: list[str] = []

    templates_gerais = [
        'edital "{kw}" {ano} site:gov.br',
        'chamada pública "{kw}" fomento {ano}',
        'pregão "{kw}" {ano}',
        '"{kw}" edital inscrições abertas',
    ]

    templates_fontes = {
        "BNDES": ['"{kw}" BNDES fomento chamada {ano}'],
        "MMA": ['"{kw}" MMA ministério meio ambiente edital {ano}'],
        "FINEP": ['"{kw}" FINEP chamada pública {ano}'],
        "PNCP": ['"{kw}" PNCP contratação pública {ano}'],
        "MCTI": ['"{kw}" MCTI edital pesquisa {ano}'],
    }

    for kw in palavras:
        for tmpl in templates_gerais:
            queries.append(tmpl.format(kw=kw, ano=ano))

        for fonte in fontes:
            for tmpl in templates_fontes.get(fonte, []):
                queries.append(tmpl.format(kw=kw, ano=ano))

        if len(queries) >= MAX_QUERIES_POR_PERFIL:
            break

    return queries[:MAX_QUERIES_POR_PERFIL]


# ---------------------------------------------------------------------------
# Normalização de resultados do DDG
# ---------------------------------------------------------------------------

_DOMINIOS_BLOQUEADOS = {
    "youtube.com", "facebook.com", "twitter.com", "instagram.com",
    "linkedin.com", "wikipedia.org", "reddit.com",
}


def _dominio(url: str) -> str:
    """Extrai o domínio de uma URL, removendo o prefixo 'www.' se presente."""
    try:
        netloc = urlparse(url).netloc
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:
        return ""


def _url_valida(url: str) -> bool:
    """Descarta URLs de redes sociais, wikipedia e similares."""
    if not url:
        return False
    dominio = _dominio(url)
    return not any(bloqueado in dominio for bloqueado in _DOMINIOS_BLOQUEADOS)


def _titulo_da_descricao(title: str, body: str) -> str:
    """Usa o título do resultado DDG; se vazio, usa os primeiros 200 chars do body."""
    titulo = (title or "").strip()
    if titulo:
        return titulo[:500]
    return (body or "").strip()[:500]


def _inferir_fonte(url: str) -> str:
    """Infere o nome da fonte a partir do domínio da URL."""
    dominio = _dominio(url).lower()
    mapeamento = {
        "bndes.gov.br": "BNDES",
        "finep.gov.br": "FINEP",
        "mma.gov.br": "MMA",
        "mcti.gov.br": "MCTI",
        "pncp.gov.br": "PNCP",
        "compras.gov.br": "ComprasGov",
        "gov.br": "Gov.br",
    }
    for sufixo, nome in mapeamento.items():
        if sufixo in dominio:
            return nome
    return "DuckDuckGo"


def _normalizar_resultado(resultado: dict) -> Optional[dict]:
    """
    Converte um resultado bruto do DDG para dict compatível com crud.criar_edital.
    Retorna None se o resultado não tiver URL ou título útil.
    """
    url = resultado.get("href") or resultado.get("url") or ""
    title = resultado.get("title") or ""
    body = resultado.get("body") or ""

    if not _url_valida(url):
        return None

    titulo = _titulo_da_descricao(title, body)
    if not titulo:
        return None

    return {
        "titulo": titulo,
        "descricao_curta": body[:1000] if body else None,
        "fonte": _inferir_fonte(url),
        "url_original": url[:2000],
        "orgao_publicador": _dominio(url)[:300],
    }


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def buscar_e_salvar_web(
    db: Session,
    perfil: Perfil,
) -> list[Edital]:
    """
    Executa buscas no DuckDuckGo usando queries geradas a partir do perfil
    e persiste editais novos no banco.

    A biblioteca duckduckgo_search é importada dentro da função para que
    a ausência do pacote não impeça a importação do módulo.

    Args:
        db:     Session do SQLAlchemy
        perfil: Perfil de busca com palavras_chave populadas

    Returns:
        Lista de Edital objetos recém-criados.
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        logger.error("duckduckgo_search não instalado. Execute: pip install duckduckgo-search")
        return []

    if not perfil.palavras_chave:
        logger.info("WebSearch: perfil '%s' sem palavras-chave, pulando.", perfil.nome)
        return []

    queries = _gerar_queries(perfil)
    logger.info(
        "WebSearch: %s queries geradas para perfil '%s'",
        len(queries), perfil.nome,
    )

    novos: list[Edital] = []
    urls_vistas: set[str] = set()

    with DDGS() as ddgs:
        for i, query in enumerate(queries):
            logger.debug("WebSearch: query %s/%s — %s", i + 1, len(queries), query)

            try:
                resultados = ddgs.text(query, max_results=MAX_RESULTS_POR_QUERY)
            except Exception as exc:
                logger.warning("WebSearch: erro na query '%s': %s", query, exc)
                time.sleep(PAUSA_ENTRE_QUERIES * 2)
                continue

            if not resultados:
                time.sleep(PAUSA_ENTRE_QUERIES)
                continue

            for resultado in resultados:
                campos = _normalizar_resultado(resultado)
                if campos is None:
                    continue

                url = campos["url_original"]

                if url in urls_vistas:
                    continue
                if crud.edital_existe_por_url(db, url, perfil.id):
                    continue

                urls_vistas.add(url)

                try:
                    edital = crud.criar_edital(db, perfil_id=perfil.id, **campos)
                    novos.append(edital)
                    logger.info(
                        "WebSearch: novo edital id=%s '%s'",
                        edital.id, edital.titulo[:60],
                    )
                except Exception as exc:
                    logger.error(
                        "WebSearch: erro ao salvar '%s': %s",
                        campos.get("titulo", ""), exc,
                    )

            time.sleep(PAUSA_ENTRE_QUERIES)

    logger.info(
        "WebSearch: busca concluída para '%s' — %s novo(s) edital(is)",
        perfil.nome, len(novos),
    )
    return novos


# ---------------------------------------------------------------------------
# Orquestrador: roda PNCP + Web para um perfil
# ---------------------------------------------------------------------------

def executar_busca_completa(
    db: Session,
    perfil: Perfil,
    incluir_pncp: bool = True,
    incluir_web: bool = True,
    dias_retroativos_pncp: int = 30,
) -> dict[str, int]:
    """
    Executa busca em todas as fontes configuradas para o perfil e atualiza
    o timestamp da última busca na ConfiguracaoBusca.

    Args:
        db:                    Session ativa
        perfil:                Perfil a ser buscado
        incluir_pncp:          Se True, busca na API do PNCP
        incluir_web:           Se True, busca via DuckDuckGo
        dias_retroativos_pncp: Janela de datas para a API PNCP

    Returns:
        Dict com contagem de novos editais por fonte, ex: {"pncp": 3, "web": 7}
    """
    from scrapers.pncp import buscar_e_salvar_pncp

    resultado = {"pncp": 0, "web": 0}

    if incluir_pncp and "PNCP" in (perfil.fontes_priorizadas or []) or incluir_pncp:
        try:
            novos_pncp = buscar_e_salvar_pncp(db, perfil, dias_retroativos=dias_retroativos_pncp)
            resultado["pncp"] = len(novos_pncp)
        except Exception as exc:
            logger.error("Erro na busca PNCP para perfil '%s': %s", perfil.nome, exc)

    if incluir_web:
        try:
            novos_web = buscar_e_salvar_web(db, perfil)
            resultado["web"] = len(novos_web)
        except Exception as exc:
            logger.error("Erro na busca web para perfil '%s': %s", perfil.nome, exc)

    # Registra timestamp da busca
    crud.atualizar_config_busca(db, perfil.id, ultima_busca_em=datetime.utcnow())

    total = resultado["pncp"] + resultado["web"]
    logger.info(
        "Busca completa '%s': pncp=%s web=%s total=%s",
        perfil.nome, resultado["pncp"], resultado["web"], total,
    )
    return resultado
