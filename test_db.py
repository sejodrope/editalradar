"""
Script de smoke test para validar models.py + crud.py com banco em memória.
Execute: python test_db.py
"""

from datetime import datetime, timedelta

from models import init_db, get_session, StatusEdital, TipoDocumento, TipoAlerta
import crud

DB_PATH = ":memory:"

def run():
    print("=== EditalRadar — Smoke Test DB ===\n")

    # Inicializa banco em memória
    init_db(DB_PATH)
    db = get_session(DB_PATH)

    # 1. Perfil
    perfil = crud.criar_perfil(
        db,
        nome="Restauração Florestal",
        descricao="Monitoramento de editais de conservação e restauração",
        area_atuacao="Meio Ambiente",
        palavras_chave=["restauração florestal", "REDD", "carbono", "biodiversidade"],
        fontes_priorizadas=["BNDES", "MMA", "FINEP", "PNCP"],
    )
    assert perfil.id is not None
    print(f"[OK] Perfil criado: {perfil}")

    # 2. Listar perfis
    perfis = crud.listar_perfis(db)
    assert len(perfis) == 1
    print(f"[OK] listar_perfis: {len(perfis)} perfil(is)")

    # 3. Edital
    edital = crud.criar_edital(
        db,
        perfil_id=perfil.id,
        titulo="Chamada Pública BNDES — Restauração da Mata Atlântica 2025",
        fonte="BNDES",
        url_original="https://bndes.gov.br/edital/restauracao-2025",
        orgao_publicador="BNDES",
        modalidade="Chamada Pública",
        data_encerramento=datetime.utcnow() + timedelta(days=5),
        valor_total=10_000_000.0,
        relevancia_score=92,
        tags=["mata atlântica", "restauração", "fomento"],
    )
    assert edital.id is not None
    print(f"[OK] Edital criado: {edital}")

    # 4. Deduplicação por URL
    existe = crud.edital_existe_por_url(db, edital.url_original, perfil.id)
    assert existe is True
    nao_existe = crud.edital_existe_por_url(db, "https://outro.gov.br", perfil.id)
    assert nao_existe is False
    print("[OK] Deduplicação por URL")

    # 5. Listar e filtrar editais
    todos = crud.listar_editais(db, perfil_id=perfil.id)
    assert len(todos) == 1
    por_texto = crud.listar_editais(db, texto="BNDES")
    assert len(por_texto) == 1
    sem_resultado = crud.listar_editais(db, texto="FINEP")
    assert len(sem_resultado) == 0
    print(f"[OK] listar_editais com filtros")

    # 6. Mudar status
    edital = crud.mudar_status_edital(db, edital.id, StatusEdital.INTERESSANTE)
    assert edital.status == StatusEdital.INTERESSANTE
    print(f"[OK] mudar_status_edital: {edital.status}")

    # 7. Documento
    doc = crud.criar_documento(
        db,
        edital_id=edital.id,
        nome="Proposta Técnica",
        tipo=TipoDocumento.EXIGIDO,
        descricao="Documento descrevendo a proposta de restauração",
    )
    assert doc.id is not None
    doc = crud.marcar_documento_enviado(db, doc.id)
    assert doc.data_envio is not None
    print(f"[OK] Documento criado e marcado como enviado: {doc}")

    # 8. Alertas de prazo
    n = crud.gerar_alertas_prazo(db)
    assert n >= 1  # edital vence em 5 dias → alerta PRAZO_7DIAS
    alertas = crud.listar_alertas(db, apenas_nao_lidos=True, perfil_id=perfil.id)
    assert len(alertas) >= 1
    print(f"[OK] Alertas de prazo gerados: {n}, não lidos: {len(alertas)}")

    nao_lidos = crud.contar_alertas_nao_lidos(db, perfil_id=perfil.id)
    crud.marcar_todos_alertas_lidos(db, perfil_id=perfil.id)
    assert crud.contar_alertas_nao_lidos(db, perfil_id=perfil.id) == 0
    print(f"[OK] marcar_todos_alertas_lidos (havia {nao_lidos})")

    # 9. Estatísticas do dashboard
    ativos = crud.contar_editais_ativos(db, perfil_id=perfil.id)
    vencendo = crud.contar_vencendo_em_dias(db, dias=7, perfil_id=perfil.id)
    novos_hoje = crud.contar_novos_hoje(db, perfil_id=perfil.id)
    timeline = crud.editais_proximos_30_dias(db, perfil_id=perfil.id)
    print(f"[OK] Dashboard stats — ativos={ativos}, vencendo_7d={vencendo}, novos_hoje={novos_hoje}, timeline={len(timeline)}")

    # 10. ConfiguracaoBusca
    config = crud.obter_config_busca(db, perfil.id)
    assert config is not None and config.frequencia_horas == 24
    crud.atualizar_config_busca(db, perfil.id, frequencia_horas=12, ultima_busca_em=datetime.utcnow())
    config = crud.obter_config_busca(db, perfil.id)
    assert config.frequencia_horas == 12
    print(f"[OK] ConfiguracaoBusca atualizada: freq={config.frequencia_horas}h")

    # 11. perfis_para_buscar (última busca recente → não deve retornar)
    para_buscar = crud.perfis_para_buscar(db)
    assert len(para_buscar) == 0  # acabamos de setar ultima_busca_em = agora
    print(f"[OK] perfis_para_buscar: {len(para_buscar)} (correto, busca recente)")

    # 12. Limpar descartados
    crud.mudar_status_edital(db, edital.id, StatusEdital.DESCARTADO)
    # Força a data de atualização para > 90 dias atrás
    edital_obj = crud.obter_edital(db, edital.id)
    edital_obj.atualizado_em = datetime.utcnow() - timedelta(days=91)
    db.commit()
    removidos = crud.limpar_descartados_antigos(db, dias=90)
    assert removidos == 1
    print(f"[OK] limpar_descartados_antigos: {removidos} removido(s)")

    # 13. Deletar perfil em cascata
    crud.deletar_perfil(db, perfil.id)
    assert crud.obter_perfil(db, perfil.id) is None
    print("[OK] deletar_perfil (cascata OK)")

    db.close()
    print("\n=== Todos os testes passaram! ===")


if __name__ == "__main__":
    run()
