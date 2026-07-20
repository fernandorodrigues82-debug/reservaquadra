"""
Serviço de agendamento.

Para cada reserva pendente no banco de dados, calcula o exato momento em
que a janela de reserva abre (data_desejada - dias_antecedencia + hora_abertura)
e agenda um job para começar a tentar reservar A PARTIR DESSE INSTANTE,
insistindo em alta frequência por alguns segundos/minutos, já que outros
moradores também vão estar tentando pegar o mesmo horário.
"""
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from tenacity import retry, stop_after_attempt, wait_fixed

sys.path.append(str(Path(__file__).parent.parent))
import storage
from scraper.townsq_client import criar_cliente_do_env

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent.parent / "data" / "scheduler.log"),
    ],
)
logger = logging.getLogger("scheduler_service")

# Quantas vezes tentar / intervalo entre tentativas assim que a janela abre.
# Ajuste conforme a concorrência real pelo horário (mais concorrido = mais tentativas rápidas).
MAX_TENTATIVAS = 40
INTERVALO_ENTRE_TENTATIVAS_SEGUNDOS = 2


def calcular_momento_abertura(reservation: dict) -> datetime:
    data_desejada = datetime.strptime(reservation["data_desejada"], "%Y-%m-%d")
    hora_abertura = datetime.strptime(reservation["hora_abertura"], "%H:%M").time()
    momento_abertura = data_desejada - timedelta(days=reservation["dias_antecedencia_abertura"])
    return datetime.combine(momento_abertura.date(), hora_abertura)


def executar_tentativa_de_reserva(reservation_id: int):
    reservation = next(
        (r for r in storage.list_reservations() if r["id"] == reservation_id), None
    )
    if not reservation or reservation["status"] != "agendado":
        logger.info(f"Reserva {reservation_id} não está mais 'agendado', pulando.")
        return

    storage.update_status(reservation_id, "executando")
    storage.add_log(reservation_id, "Iniciando tentativas de reserva.")

    data_desejada = datetime.strptime(reservation["data_desejada"], "%Y-%m-%d").date()
    sucesso = False

    try:
        with criar_cliente_do_env() as client:
            client.login()
            client.navegar_para_reserva_quadra(reservation["quadra"])

            for tentativa in range(1, MAX_TENTATIVAS + 1):
                ok = client.tentar_reservar(data_desejada, reservation["horario_desejado"])
                if ok:
                    sucesso = True
                    break
                storage.add_log(
                    reservation_id,
                    f"Tentativa {tentativa}/{MAX_TENTATIVAS} sem sucesso, tentando de novo..."
                )
                time.sleep(INTERVALO_ENTRE_TENTATIVAS_SEGUNDOS)
                client.recarregar_pagina_reserva()

    except Exception as e:
        logger.exception("Erro durante tentativa de reserva")
        storage.add_log(reservation_id, f"Erro: {e}", nivel="ERRO")

    if sucesso:
        storage.update_status(reservation_id, "sucesso")
        storage.add_log(reservation_id, "Reserva concluída com sucesso!", nivel="SUCESSO")
    else:
        storage.update_status(reservation_id, "falha")
        storage.add_log(
            reservation_id,
            f"Não foi possível reservar após {MAX_TENTATIVAS} tentativas.",
            nivel="ERRO",
        )


def agendar_todas_pendentes(scheduler: BlockingScheduler):
    for reservation in storage.list_reservations():
        if reservation["status"] != "agendado":
            continue
        momento = calcular_momento_abertura(reservation)
        if momento < datetime.now():
            logger.warning(
                f"Reserva {reservation['id']}: momento de abertura já passou ({momento}). "
                "Verifique a configuração de antecedência."
            )
            continue
        scheduler.add_job(
            executar_tentativa_de_reserva,
            "date",
            run_date=momento,
            args=[reservation["id"]],
            id=f"reserva_{reservation['id']}",
            replace_existing=True,
        )
        logger.info(f"Reserva {reservation['id']} agendada para {momento}.")


def main():
    storage.init_db()
    scheduler = BlockingScheduler()
    agendar_todas_pendentes(scheduler)

    # Reavalia a cada 5 minutos se novas reservas foram criadas pelo painel Streamlit
    scheduler.add_job(
        lambda: agendar_todas_pendentes(scheduler),
        "interval",
        minutes=5,
        id="reload_pendentes",
    )

    logger.info("Scheduler iniciado. Aguardando horários de abertura das reservas...")
    scheduler.start()


if __name__ == "__main__":
    main()
