"""
Scraper de editais via busca web (ddgs / duckduckgo_search).
Queries focadas em oportunidades ABERTAS para consultora ambiental solo/MEI.
"""

from __future__ import annotations

import logging
import re
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
MAX_QUERIES_POR_PERFIL = 20

_TERMOS_EDITAL = {
    "edital", "chamada", "fomento", "licitação", "concurso", "seleção",
    "convocação", "pregão", "inscrição", "bolsa", "financiamento",
    "subvenção", "grant", "proposta", "candidatura", "parceria",
    "contratação", "assessoria", "consultoria", "termo de referência", "tdr",
}

_DOMINIOS_BLOQUEADOS = {
    "youtube.com", "facebook.com", "twitter.com", "instagram.com",
    "linkedin.com", "wikipedia.org", "reddit.com",
    "microsoft.com", "stackoverflow.com", "github.com",
    "amazon.com", "mercadolivre.com",
}

# Portais prioritários onde as oportunidades da Bruna realmente aparecem
_PORTAIS_ALTA_PRIORIDADE = [
    # ONGs ambientais
    ("funbio.org.br",       "Funbio"),
    ("cepf.net",            "CEPF"),
    ("wwf.org.br",          "WWF"),
    ("ipe.org.br",          "IPÊ"),
    ("iis-rio.org",         "IIS"),
    ("imazon.org.br",       "Imazon"),
    ("imaflora.org",        "Imaflora"),
    ("socioambiental.org",  "ISA"),
    ("ci.org.br",           "Conservation International"),
    ("aliancadaterra.org.br","Aliança da Terra"),
    ("ispn.org.br",         "ISPN"),
    # Governamentais
    ("icmbio.gov.br",       "ICMBio"),
    ("mma.gov.br",          "MMA"),
    ("funai.gov.br",        "FUNAI"),
]


def _gerar_queries(perfil: Perfil) -> list[str]:
    """Gera queries variadas cobrindo todas as especialidades da Bruna."""
    ano = datetime.now().year
    palavras = perfil.palavras_chave or []
    queries: list[str] = []

    # ── 1. Portais especializados (maior qualidade) ────────────────────────
    for dominio, _ in _PORTAIS_ALTA_PRIORIDADE[:8]:
        queries.append(f"site:{dominio} chamada consultoria {ano}")

    # ── 2. Queries por especialidades-chave da Bruna ──────────────────────
    especialidades_core = [
        ("plano de manejo",              f'"plano de manejo" consultoria "inscrições abertas" {ano}'),
        ("facilitação participativa",    f'"facilitação participativa" chamada consultoria {ano} site:gov.br'),
        ("programa de comunicação social", f'"programa de comunicação social" consultoria "pessoa física" {ano}'),
        ("diagnóstico socioeconômico",   f'"diagnóstico socioeconômico" consultoria edital {ano}'),
        ("etnoconhecimento",             f'"etnoconhecimento" chamada pesquisa bolsa {ano}'),
        ("sociobiodiversidade",          f'"sociobiodiversidade" consultoria chamada {ano}'),
        ("povos e comunidades",          f'"comunidades tradicionais" consultoria edital "pessoa física" {ano}'),
    ]
    for _, query in especialidades_core:
        queries.append(query)
        if len(queries) >= MAX_QUERIES_POR_PERFIL:
            break

    # ── 3. Queries PNUD/GEF/ICMBio (projetos recorrentes onde ela trabalha) ──
    queries.append(f"PNUD MMA consultoria socioambiental edital {ano} site:gov.br")
    queries.append(f"GEF Brasil consultoria ambiental chamada {ano}")
    queries.append(f"site:icmbio.gov.br consultoria edital {ano}")

    # ── 4. Queries por fontes priorizadas do perfil ────────────────────────
    fontes = perfil.fontes_priorizadas or []
    if "BNDES" in fontes:
        queries.append(f"site:bndes.gov.br chamada consultoria socioambiental {ano}")
    if "FINEP" in fontes:
        queries.append(f"site:finep.gov.br chamada consultoria ambiental {ano}")

    # ── 5. Queries gerais com foco em abertas ────────────────────────────
    queries.append(f'consultoria socioambiental "pessoa física" edital "inscrições abertas" {ano}')
    queries.append(f'"termo de referência" consultoria ambiental {ano} site:gov.br')

    return queries[:MAX_QUERIES_POR_PERFIL]


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
    return not any(b in d for b in _DOMINIOS_BLOQUEADOS)


def _e_relevante_para_edital(title: str, body: str) -> bool:
    texto = (title + " " + body).lower()
    if not any(termo in texto for termo in _TERMOS_EDITAL):
        return False
    # Descarta conteúdo com datas claramente velhas
    ano_atual = datetime.now().year
    for ano in range(2020, ano_atual - 1):  # 2020..ano-2
        if re.search(rf'\b{ano}\b', texto):
            return False
    return True


def _inferir_fonte(url: str) -> str:
    d = _dominio(url).lower()
    for dominio, nome in _PORTAIS_ALTA_PRIORIDADE:
        if dominio in d:
            return nome
    if "gov.br" in d:
        return "Gov.br"
    return "DuckDuckGo"


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


def buscar_e_salvar_web(db: Session, perfil: Perfil) -> list[Edital]:
    """Busca com queries especializadas para o perfil da Bruna."""
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

    try:
        with DDGS() as ddgs:
            for i, query in enumerate(queries):
                try:
                    res = ddgs.text(query, max_results=MAX_RESULTS_POR_QUERY)
                except Exception as exc:
                    logger.warning("WebSearch erro query '%s': %s", query[:60], exc)
                    time.sleep(PAUSA_ENTRE_QUERIES * 2)
                    continue

                for r in (res or []):
                    campos = _normalizar_resultado(r)
                    if campos is None:
                        continue
                    url = campos["url_original"]
                    if url in urls_vistas or crud.edital_existe_por_url(db, url, perfil.id):
                        continue
                    urls_vistas.add(url)
                    try:
                        edital = crud.criar_edital(db, perfil_id=perfil.id, **campos)
                        novos.append(edital)
                        logger.info("WebSearch: id=%s '%s'", edital.id, edital.titulo[:55])
                    except Exception as exc:
                        logger.error("WebSearch salvar: %s", exc)

                time.sleep(PAUSA_ENTRE_QUERIES)

    except Exception as exc:
        logger.error("WebSearch erro geral: %s", exc)

    logger.info("WebSearch: '%s' — %s novo(s)", perfil.nome, len(novos))
    return novos


def executar_busca_completa(
    db: Session,
    perfil: Perfil,
    incluir_pncp: bool = True,
    incluir_web: bool = True,
    dias_retroativos_pncp: int = 30,
) -> dict[str, int]:
    from scrapers.pncp import buscar_e_salvar_pncp
    from scrapers.claude_search import buscar_editais as claude_buscar, esta_disponivel as claude_ok

    resultado = {"pncp": 0, "web": 0, "claude_search": 0}

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
    total = sum(resultado.values())
    logger.info("Busca completa '%s': %s", perfil.nome, resultado)
    return resultado
