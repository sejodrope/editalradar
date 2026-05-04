"""
Scraper de editais via busca web (ddgs / duckduckgo_search).
Queries focadas em oportunidades para consultora ambiental solo/MEI.
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
MAX_QUERIES_POR_PERFIL = 14

# Termos obrigatórios no resultado para considerar como edital
_TERMOS_EDITAL = {
    "edital", "chamada", "fomento", "licitação", "concurso", "seleção",
    "convocação", "pregão", "inscrição", "bolsa", "financiamento",
    "subvenção", "grant", "proposta", "candidatura", "parceria",
    "contratação", "assessoria", "consultoria",
}

# Domínios que nunca são editais
_DOMINIOS_BLOQUEADOS = {
    "youtube.com", "facebook.com", "twitter.com", "instagram.com",
    "linkedin.com", "wikipedia.org", "reddit.com",
    "microsoft.com", "answers.microsoft.com", "support.microsoft.com",
    "stackoverflow.com", "github.com", "medium.com",
    "soundcloud.com", "spotify.com", "apple.com",
    "amazon.com", "mercadolivre.com",
}

# Fontes prioritárias para consultora ambiental
_DOMINIOS_PRIORITARIOS = {
    "gov.br", "org.br",
    "bndes.gov.br", "finep.gov.br", "mma.gov.br", "mcti.gov.br",
    "cnpq.br", "capes.gov.br", "funbio.org.br", "wwf.org.br",
    "iis-rio.org", "ipe.org.br", "imazon.org.br", "inpa.br",
    "amazonia.org.br", "socioambiental.org", "imaflora.org",
    "fapeam.am.gov.br", "fapesp.br", "fapemig.br",
    "pncp.gov.br", "compras.gov.br",
}


# ---------------------------------------------------------------------------
# Geração de queries — focadas em solo / consultoria ambiental
# ---------------------------------------------------------------------------

def _gerar_queries(perfil: Perfil) -> list[str]:
    """
    Gera queries específicas para oportunidades de consultora ambiental solo.
    Prioriza: consultorias individuais, parcerias, ONGs, fomento, elaboração de planos.
    Evita: obras, pregões de material, grandes licitações.
    """
    ano = datetime.now().year
    palavras = perfil.palavras_chave or []
    fontes = perfil.fontes_priorizadas or []
    queries: list[str] = []

    for kw in palavras:
        # Alta precisão: gov.br + keyword + termos de consultoria individual
        queries.append(f'consultoria "{kw}" pessoa física edital {ano} site:gov.br')
        queries.append(f'chamada pública "{kw}" fomento individual {ano}')

        # Parcerias e ONGs — muito relevante para consultora solo
        queries.append(f'"{kw}" parceria ONG consultoria ambiental edital {ano}')
        queries.append(f'"{kw}" chamada projetos fundação {ano}')

        # Elaboração de planos técnicos — trabalho típico de consultora
        queries.append(f'"{kw}" elaboração plano técnico chamada {ano} site:gov.br')

        # Por fonte específica
        for fonte in fontes:
            if fonte == "BNDES":
                queries.append(f'"{kw}" BNDES chamada consultoria {ano}')
            elif fonte == "FINEP":
                queries.append(f'"{kw}" FINEP chamada pesquisador {ano}')
            elif fonte == "MMA":
                queries.append(f'"{kw}" MMA chamada ambiental {ano}')
            elif fonte == "MCTI":
                queries.append(f'"{kw}" MCTI pesquisa ambiental edital {ano}')

        if len(queries) >= MAX_QUERIES_POR_PERFIL:
            break

    # Queries gerais para capturar oportunidades da área sem keyword específica
    area = perfil.area_atuacao or "ambiental"
    queries.append(f'consultoria {area} MEI chamada pública {ano}')
    queries.append(f'edital assessoria técnica {area} pessoa física {ano}')

    return queries[:MAX_QUERIES_POR_PERFIL]


# ---------------------------------------------------------------------------
# Validação e normalização
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
    texto = (title + " " + body).lower()
    return any(termo in texto for termo in _TERMOS_EDITAL)


def _inferir_fonte(url: str) -> str:
    d = _dominio(url).lower()
    mapa = {
        "bndes.gov.br": "BNDES", "finep.gov.br": "FINEP",
        "mma.gov.br": "MMA", "mcti.gov.br": "MCTI",
        "pncp.gov.br": "PNCP", "compras.gov.br": "ComprasGov",
        "cnpq.br": "CNPq", "capes.gov.br": "CAPES",
        "funbio.org.br": "Funbio", "wwf.org.br": "WWF",
        "iis-rio.org": "IIS", "ipe.org.br": "IPÊ",
        "imazon.org.br": "Imazon", "imaflora.org": "Imaflora",
        "socioambiental.org": "ISA", "fapeam.am.gov.br": "FAPEAM",
        "gov.br": "Gov.br",
    }
    for sufixo, nome in mapa.items():
        if sufixo in d:
            return nome
    return "DuckDuckGo"


def _e_fonte_prioritaria(url: str) -> bool:
    d = _dominio(url).lower()
    return any(p in d for p in _DOMINIOS_PRIORITARIOS)


def _normalizar_resultado(resultado: dict) -> Optional[dict]:
    url   = resultado.get("href") or resultado.get("url") or ""
    title = resultado.get("title") or ""
    body  = resultado.get("body") or ""

    if not _url_valida(url):
        return None
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
    """Busca oportunidades focadas em consultoria ambiental solo via ddgs."""
    DDGS = None
    for pkg, cls in [("ddgs", "DDGS"), ("duckduckgo_search", "DDGS")]:
        try:
            mod = __import__(pkg)
            DDGS = getattr(mod, cls)
            break
        except (ImportError, AttributeError):
            continue

    if DDGS is None:
        logger.error("Instale: pip install ddgs")
        return []

    if not perfil.palavras_chave:
        return []

    queries = _gerar_queries(perfil)
    logger.info("WebSearch: %s queries para '%s'", len(queries), perfil.nome)

    novos: list[Edital] = []
    urls_vistas: set[str] = set()
    # Fontes prioritárias primeiro para não perder em rate limit
    resultados_buffer: list[dict] = []

    try:
        with DDGS() as ddgs:
            for i, query in enumerate(queries):
                try:
                    res = ddgs.text(query, max_results=MAX_RESULTS_POR_QUERY)
                except Exception as exc:
                    logger.warning("WebSearch erro query '%s': %s", query, exc)
                    time.sleep(PAUSA_ENTRE_QUERIES * 2)
                    continue

                for r in (res or []):
                    campos = _normalizar_resultado(r)
                    if campos:
                        resultados_buffer.append(campos)

                time.sleep(PAUSA_ENTRE_QUERIES)
    except Exception as exc:
        logger.error("WebSearch erro geral: %s", exc)

    # Ordena: fontes prioritárias primeiro
    resultados_buffer.sort(key=lambda r: 0 if _e_fonte_prioritaria(r["url_original"]) else 1)

    for campos in resultados_buffer:
        url = campos["url_original"]
        if url in urls_vistas or crud.edital_existe_por_url(db, url, perfil.id):
            continue
        urls_vistas.add(url)
        try:
            edital = crud.criar_edital(db, perfil_id=perfil.id, **campos)
            novos.append(edital)
            logger.info("WebSearch: id=%s '%s'", edital.id, edital.titulo[:60])
        except Exception as exc:
            logger.error("WebSearch salvar erro: %s", exc)

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
    from scrapers.pncp import buscar_e_salvar_pncp

    resultado = {"pncp": 0, "web": 0}

    if incluir_pncp:
        try:
            resultado["pncp"] = len(buscar_e_salvar_pncp(db, perfil, dias_retroativos=dias_retroativos_pncp))
        except Exception as exc:
            logger.error("Erro PNCP '%s': %s", perfil.nome, exc)

    if incluir_web:
        try:
            resultado["web"] = len(buscar_e_salvar_web(db, perfil))
        except Exception as exc:
            logger.error("Erro web '%s': %s", perfil.nome, exc)

    crud.atualizar_config_busca(db, perfil.id, ultima_busca_em=datetime.now())
    logger.info("Busca completa '%s': pncp=%s web=%s", perfil.nome, resultado["pncp"], resultado["web"])
    return resultado
