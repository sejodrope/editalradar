"""
Testes unitários para scheduler/jobs.py — sem chamadas reais de rede ou API.
Valida: job_busca_editais, job_gerar_alertas, criar_scheduler, status_scheduler.
"""

import sys
sys.path.insert(0, ".")

from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from models import init_db, get_session, StatusEdital
import crud


# ---------------------------------------------------------------------------
# Setup de banco em memória
# ---------------------------------------------------------------------------

def _setup():
    init_db(":memory:")
    db = get_session(":memory:")
    perfil = crud.criar_perfil(
        db,
        nome="Florestal",
        area_atuacao="Meio Ambiente",
        palavras_chave=["restauração"],
        fontes_priorizadas=["PNCP"],
    )
    # Força ultima_busca_em = None para que perfis_para_buscar retorne este perfil
    crud.atualizar_config_busca(db, perfil.id, ultima_busca_em=None)
    return db, perfil


# ---------------------------------------------------------------------------
# job_busca_editais
# ---------------------------------------------------------------------------

def test_job_busca_editais_sem_perfis():
    """Com todos os perfis já buscados recentemente, não deve executar nada."""
    db, perfil = _setup()
    # Marca ultima_busca_em = agora → perfil não precisa de busca
    crud.atualizar_config_busca(db, perfil.id, ultima_busca_em=datetime.utcnow())
    db.close()

    with patch("models.get_session", return_value=get_session(":memory:")):
        from scheduler.jobs import job_busca_editais
        resultado = job_busca_editais(db_path=":memory:")

    assert resultado["perfis_buscados"] == 0
    print("[OK] job_busca_editais (sem perfis pendentes -> perfis_buscados=0)")


def test_job_busca_editais_com_mock():
    """Com perfil pendente de busca, deve chamar executar_busca_completa."""
    db, perfil = _setup()

    mock_resultado = {"pncp": 2, "web": 3}
    novos_editais = []

    with (
        patch("crud.perfis_para_buscar", return_value=[perfil]),
        patch("scrapers.web_search.executar_busca_completa", return_value=mock_resultado),
        patch("scheduler.jobs._editais_recentes", return_value=novos_editais),
        patch("models.get_session", return_value=db),
    ):
        from scheduler.jobs import job_busca_editais
        resultado = job_busca_editais(db_path=":memory:")

    assert resultado["pncp"] == 2
    assert resultado["web"] == 3
    assert resultado["perfis_buscados"] == 1
    print("[OK] job_busca_editais (com mock: pncp=2 web=3)")
    db.close()


def test_job_busca_editais_erro_por_perfil():
    """Erro em um perfil não deve interromper os demais."""
    db, perfil = _setup()

    perfil2 = crud.criar_perfil(db, nome="Perfil2", palavras_chave=["carbono"])
    crud.atualizar_config_busca(db, perfil2.id, ultima_busca_em=None)

    resultados_mock = [Exception("falha de rede"), {"pncp": 1, "web": 0}]

    with (
        patch("crud.perfis_para_buscar", return_value=[perfil, perfil2]),
        patch(
            "scrapers.web_search.executar_busca_completa",
            side_effect=resultados_mock
        ),
        patch("scheduler.jobs._editais_recentes", return_value=[]),
        patch("models.get_session", return_value=db),
    ):
        from scheduler.jobs import job_busca_editais
        resultado = job_busca_editais(db_path=":memory:")

    # Apenas o segundo perfil contribuiu (primeiro lançou exceção)
    assert resultado["web"] == 0  # primeiro falhou, segundo tem web=0
    assert resultado["pncp"] == 1
    print("[OK] job_busca_editais (erro em 1 perfil não interrompe os demais)")
    db.close()


# ---------------------------------------------------------------------------
# job_gerar_alertas
# ---------------------------------------------------------------------------

def test_job_gerar_alertas():
    """Deve gerar alerta para edital vencendo em breve."""
    db, perfil = _setup()
    edital = crud.criar_edital(
        db,
        perfil_id=perfil.id,
        titulo="Edital com prazo próximo",
        fonte="PNCP",
        url_original="https://test.gov.br/1",
        data_encerramento=datetime.utcnow() + timedelta(days=2),
    )

    with patch("models.get_session", return_value=db):
        from scheduler.jobs import job_gerar_alertas
        criados = job_gerar_alertas(db_path=":memory:")

    assert criados >= 1
    alertas = crud.listar_alertas(db, apenas_nao_lidos=True)
    assert len(alertas) >= 1
    print(f"[OK] job_gerar_alertas: {criados} alerta(s) criado(s)")
    db.close()


def test_job_gerar_alertas_sem_editais():
    """Sem editais ativos, não deve criar alertas."""
    db = get_session(":memory:")
    init_db(":memory:")

    with patch("models.get_session", return_value=db):
        from scheduler.jobs import job_gerar_alertas
        criados = job_gerar_alertas(db_path=":memory:")

    assert criados == 0
    print("[OK] job_gerar_alertas (sem editais -> 0 alertas)")
    db.close()


# ---------------------------------------------------------------------------
# criar_scheduler / status_scheduler
# ---------------------------------------------------------------------------

def test_criar_scheduler_importa():
    """Verifica que o scheduler é criado sem erros com APScheduler instalado."""
    try:
        from scheduler.jobs import criar_scheduler
        sched = criar_scheduler(db_path=":memory:")
        jobs = sched.get_jobs()
        ids = [j.id for j in jobs]
        assert "busca_editais" in ids
        assert "gerar_alertas" in ids
        print(f"[OK] criar_scheduler: {ids}")
    except ImportError:
        print("[SKIP] criar_scheduler (APScheduler não instalado)")


def test_status_scheduler_inativo():
    """status_scheduler com None deve retornar ativo=False."""
    from scheduler.jobs import status_scheduler
    info = status_scheduler(None)
    assert info["ativo"] is False
    assert info["jobs"] == []
    print("[OK] status_scheduler (None -> ativo=False)")


def test_status_scheduler_ativo():
    """status_scheduler com mock ativo deve retornar jobs."""
    from scheduler.jobs import status_scheduler

    mock_job = MagicMock()
    mock_job.id = "busca_editais"
    mock_job.name = "Busca periódica"
    mock_job.next_run_time = datetime(2026, 6, 1, 10, 0)

    mock_sched = MagicMock()
    mock_sched.running = True
    mock_sched.get_jobs.return_value = [mock_job]

    info = status_scheduler(mock_sched)
    assert info["ativo"] is True
    assert len(info["jobs"]) == 1
    assert info["jobs"][0]["id"] == "busca_editais"
    print("[OK] status_scheduler (mock ativo -> 1 job)")


# ---------------------------------------------------------------------------
# iniciar_scheduler — graceful sem APScheduler
# ---------------------------------------------------------------------------

def test_iniciar_scheduler_sem_apscheduler():
    """Se APScheduler não estiver disponível, deve retornar None sem exceção."""
    with patch("scheduler.jobs.criar_scheduler", side_effect=ImportError("no apscheduler")):
        from scheduler.jobs import iniciar_scheduler
        resultado = iniciar_scheduler(db_path=":memory:")
    assert resultado is None
    print("[OK] iniciar_scheduler (ImportError -> None gracioso)")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Smoke tests scheduler/jobs.py ===\n")

    test_job_busca_editais_sem_perfis()
    test_job_busca_editais_com_mock()
    test_job_busca_editais_erro_por_perfil()
    test_job_gerar_alertas()
    test_job_gerar_alertas_sem_editais()
    test_criar_scheduler_importa()
    test_status_scheduler_inativo()
    test_status_scheduler_ativo()
    test_iniciar_scheduler_sem_apscheduler()

    print("\n=== Todos os testes do scheduler passaram! ===")
