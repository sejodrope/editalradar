"""
Scraper de editais via busca web (ddgs / duckduckgo_search).
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
PAUSA_ENTRE_QUERIES = 1.5
MAX_QUERIES_POR_PERFIL = 10

# Termos que devem aparecer no título ou corpo para considerar relevante
_TERMOS_EDITAL = {
    "edital", "chamada", "fomento", "licitação", "concurso", "seleção",
    "convocação", "pregão", "inscrição", "bolsa", "financiamento",
    "subvenção", "grant", "proposta", "candidatura",
}

# Domínios que nunca são editais
_DOMINIOS_BLOQUEADOS = {
    "youtube.com", "facebook.com", "twitter.com", "instagram.com",
    "linkedin.com", "wikipedia.org", "reddit.com",
    "microsoft.com", "answers.microsoft.com", "support.microsoft.com",
    "stackoverflow.com", "github.com", "medium.com",
    "soundcloud.com", "spotify.com", "apple.com",
    "amazon.com", "mercadolivre.com", "shopify.com",
}

# Domínios prioritários (editais reais provavelmente vêm daqui)
_DOMINIOS_CONFIÁVEIS = {
    "gov.br", "org.br", "edu.br",
    "bndes.gov.br", "finep.gov.br", "mma.gov.br", "mcti.gov.br",
    "cnpq.br", "capes.gov.br", "fapesp.br", "fapemig.br",
    "pncp.gov.br", "compras.gov.br", "funbio.org.br",
}


# ---------------------------------------------------------------------------
# Geração de queries — apenas queries específicas e de qualidade
# ---------------------------------------------------------------------------

def _gerar_queries(perfil: Perfil) -> list[str]:
    """Gera queries focadas em editais reais, sem termos genéricos demais."""
    ano = datetime.now().year
    palavras = perfil.palavras_chave or []
    fontes = perfil.fontes_priorizadas or []
    queries: list[str] = []

    for kw in palavras:
        # Queries com domínio gov.br — alta precisão
        queries.append(f'edital "{kw}" {ano} site:gov.br')
        queries.append(f'chamada pública "{kw}" {ano} site:gov.br')

        # Queries por fonte específica
        for fonte in fontes:
            if fonte == "BNDES":
                queries.append(f'"{kw}" BNDES edital chamada {ano}')
            elif fonte == "FINEP":
                queries.append(f'"{kw}" FINEP chamada pública {ano}')
            elif fonte == "MMA":
                queries.append(f'"{kw}" "ministério meio ambiente" edital {ano}')
            elif fonte == "MCTI":
                queries.append(f'"{kw}" MCTI edital pesquisa {ano}')

        if len(queries) >= MAX_QUERIES_POR_PERFIL:
            break

    return queries[:MAX_QUERIES_POR_PERFIL]


# ---------------------------------------------------------------------------
# Validação e normalização de resultados
# ---------------------------------------------------------------------------

def _dominio(url: str) -> str:
    try:
        netloc = urlparse(url).netloc
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:
        return ""


def _url_valida(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    d = _dominio(url)
    return not any(bloqueado in d for bloqueado in _DOMINIOS_BLOQUEADOS)


def _e_relevante_para_edital(title: str, body: str) -> bool:
    """Verifica se o resultado realmente parece ser um edital/chamada pública."""
    texto = (title + " " + body).lower()
    return any(termo in texto for termo in _TERMOS_EDITAL)


def _inferir_fonte(url: str) -> str:
    d = _dominio(url).lower()
    mapa = {
        "bndes.gov.br": "BNDES", "finep.gov.br": "FINEP",
        "mma.gov.br": "MMA", "mcti.gov.br": "MCTI",
        "pncp.gov.br": "PNCP", "compras.gov.br": "ComprasGov",
        "cnpq.br": "CNPq", "capes.gov.br": "CAPES",
        "gov.br": "Gov.br",
    }
    for sufixo, nome in mapa.items():
        if sufixo in d:
            return nome
    return "DuckDuckGo"


def _normalizar_resultado(resultado: dict) -> Optional[dict]:
    url   = resultado.get("href") or resultado.get("url") or ""
    title = resultado.get("title") or ""
    body  = resultado.get("body") or ""

    if not _url_valida(url):
        return None

    # Filtra resultado que não parece edital
    if not _e_relevante_para_edital(title, body):
        return None

    titulo = (title or body[:200]).strip()[:500]
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

def buscar_e_salvar_web(db: Session, perfil: Perfil) -> list[Edital]:
    """
    Executa buscas web para o perfil usando ddgs (ex-duckduckgo_search)
    e persiste apenas resultados que parecem editais reais.
    """
    # Tenta importar ddgs (novo nome) ou duckduckgo_search (nome antigo)
    DDGS = None
    for pkg, cls in [("ddgs", "DDGS"), ("duckduckgo_search", "DDGS")]:
        try:
            mod = __import__(pkg)
            DDGS = getattr(mod, cls)
            break
        except (ImportError, AttributeError):
            continue

    if DDGS is None:
        logger.error("Instale o pacote ddgs: pip install ddgs")
        return []

    if not perfil.palavras_chave:
        return []

    queries = _gerar_queries(perfil)
    logger.info("WebSearch: %s queries para perfil '%s'", len(queries), perfil.nome)

    novos: list[Edital] = []
    urls_vistas: set[str] = set()

    try:
        with DDGS() as ddgs:
            for i, query in enumerate(queries):
                logger.debug("WebSearch query %s/%s: %s", i + 1, len(queries), query)
                try:
                    resultados = ddgs.text(query, max_results=MAX_RESULTS_POR_QUERY)
                except Exception as exc:
                    logger.warning("WebSearch erro na query '%s': %s", query, exc)
                    time.sleep(PAUSA_ENTRE_QUERIES * 2)
                    continue

                for resultado in (resultados or []):
                    campos = _normalizar_resultado(resultado)
                    if campos is None:
                        continue
                    url = campos["url_original"]
                    if url in urls_vistas or crud.edital_existe_por_url(db, url, perfil.id):
                        continue
                    urls_vistas.add(url)
                    try:
                        edital = crud.criar_edital(db, perfil_id=perfil.id, **campos)
                        novos.append(edital)
                        logger.info("WebSearch: id=%s '%s'", edital.id, edital.titulo[:60])
                    except Exception as exc:
                        logger.error("WebSearch: erro ao salvar '%s': %s", campos.get("titulo", ""), exc)

                time.sleep(PAUSA_ENTRE_QUERIES)
    except Exception as exc:
        logger.error("WebSearch: erro geral: %s", exc)

    logger.info("WebSearch: '%s' — %s novo(s)", perfil.nome, len(novos))
    return novos


# ---------------------------------------------------------------------------
# Orquestrador
# ---------------------------------------------------------------------------

def executar_busca_completa(
    db: Session,
    perfil: Perfil,
    incluir_pncp: bool = True,
    incluir_web: bool = True,
    dias_retroativos_pncp: int = 30,
) -> dict[str, int]:
    """Executa busca em todas as fontes e atualiza timestamp."""
    from scrapers.pncp import buscar_e_salvar_pncp

    resultado = {"pncp": 0, "web": 0}

    if incluir_pncp:
        try:
            novos_pncp = buscar_e_salvar_pncp(db, perfil, dias_retroativos=dias_retroativos_pncp)
            resultado["pncp"] = len(novos_pncp)
        except Exception as exc:
            logger.error("Erro PNCP para '%s': %s", perfil.nome, exc)

    if incluir_web:
        try:
            novos_web = buscar_e_salvar_web(db, perfil)
            resultado["web"] = len(novos_web)
        except Exception as exc:
            logger.error("Erro web para '%s': %s", perfil.nome, exc)

    crud.atualizar_config_busca(db, perfil.id, ultima_busca_em=datetime.now())
    logger.info("Busca completa '%s': pncp=%s web=%s", perfil.nome, resultado["pncp"], resultado["web"])
    return resultado
