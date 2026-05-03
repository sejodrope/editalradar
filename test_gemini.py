"""
Testes unitários para ai/gemini.py — sem chamadas reais à API.
Valida: parsing JSON, validação de resultado, prompt, fallback sem chave, triagem em lote.
"""

import sys
sys.path.insert(0, ".")

import os
from unittest.mock import MagicMock, patch

from ai.gemini import (
    _extrair_json,
    _validar_resultado,
    _montar_prompt,
    analisar_edital,
    triar_editais,
    esta_configurado,
    RELEVANCIA_MINIMA,
)
from models import Edital, Perfil, StatusEdital, init_db, get_session
import crud


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _edital(titulo="Chamada Pública BNDES Restauração 2025", descricao="Fomento à restauração florestal"):
    e = Edital()
    e.id = 1
    e.titulo = titulo
    e.descricao_completa = descricao
    e.descricao_curta = None
    e.orgao_publicador = "BNDES"
    e.modalidade = "Chamada Pública"
    e.status = StatusEdital.NOVO
    e.observacoes = None
    return e


def _perfil():
    p = Perfil()
    p.nome = "Restauração Florestal"
    p.area_atuacao = "Meio Ambiente"
    p.palavras_chave = ["restauração florestal", "carbono", "REDD"]
    return p


# ---------------------------------------------------------------------------
# _extrair_json
# ---------------------------------------------------------------------------

def test_extrair_json_puro():
    texto = '{"relevancia": 85, "motivo": "ok", "tags": ["floresta"], "resumo_curto": "resumo"}'
    dados = _extrair_json(texto)
    assert dados is not None
    assert dados["relevancia"] == 85
    print("[OK] _extrair_json (JSON puro)")


def test_extrair_json_markdown():
    texto = '```json\n{"relevancia": 70, "motivo": "relevante", "tags": [], "resumo_curto": "x"}\n```'
    dados = _extrair_json(texto)
    assert dados is not None
    assert dados["relevancia"] == 70
    print("[OK] _extrair_json (markdown fence)")


def test_extrair_json_embutido():
    texto = 'Aqui está a resposta: {"relevancia": 40, "motivo": "pouco relevante", "tags": [], "resumo_curto": "y"} fim.'
    dados = _extrair_json(texto)
    assert dados is not None
    assert dados["relevancia"] == 40
    print("[OK] _extrair_json (JSON embutido em texto)")


def test_extrair_json_invalido():
    assert _extrair_json("isso nao e json") is None
    assert _extrair_json("") is None
    print("[OK] _extrair_json (texto inválido -> None)")


# ---------------------------------------------------------------------------
# _validar_resultado
# ---------------------------------------------------------------------------

def test_validar_resultado_normal():
    dados = {"relevancia": 85, "motivo": "Muito relevante", "tags": ["mata", "carbono"], "resumo_curto": "Resumo ok"}
    r = _validar_resultado(dados)
    assert r["relevancia"] == 85
    assert r["tags"] == ["mata", "carbono"]
    assert r["resumo_curto"] == "Resumo ok"
    print("[OK] _validar_resultado (normal)")


def test_validar_resultado_limites():
    # Relevância fora do range 0-100
    r = _validar_resultado({"relevancia": 150})
    assert r["relevancia"] == 100
    r = _validar_resultado({"relevancia": -10})
    assert r["relevancia"] == 0
    print("[OK] _validar_resultado (limites 0-100)")


def test_validar_resultado_tipos_errados():
    dados = {"relevancia": "oitenta", "tags": "nao-e-lista", "motivo": 123}
    r = _validar_resultado(dados)
    assert r["relevancia"] == 50   # fallback
    assert r["tags"] == []         # lista inválida vira []
    assert isinstance(r["motivo"], str)
    print("[OK] _validar_resultado (tipos errados -> fallback)")


def test_validar_resultado_max_tags():
    dados = {"relevancia": 60, "tags": [f"tag{i}" for i in range(20)]}
    r = _validar_resultado(dados)
    assert len(r["tags"]) <= 10
    print("[OK] _validar_resultado (máx 10 tags)")


# ---------------------------------------------------------------------------
# _montar_prompt
# ---------------------------------------------------------------------------

def test_montar_prompt():
    prompt = _montar_prompt(_edital(), _perfil())
    assert "restauração florestal" in prompt
    assert "BNDES" in prompt
    assert "Meio Ambiente" in prompt
    assert "JSON" in prompt
    assert "relevancia" in prompt
    print("[OK] _montar_prompt")


def test_montar_prompt_trunca_descricao_longa():
    descricao_longa = "x" * 5000
    edital = _edital(descricao=descricao_longa)
    prompt = _montar_prompt(edital, _perfil())
    # A descrição no prompt deve estar truncada
    assert len(prompt) < 10000
    print("[OK] _montar_prompt (trunca descricao longa)")


# ---------------------------------------------------------------------------
# analisar_edital — com mock da API
# ---------------------------------------------------------------------------

def test_analisar_edital_sucesso():
    resposta_mock = '{"relevancia": 88, "motivo": "Edital direto ao ponto", "tags": ["mata", "REDD"], "resumo_curto": "Fomento florestal"}'

    with patch("ai.gemini._chamar_gemini", return_value=resposta_mock):
        resultado = analisar_edital(_edital(), _perfil(), chave="fake-key")

    assert resultado is not None
    assert resultado["relevancia"] == 88
    assert "mata" in resultado["tags"]
    print("[OK] analisar_edital (mock sucesso)")


def test_analisar_edital_api_falha():
    with patch("ai.gemini._chamar_gemini", return_value=None):
        resultado = analisar_edital(_edital(), _perfil(), chave="fake-key")
    assert resultado is None
    print("[OK] analisar_edital (API falha -> None)")


def test_analisar_edital_sem_chave():
    with patch("ai.gemini._carregar_chave_env", return_value=None):
        resultado = analisar_edital(_edital(), _perfil())
    assert resultado is None
    print("[OK] analisar_edital (sem chave -> None sem erro)")


# ---------------------------------------------------------------------------
# triar_editais — com banco em memória e mock da API
# ---------------------------------------------------------------------------

def _setup_db():
    engine = init_db(":memory:")
    db = get_session(":memory:")
    perfil = crud.criar_perfil(
        db,
        nome="Florestal",
        area_atuacao="Meio Ambiente",
        palavras_chave=["restauração"],
    )
    e1 = crud.criar_edital(db, perfil.id, titulo="Edital Relevante", fonte="BNDES", url_original="https://a.com")
    e2 = crud.criar_edital(db, perfil.id, titulo="Edital Irrelevante", fonte="DuckDuckGo", url_original="https://b.com")
    return db, perfil, [e1, e2]


def test_triar_editais_sem_chave():
    db, perfil, editais = _setup_db()
    with patch("ai.gemini._carregar_chave_env", return_value=None):
        contadores = triar_editais(db, editais, perfil)
    assert contadores["sem_chave"] == 2
    assert contadores["analisados"] == 0
    # Status não deve ter mudado
    for e in editais:
        atualizado = crud.obter_edital(db, e.id)
        assert atualizado.status == StatusEdital.NOVO
    print("[OK] triar_editais (sem chave -> sem_chave=2, status inalterado)")


def test_triar_editais_com_mock():
    db, perfil, editais = _setup_db()

    respostas = [
        # Edital 1: relevante (88)
        '{"relevancia": 88, "motivo": "Muito relevante", "tags": ["floresta"], "resumo_curto": "Resumo A"}',
        # Edital 2: irrelevante (15) -> deve ser descartado
        '{"relevancia": 15, "motivo": "Sem relacao", "tags": [], "resumo_curto": "Resumo B"}',
    ]

    with patch("ai.gemini._chamar_gemini", side_effect=respostas):
        contadores = triar_editais(db, editais, perfil, chave="fake-key")

    assert contadores["analisados"] == 2
    assert contadores["descartados"] == 1

    e1 = crud.obter_edital(db, editais[0].id)
    e2 = crud.obter_edital(db, editais[1].id)

    assert e1.relevancia_score == 88
    assert e1.status == StatusEdital.NOVO
    assert e1.tags == ["floresta"]

    assert e2.relevancia_score == 15
    assert e2.status == StatusEdital.DESCARTADO
    print("[OK] triar_editais (mock: 2 analisados, 1 descartado)")


def test_triar_editais_api_intermitente():
    """Se a API falha para um edital, deve continuar processando os demais."""
    db, perfil, editais = _setup_db()

    respostas = [None, '{"relevancia": 75, "motivo": "ok", "tags": [], "resumo_curto": "ok"}']

    with patch("ai.gemini._chamar_gemini", side_effect=respostas):
        contadores = triar_editais(db, editais, perfil, chave="fake-key")

    assert contadores["analisados"] == 1   # só o segundo foi analisado
    e2 = crud.obter_edital(db, editais[1].id)
    assert e2.relevancia_score == 75
    print("[OK] triar_editais (API intermitente -> continua processando)")


# ---------------------------------------------------------------------------
# esta_configurado
# ---------------------------------------------------------------------------

def test_esta_configurado_com_env():
    with patch.dict(os.environ, {"GEMINI_API_KEY": "minha-chave"}):
        assert esta_configurado() is True
    print("[OK] esta_configurado (com env var)")


def test_esta_configurado_sem_env():
    env_sem_chave = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
    with patch.dict(os.environ, env_sem_chave, clear=True):
        with patch("ai.gemini.Path.exists", return_value=False):
            assert esta_configurado() is False
    print("[OK] esta_configurado (sem chave -> False)")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Smoke tests ai/gemini.py (sem rede) ===\n")

    test_extrair_json_puro()
    test_extrair_json_markdown()
    test_extrair_json_embutido()
    test_extrair_json_invalido()

    test_validar_resultado_normal()
    test_validar_resultado_limites()
    test_validar_resultado_tipos_errados()
    test_validar_resultado_max_tags()

    test_montar_prompt()
    test_montar_prompt_trunca_descricao_longa()

    test_analisar_edital_sucesso()
    test_analisar_edital_api_falha()
    test_analisar_edital_sem_chave()

    test_triar_editais_sem_chave()
    test_triar_editais_com_mock()
    test_triar_editais_api_intermitente()

    test_esta_configurado_com_env()
    test_esta_configurado_sem_env()

    print("\n=== Todos os testes do Gemini passaram! ===")
