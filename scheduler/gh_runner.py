"""
Runner para GitHub Actions.

O GitHub Actions dispara este script um pouco ANTES da meia-noite (via cron
no workflow). O script então:
  1. Lê as reservas pendentes (do arquivo reservations.json versionado no repo)
  2. Faz login no TownSq com antecedência (para não perder tempo na hora H)
  3. Fica em espera ativa até 00:00:00 do horário de Brasília
  4. No instante exato, dispara as tentativas de reserva

Por que esperar dentro do script em vez de confiar no cron?
Porque o cron do GitHub Actions costuma atrasar 10-30 min. Então acordamos
mais cedo e controlamos o timing fino aqui dentro, garantindo o disparo no
segundo exato em que a janela de reserva abre.
"""
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from scraper.townsq_client import criar_cliente_do_env

# Fuso de Brasília (UTC-3, sem horário de verão desde 2019)
BRASILIA = timezone(timedelta(hours=-3))

# Quantas tentativas e com que intervalo, a partir do disparo à meia-noite
MAX_TENTATIVAS = 40
INTERVALO_ENTRE_TENTATIVAS_SEGUNDOS = 2

# Margem de segurança: se faltar mais que isso pra meia-noite, esperamos.
# Se já passou da meia-noite (cron atrasou), dispara imediatamente.
RESERVATIONS_FILE = Path(__file__).parent.parent / "reservations.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("gh_runner")


def carregar_reservas_pendentes():
    if not RESERVATIONS_FILE.exists():
        logger.warning(f"Arquivo {RESERVATIONS_FILE} não encontrado. Nada a fazer.")
        return []
    with open(RESERVATIONS_FILE, encoding="utf-8") as f:
        dados = json.load(f)
    # Só reservas cujo "momento de abertura" é HOJE (à meia-noite que está chegando)
    hoje = datetime.now(BRASILIA).date()
    pendentes = []
    for r in dados.get("reservas", []):
        if r.get("status") != "agendado":
            continue
        data_desejada = datetime.strptime(r["data_desejada"], "%Y-%m-%d").date()
        momento_abertura = data_desejada - timedelta(days=r["dias_antecedencia_abertura"])
        if momento_abertura == hoje:
            pendentes.append(r)
    return pendentes


def esperar_ate_meia_noite():
    """Espera (com precisão) até 00:00:00 de Brasília. Se já passou, retorna já."""
    agora = datetime.now(BRASILIA)
    # A próxima meia-noite após 'agora'
    proxima_meia_noite = (agora + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    # Se estamos rodando ANTES da meia-noite (ex: 23:45), a meia-noite alvo é hoje+0:00 do dia seguinte
    # Se o cron atrasou e já passou da meia-noite, não esperamos.
    if agora.hour == 0:
        logger.info("Já passou da meia-noite (cron pode ter atrasado). Disparando imediatamente.")
        return

    segundos_ate = (proxima_meia_noite - agora).total_seconds()
    if segundos_ate > 900:  # mais de 15 min: algo errado no agendamento, mas esperamos mesmo assim
        logger.warning(f"Faltam {segundos_ate:.0f}s até meia-noite (muito). Esperando mesmo assim.")

    logger.info(f"Aguardando {segundos_ate:.1f}s até a meia-noite de Brasília ({proxima_meia_noite})...")
    # Espera grosseira até faltar 2s, depois espera fina
    while True:
        restante = (proxima_meia_noite - datetime.now(BRASILIA)).total_seconds()
        if restante <= 0:
            break
        time.sleep(min(restante, 1))
    logger.info("Meia-noite! Disparando tentativas de reserva.")


def executar():
    pendentes = carregar_reservas_pendentes()
    if not pendentes:
        logger.info("Nenhuma reserva pendente para hoje. Encerrando.")
        return

    logger.info(f"{len(pendentes)} reserva(s) pendente(s) para hoje.")

    # Faz login ANTES da meia-noite para não perder tempo
    with criar_cliente_do_env() as client:
        client.login()

        for reserva in pendentes:
            client.navegar_para_reserva_quadra(reserva["quadra"])

        # Espera o instante exato
        esperar_ate_meia_noite()

        # Dispara para cada reserva
        for reserva in pendentes:
            data_desejada = datetime.strptime(reserva["data_desejada"], "%Y-%m-%d").date()
            client.navegar_para_reserva_quadra(reserva["quadra"])
            sucesso = False
            for tentativa in range(1, MAX_TENTATIVAS + 1):
                ok = client.tentar_reservar(data_desejada, reserva["horario_desejado"])
                if ok:
                    sucesso = True
                    logger.info(f"✅ Reserva CONFIRMADA: {reserva['quadra']} "
                                f"{reserva['data_desejada']} {reserva['horario_desejado']}")
                    break
                logger.info(f"Tentativa {tentativa}/{MAX_TENTATIVAS} sem sucesso...")
                time.sleep(INTERVALO_ENTRE_TENTATIVAS_SEGUNDOS)
                client.recarregar_pagina_reserva()
            if not sucesso:
                logger.error(f"❌ Falhou após {MAX_TENTATIVAS} tentativas: "
                             f"{reserva['quadra']} {reserva['data_desejada']} {reserva['horario_desejado']}")


if __name__ == "__main__":
    executar()
