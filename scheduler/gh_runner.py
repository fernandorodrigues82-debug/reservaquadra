"""
Runner para GitHub Actions.

O GitHub Actions dispara este script um pouco ANTES da meia-noite (via cron
no workflow). O script então:
  1. Lê as reservas pendentes (do arquivo reservations.json versionado no repo)
  2. Faz login no TownSq com antecedência (para não perder tempo na hora H)
  3. Fica em espera ativa até 00:00:00 do horário de Brasília
  4. No instante exato, dispara as tentativas de reserva
  5. Marca reservas pontuais bem-sucedidas como "reservado" no JSON, para
     não tentar de novo nas próximas execuções

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

RESERVATIONS_FILE = Path(__file__).parent.parent / "reservations.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("gh_runner")


DIAS_SEMANA_PT = {
    "segunda": 0, "terça": 1, "terca": 1, "quarta": 2, "quinta": 3,
    "sexta": 4, "sabado": 5, "sábado": 5, "domingo": 6,
}


def carregar_dados():
    if not RESERVATIONS_FILE.exists():
        logger.warning(f"Arquivo {RESERVATIONS_FILE} não encontrado.")
        return {"reservas": [], "regras_recorrentes": []}
    with open(RESERVATIONS_FILE, encoding="utf-8") as f:
        return json.load(f)


def salvar_dados(dados):
    with open(RESERVATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def calcular_abertura_date():
    # O cron dispara às 23:40 do dia ANTERIOR à meia-noite que importa.
    # Ex: dispara segunda 23:40, espera, e a "abertura" que acontece de fato
    # é à meia-noite de terça. Por isso usamos hoje+1 (amanhã) como a data
    # de abertura de verdade, não a data de hoje em que o cron disparou.
    # Caso raro: se o GitHub atrasou tanto que o script só começou já depois
    # da meia-noite, "hoje" já É o dia de abertura (não precisa +1).
    agora = datetime.now(BRASILIA)
    hoje = agora.date()
    return hoje if agora.hour == 0 else hoje + timedelta(days=1)


def montar_pendentes(dados, abertura_date):
    """
    Retorna lista de reservas a tentar hoje. Cada item inclui 'origem' para
    sabermos, depois, se/como atualizar o status no JSON:
      ("pontual", índice na lista dados["reservas"])
      ("recorrente", None)  — regras recorrentes nunca "terminam", então
                              não marcamos como concluídas.
    """
    pendentes = []

    # 1) Reservas pontuais — dispara se a janela já abriu (hoje ou antes) e
    #    ainda não foi marcada como concluída. Isso cobre tanto o caso normal
    #    (abre exatamente hoje) quanto casos de recuperação (cron falhou
    #    ontem, ou a instrução foi cadastrada depois que a janela já tinha
    #    aberto).
    for i, r in enumerate(dados.get("reservas", [])):
        if r.get("status") != "agendado":
            continue
        data_desejada = datetime.strptime(r["data_desejada"], "%Y-%m-%d").date()
        momento_abertura = data_desejada - timedelta(days=r["dias_antecedencia_abertura"])
        if momento_abertura <= abertura_date:
            pendentes.append({
                "quadra": r["quadra"],
                "data_desejada": r["data_desejada"],
                "horario_desejado": r["horario_desejado"],
                "origem": ("pontual", i),
            })

    # 2) Regras recorrentes (toda semana no mesmo dia da semana)
    for regra in dados.get("regras_recorrentes", []):
        if regra.get("status") != "ativo":
            continue
        dia_semana_alvo = DIAS_SEMANA_PT.get(regra["dia_semana"].lower())
        if dia_semana_alvo is None:
            logger.warning(f"dia_semana inválido na regra recorrente: {regra['dia_semana']!r}")
            continue
        data_alvo = abertura_date + timedelta(days=regra["dias_antecedencia_abertura"])
        if data_alvo.weekday() == dia_semana_alvo:
            pendentes.append({
                "quadra": regra["quadra"],
                "data_desejada": data_alvo.strftime("%Y-%m-%d"),
                "horario_desejado": regra["horario"],
                "origem": ("recorrente", None),
            })

    return pendentes


def esperar_ate_meia_noite():
    """Espera (com precisão) até 00:00:00 de Brasília. Se já passou, retorna já."""
    agora = datetime.now(BRASILIA)
    proxima_meia_noite = (agora + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    if agora.hour == 0:
        logger.info("Já passou da meia-noite (cron pode ter atrasado). Disparando imediatamente.")
        return

    segundos_ate = (proxima_meia_noite - agora).total_seconds()
    if segundos_ate > 900:
        logger.warning(f"Faltam {segundos_ate:.0f}s até meia-noite (muito). Esperando mesmo assim.")

    logger.info(f"Aguardando {segundos_ate:.1f}s até a meia-noite de Brasília ({proxima_meia_noite})...")
    while True:
        restante = (proxima_meia_noite - datetime.now(BRASILIA)).total_seconds()
        if restante <= 0:
            break
        time.sleep(min(restante, 1))
    logger.info("Meia-noite! Disparando tentativas de reserva.")


def executar():
    dados = carregar_dados()
    abertura_date = calcular_abertura_date()
    pendentes = montar_pendentes(dados, abertura_date)

    if not pendentes:
        logger.info("Nenhuma reserva pendente para hoje. Encerrando.")
        return

    logger.info(f"{len(pendentes)} reserva(s) pendente(s) para hoje.")
    houve_mudanca = False

    with criar_cliente_do_env() as client:
        client.login()

        for reserva in pendentes:
            client.navegar_para_reserva_quadra(reserva["quadra"])

        esperar_ate_meia_noite()

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
                continue

            # Marca reservas pontuais bem-sucedidas como concluídas, para
            # não tentar de novo na próxima execução.
            tipo, indice = reserva["origem"]
            if tipo == "pontual":
                dados["reservas"][indice]["status"] = "reservado"
                houve_mudanca = True

    if houve_mudanca:
        salvar_dados(dados)
        logger.info("reservations.json atualizado com o resultado das reservas pontuais.")


if __name__ == "__main__":
    executar()
