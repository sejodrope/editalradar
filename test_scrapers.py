"""
Testes unitários para os scrapers (sem chamadas reais de rede).
Valida: parsing, filtragem por palavras-chave, geração de queries, normalização DDG.
"""

import sys
sys.path.insert(0, ".")

from datetime import datetime
from scrapers.pncp import _parse_data, _extrair_campos, _e_relevante
from scrapers.web_search import _gerar_queries, _normalizar_resultado, _url_valida, _inferir_fonte
from models import Perfil


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _perfil(palavras_chave=None, fontes=None):
    p = Perfil()
    p.nome = "Teste"
    p.palavras_chave = palavras_chave or []
    p.fontes_priorizadas = fontes or []
    return p


# ---------------------------------------------------------------------------
# PNCP — _parse_data
# ---------------------------------------------------------------------------

def test_parse_data():
    assert _parse_data(None) is None
    assert _parse_data("") is None
    assert _parse_data("2025-03-15T14:30:00") == datetime(2025, 3, 15, 14, 30, 0)
    assert _parse_data("2025-03-15") == datetime(2025, 3, 15, 0, 0, 0)
    assert _parse_data("invalido") is None
    print("[OK] _parse_data")


# ---------------------------------------------------------------------------
# PNCP — _extrair_campos
# ---------------------------------------------------------------------------

def test_extrair_campos():
    item = {
        "objetoCompra": "Restauração florestal na Mata Atlântica",
        "orgaoEntidade": {"cnpj": "12345678000100", "razaoSocial": "IBAMA"},
        "unidadeOrgao": {"nomeUnidade": "IBAMA SP"},
        "anoCompra": 2025,
        "sequencialCompra": 42,
        "linkSistemaOrigem": "https://pncp.gov.br/app/editais/12345678000100/2025/42",
        "dataPublicacaoPncp": "2025-01-10T00:00:00",
        "dataAberturaProposta": "2025-02-01T09:00:00",
        "dataEncerramentoProposta": "2025-03-01T18:00:00",
        "valorTotalEstimado": 5_000_000.0,
        "modalidadeNome": "Chamada Pública",
    }
    campos = _extrair_campos(item)
    assert campos["titulo"] == "Restauração florestal na Mata Atlântica"
    assert campos["orgao_publicador"] == "IBAMA SP"
    assert campos["fonte"] == "PNCP"
    assert "pncp.gov.br" in campos["url_original"]
    assert campos["valor_total"] == 5_000_000.0
    assert campos["modalidade"] == "Chamada Pública"
    assert campos["data_publicacao"] == datetime(2025, 1, 10)
    print("[OK] _extrair_campos")


def test_extrair_campos_sem_url():
    """Sem linkSistemaOrigem deve montar URL a partir do CNPJ/ano/seq."""
    item = {
        "objetoCompra": "Edital X",
        "orgaoEntidade": {"cnpj": "00000000000191", "razaoSocial": "Banco do Brasil"},
        "anoCompra": 2025,
        "sequencialCompra": 7,
    }
    campos = _extrair_campos(item)
    assert "00000000000191" in campos["url_original"]
    print("[OK] _extrair_campos_sem_url")


# ---------------------------------------------------------------------------
# PNCP — _e_relevante
# ---------------------------------------------------------------------------

def test_e_relevante():
    item_relevante = {
        "objetoCompra": "Projeto de restauração florestal e compensação de carbono",
        "orgaoEntidade": {"razaoSocial": "MMA"},
    }
    item_irrelevante = {
        "objetoCompra": "Aquisição de material de escritório",
        "orgaoEntidade": {"razaoSocial": "Ministério da Fazenda"},
    }
    palavras = ["restauração florestal", "carbono", "REDD"]

    assert _e_relevante(item_relevante, palavras) is True
    assert _e_relevante(item_irrelevante, palavras) is False
    assert _e_relevante(item_relevante, []) is False  # sem palavras → não relevante
    print("[OK] _e_relevante")


# ---------------------------------------------------------------------------
# WebSearch — _gerar_queries
# ---------------------------------------------------------------------------

def test_gerar_queries():
    perfil = _perfil(
        palavras_chave=["restauração florestal", "carbono"],
        fontes=["BNDES", "FINEP"],
    )
    queries = _gerar_queries(perfil)
    assert len(queries) > 0
    assert len(queries) <= 15  # respeita MAX_QUERIES_POR_PERFIL

    # Deve conter ao menos uma query com a palavra-chave
    texto_queries = " ".join(queries)
    assert "restauração florestal" in texto_queries
    assert "carbono" in texto_queries
    print(f"[OK] _gerar_queries: {len(queries)} queries geradas")
    for q in queries[:5]:
        print(f"     -> {q}")


def test_gerar_queries_sem_palavras():
    """Sem palavras-chave, gera apenas queries gerais de consultoria ambiental."""
    perfil = _perfil()
    queries = _gerar_queries(perfil)
    # Agora sempre gera ao menos as queries gerais de área
    assert isinstance(queries, list)
    # Sem keywords específicas, nenhuma query deve conter aspas duplas de keyword
    for q in queries:
        assert '""' not in q
    print(f"[OK] _gerar_queries sem palavras-chave -> {len(queries)} query(ies) gerais")


# ---------------------------------------------------------------------------
# WebSearch — _url_valida
# ---------------------------------------------------------------------------

def test_url_valida():
    assert _url_valida("https://bndes.gov.br/edital/2025") is True
    assert _url_valida("https://www.youtube.com/watch?v=abc") is False
    assert _url_valida("https://wikipedia.org/wiki/REDD") is False
    assert _url_valida("") is False
    print("[OK] _url_valida")


# ---------------------------------------------------------------------------
# WebSearch — _inferir_fonte
# ---------------------------------------------------------------------------

def test_inferir_fonte():
    assert _inferir_fonte("https://bndes.gov.br/foo") == "BNDES"
    assert _inferir_fonte("https://finep.gov.br/chamada") == "FINEP"
    assert _inferir_fonte("https://pncp.gov.br/app") == "PNCP"
    assert _inferir_fonte("https://randomsite.com.br") == "DuckDuckGo"
    print("[OK] _inferir_fonte")


# ---------------------------------------------------------------------------
# WebSearch — _normalizar_resultado
# ---------------------------------------------------------------------------

def test_normalizar_resultado():
    raw = {
        "href": "https://mma.gov.br/edital/restauracao-2025",
        "title": "Chamada Pública MMA — Restauração Florestal 2025",
        "body": "O Ministério do Meio Ambiente abre chamada pública para projetos de restauração.",
    }
    campos = _normalizar_resultado(raw)
    assert campos is not None
    assert campos["titulo"] == "Chamada Pública MMA — Restauração Florestal 2025"
    assert campos["fonte"] == "MMA"
    assert "mma.gov.br" in campos["url_original"]
    assert campos["descricao_curta"] is not None
    print("[OK] _normalizar_resultado")


def test_normalizar_resultado_bloqueado():
    raw = {
        "href": "https://youtube.com/watch?v=123",
        "title": "Vídeo sobre editais",
        "body": "...",
    }
    assert _normalizar_resultado(raw) is None
    print("[OK] _normalizar_resultado (URL bloqueada → None)")


def test_normalizar_resultado_sem_titulo():
    raw = {
        "href": "https://gov.br/edital",
        "title": "",
        "body": "Chamada pública aberta para inscrição de projetos de fomento",
    }
    campos = _normalizar_resultado(raw)
    assert campos is not None
    assert len(campos["titulo"]) > 0
    print("[OK] _normalizar_resultado (title vazio usa body)")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Smoke tests dos scrapers (sem rede) ===\n")

    test_parse_data()
    test_extrair_campos()
    test_extrair_campos_sem_url()
    test_e_relevante()
    test_gerar_queries()
    test_gerar_queries_sem_palavras()
    test_url_valida()
    test_inferir_fonte()
    test_normalizar_resultado()
    test_normalizar_resultado_bloqueado()
    test_normalizar_resultado_sem_titulo()

    print("\n=== Todos os testes dos scrapers passaram! ===")
