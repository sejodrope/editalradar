"""
Jobs do scheduler periódico do EditalRadar.

Dois jobs registrados:
  - busca_editais  : a cada hora, verifica quais perfis precisam de busca e executa
  - gerar_alertas  : a cada 6 horas, cria alertas de prazo para editais ativos

Pode ser iniciado embutido no Streamlit (via BackgroundScheduler) ou como
processo standalone via scheduler/runner.py.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Garante que o diretório do projeto está no path quando rodado diretamente
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

DB_PATH = "editalradar.db"
_CUTOFF_MINUTOS = 15  # janela para considerar um edital "recém-criado"


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _editais_recentes(db, perfil_id: int) -> list:
    """Retorna editais com status 'novo' criados dentro da janela de corte."""
    import crud
    from models import StatusEdital

    cutoff = datetime.now() - timedelta(minutes=_CUTOFF_MINUTOS)
    todos = crud.listar_editais(db, perfil_id=perfil_id, status=[StatusEdital.NOVO])
    return [e for e in todos if e.criado_em >= cutoff]


def _log_resumo_busca(perfil_nome: str, resultado: dict, n_triados: int) -> None:
    total = resultado.get("pncp", 0) + resultado.get("web", 0)
    logger.info(
        "[busca] perfil='%s' pncp=%s web=%s total=%s triados=%s",
        perfil_nome, resultado.get("pncp", 0), resultado.get("web", 0), total, n_triados,
    )


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def job_busca_editais(db_path: str = DB_PATH) -> dict[str, int]:
    """
    Verifica quais perfis precisam de atualização e executa busca em todas as fontes.
    Para cada perfil com editais novos, dispara a triagem do Gemini.

    Retorna contadores: {"pncp": N, "web": N, "perfis_buscados": N, "triados": N}
    """
    from models import get_session
    import crud
    from scrapers.web_search import executar_busca_completa
    from ai.triagem import triar_editais

    contadores: dict[str, int] = {"pncp": 0, "web": 0, "perfis_buscados": 0, "triados": 0}
    db = get_session(db_path)

    try:
        perfis = crud.perfis_para_buscar(db)
        if not perfis:
            logger.debug("[busca] Nenhum perfil necessita de busca agora.")
            return contadores

        contadores["perfis_buscados"] = len(perfis)
        logger.info("[busca] Iniciando busca para %s perfil(is).", len(perfis))

        for perfil in perfis:
            try:
                resultado = executar_busca_completa(db, perfil)
                contadores["pncp"] += resultado.get("pncp", 0)
                contadores["web"] += resultado.get("web", 0)

                novos = _editais_recentes(db, perfil.id)
                if novos:
                    triar_editais(db, novos, perfil)
                    contadores["triados"] += len(novos)

                _log_resumo_busca(perfil.nome, resultado, len(novos))

            except Exception as exc:
                logger.error("[busca] Erro no perfil '%s': %s", perfil.nome, exc)

    except Exception as exc:
        logger.error("[busca] Erro geral: %s", exc)
    finally:
        db.close()

    return contadores


def job_gerar_alertas(db_path: str = DB_PATH) -> int:
    """
    Gera alertas de prazo (7 dias, 3 dias, hoje) para todos os editais ativos.
    Retorna a quantidade de alertas criados nesta execução.
    """
    from models import get_session
    import crud

    db = get_session(db_path)
    try:
        criados = crud.gerar_alertas_prazo(db)
        if criados:
            logger.info("[alertas] %s novo(s) alerta(s) de prazo gerado(s).", criados)
        return criados
    except Exception as exc:
        logger.error("[alertas] Erro ao gerar alertas: %s", exc)
        return 0
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Fábrica do scheduler
# ---------------------------------------------------------------------------

def criar_scheduler(db_path: str = DB_PATH):
    """
    Cria e configura o BackgroundScheduler com os jobs do EditalRadar.

    Jobs:
      - busca_editais  : interval/1h (verifica internamente quais perfis precisam)
      - gerar_alertas  : interval/6h

    Returns:
        BackgroundScheduler configurado (não iniciado).
    Raises:
        ImportError se apscheduler não estiver instalado.
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.executors.pool import ThreadPoolExecutor
    except ImportError as exc:
        raise ImportError(
            "APScheduler não instalado. Execute: pip install apscheduler"
        ) from exc

    scheduler = BackgroundScheduler(
        executors={"default": ThreadPoolExecutor(max_workers=1)},
        job_defaults={
            "coalesce": True,       # executa apenas uma vez se atrasado
            "max_instances": 1,     # evita execuções sobrepostas
            "misfire_grace_time": 300,
        },
        timezone="America/Sao_Paulo",
    )

    scheduler.add_job(
        func=job_busca_editais,
        trigger="interval",
        hours=1,
        id="busca_editais",
        name="Busca periódica de editais",
        kwargs={"db_path": db_path},
        replace_existing=True,
        # Executa também imediatamente ao iniciar (next_run_time=now)
        next_run_time=datetime.now(),
    )

    scheduler.add_job(
        func=job_gerar_alertas,
        trigger="interval",
        hours=6,
        id="gerar_alertas",
        name="Geração de alertas de prazo",
        kwargs={"db_path": db_path},
        replace_existing=True,
        next_run_time=datetime.now() + timedelta(seconds=30),  # ligeiro delay
    )

    return scheduler


def iniciar_scheduler(db_path: str = DB_PATH):
    """
    Cria e inicia o BackgroundScheduler.
    Retorna None graciosamente se APScheduler não estiver disponível.

    Uso típico em app.py:
        @st.cache_resource
        def _start_scheduler():
            from scheduler.jobs import iniciar_scheduler
            return iniciar_scheduler()
    """
    try:
        sched = criar_scheduler(db_path)
        sched.start()
        jobs = [j.id for j in sched.get_jobs()]
        logger.info("Scheduler iniciado. Jobs ativos: %s", jobs)
        return sched
    except ImportError as exc:
        logger.warning("Scheduler desativado (APScheduler ausente): %s", exc)
        return None
    except Exception as exc:
        logger.error("Scheduler não pôde ser iniciado: %s", exc)
        return None


def parar_scheduler(scheduler) -> None:
    """Para o scheduler de forma limpa, aguardando jobs em andamento."""
    if scheduler is None:
        return
    try:
        scheduler.shutdown(wait=True)
        logger.info("Scheduler encerrado.")
    except Exception as exc:
        logger.warning("Erro ao encerrar scheduler: %s", exc)


def status_scheduler(scheduler) -> dict:
    """
    Retorna um dict com o estado atual do scheduler e próximas execuções.
    Útil para exibir na página de Configurações.
    """
    if scheduler is None:
        return {"ativo": False, "jobs": []}

    jobs_info = []
    for job in scheduler.get_jobs():
        jobs_info.append({
            "id": job.id,
            "nome": job.name,
            "proxima_execucao": job.next_run_time,
        })

    return {
        "ativo": scheduler.running,
        "jobs": jobs_info,
    }
