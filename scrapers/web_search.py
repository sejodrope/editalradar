"""
Scraper de editais via busca web — queries cirúrgicas para a Bruna.

Foco exclusivo em:
- Termos de referência, manifestações de interesse, contratação de consultor individual
- Temas: povos e comunidades tradicionais, sociobiodiversidade, bioeconomia,
  CLPI, restauração da vegetação, facilitação/moderação participativa,
  sistematização, análise qualitativa, entrevistas semiestruturadas

NÃO busca: programas de extensão universitária, bolsas de pós-graduação,
vagas de emprego CLT, fornecimento de materiais/equipamentos.
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

MAX_RESULTS_POR_QUERY = 8   # reduzido: qualidade > quantidade
PAUSA_ENTRE_QUERIES = 1.5
MAX_QUERIES_POR_PERFIL = 14  # menos queries, mas mais cirúrgicas

# Termos que PRECISAM estar no conteúdo para considerar relevante
_TERMOS_DOCUMENTO = {
    "termo de referência", "tdr", "manifestação de interesse",
    "contratação", "consultoria", "consultor", "chamada", "edital",
    "seleção", "proposta", "candidatura",
}

# Termos que IMEDIATAMENTE descartam o resultado
_TERMOS_EXCLUIR = {
    "extensão universitária", "programa de extensão", "pós-graduação",
    "mestrado", "doutorado", "vagas de emprego", "concurso público",
    "clt", "carteira assinada", "pregão eletrônico para aquisição",
    "licitação de materiais", "fornecimento de equipamentos",
}

_DOMINIOS_BLOQUEADOS = {
    "youtube.com", "facebook.com", "twitter.com", "instagram.com",
    "linkedin.com", "wikipedia.org", "reddit.com", "stackoverflow.com",
    "amazon.com", "mercadolivre.com", "indeed.com", "catho.com",
}

# Portais onde as oportunidades da Bruna realmente aparecem
_PORTAIS = [
    ("funbio.org.br",       "Funbio"),
    ("cepf.net",            "CEPF"),
    ("ipe.org.br",          "IPÊ"),
    ("imazon.org.br",       "Imazon"),
    ("socioambiental.org",  "ISA"),
    ("iis-rio.org",         "IIS"),
    ("imaflora.org",        "Imaflora"),
    ("ispn.org.br",         "ISPN"),
    ("aliancadaterra.org.br", "Aliança da Terra"),
    ("wwf.org.br",          "WWF"),
    ("ci.org.br",           "Conservation International"),
    ("icmbio.gov.br",       "ICMBio"),
    ("mma.gov.br",          "MMA"),
]


def _gerar_queries(perfil: Perfil) -> list[str]:
    """
    Queries cirúrgicas focadas nos instrumentos exatos que a Bruna executa.
    Menos queries, mais precisas = menos triagem, menos custo.
    """
    ano = datetime.now().year
    excluir = '-"extensão universitária" -"pós-graduação" -"concurso público"'
    queries = []

    # ── Grupo 1: Portais especializados (mais qualidade) ──────────────────
    for dominio, _ in _PORTAIS[:6]:
        queries.append(f'site:{dominio} "termo de referência" OR "manifestação de interesse" {ano}')

    # ── Grupo 2: Documentos específicos por tema ──────────────────────────
    temas_queries = [
        f'"termo de referência" "comunidades tradicionais" consultoria {ano} {excluir}',
        f'"manifestação de interesse" sociobiodiversidade bioeconomia {ano}',
        f'"contratação consultor" "consulta prévia" OR "CLPI" OR "restauração" {ano} site:gov.br',
        f'"facilitação" OR "moderação" oficinas participativas consultoria {ano} {excluir}',
        f'"sistematização" OR "análise qualitativa" consultoria ambiental {ano} site:gov.br',
        f'PNUD GEF "consultor individual" socioambiental {ano} site:gov.br',
        f'"bioeconomia" "comunidades tradicionais" consultoria {ano}',
        f'ICMBio "plano de manejo" "manifestação de interesse" {ano}',
    ]
    queries.extend(temas_queries)

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


def _e_relevante(title: str, body: str, url: str) -> bool:
    """Filtra em 3 camadas antes de gastar com Claude."""
    texto = (title + " " + body).lower()
    url_lower = url.lower()

    # Camada 1: Descarta se tem termos de exclusão
    if any(t in texto for t in _TERMOS_EXCLUIR):
        return False

    # Camada 2: Precisa ter pelo menos um termo de documento relevante
    if not any(t in texto for t in _TERMOS_DOCUMENTO):
        return False

    # Camada 3: Descarta conteúdo com datas velhas (2020-2024)
    ano_atual = datetime.now().year
    for ano in range(2020, ano_atual - 1):
        # Checa no texto E na URL
        if re.search(rf'\b{ano}\b', texto) or f'/{ano}/' in url_lower:
            return False

    return True


def _inferir_fonte(url: str) -> str:
    d = _dominio(url).lower()
    for dominio, nome in _PORTAIS:
        if dominio in d:
            return nome
    if "gov.br" in d:
        return "Gov.br"
    return "Web"


def _normalizar(resultado: dict) -> Optional[dict]:
    url   = resultado.get("href") or resultado.get("url") or ""
    title = resultado.get("title") or ""
    body  = resultado.get("body") or ""

    if not _url_valida(url):
        return None
    if not _e_relevante(title, body, url):
        return None

    titulo = (title or body[:200]).strip()[:500]
    if not titulo:
        return None

    return {
        "titulo": titulo,
        "descricao_curta": body[:800] if body else None,
        "fonte": _inferir_fonte(url),
        "url_original": url[:2000],
        "orgao_publicador": _dominio(url)[:300],
    }


def buscar_e_salvar_web(db: Session, perfil: Perfil) -> list[Edital]:
    """Busca com queries cirúrgicas — qualidade > volume."""
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

    queries = _gerar_queries(perfil)
    logger.info("WebSearch: %s queries cirúrgicas para '%s'", len(queries), perfil.nome)

    novos: list[Edital] = []
    urls_vistas: set[str] = set()

    try:
        with DDGS() as ddgs:
            for i, query in enumerate(queries):
                try:
                    res = ddgs.text(query, max_results=MAX_RESULTS_POR_QUERY)
                except Exception as exc:
                    logger.warning("WebSearch query erro: %s", exc)
                    time.sleep(PAUSA_ENTRE_QUERIES * 2)
                    continue

                para_salvar = []
                for r in (res or []):
                    campos = _normalizar(r)
                    if campos is None:
                        continue
                    url = campos["url_original"]
                    if url in urls_vistas or crud.edital_existe_por_url(db, url, perfil.id):
                        continue
                    urls_vistas.add(url)
                    para_salvar.append(campos)

                if para_salvar:
                    logger.info("Query %s/%s: %s resultados válidos", i+1, len(queries), len(para_salvar))
                    for campos in para_salvar:
                        try:
                            edital = crud.criar_edital(db, perfil_id=perfil.id, **campos)
                            novos.append(edital)
                        except Exception as exc:
                            logger.error("Salvar erro: %s", exc)

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

    resultado = {"pncp": 0, "web": 0, "claude_search": 0}

    if incluir_pncp:
        try:
            resultado["pncp"] = len(buscar_e_salvar_pncp(db, perfil, dias_retroativos=dias_retroativos_pncp))
        except Exception as exc:
            logger.error("Erro PNCP: %s", exc)

    if incluir_web:
        try:
            resultado["web"] = len(buscar_e_salvar_web(db, perfil))
        except Exception as exc:
            logger.error("Erro web: %s", exc)

    crud.atualizar_config_busca(db, perfil.id, ultima_busca_em=datetime.now())
    logger.info("Busca completa '%s': %s", perfil.nome, resultado)
    return resultado
