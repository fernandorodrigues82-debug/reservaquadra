"""
Runner para GitHub Actions.

O GitHub Actions dispara este script BEM ANTES da meia-noite (18:00
Brasília, longe do pico de fila do GitHub por volta de 00:00 UTC). O
script então:
  1. Lê as reservas pendentes (do arquivo reservations.json versionado no repo)
  2. Se não houver nada pendente, encerra na hora — não fica de bobeira
  3. Se houver, DORME sozinho (sem abrir navegador/sessão) até pouco antes
     da meia-noite de Brasília — isso evita manter uma sessão logada aberta
     por horas à toa, e absorve atrasos grandes do agendador do GitHub
  4. Só então faz login no TownSq e espera o segundo exato da meia-noite
  5. Dispara as tentativas de reserva
  6. Marca reservas pontuais bem-sucedidas como "reservado" no JSON, para
     não tentar de novo nas próximas execuções

Por que dois estágios de espera (dormir cedo, depois esperar fino perto da
meia-noite) em vez de só confiar no horário do cron?
Porque o GitHub Actions pode atrasar o disparo do cron por HORAS (não só
minutos) em horários de pico — e o pico mais forte é logo na virada do dia
em UTC (00:00-01:00 UTC), que cai perto da meia-noite de Brasília. Disparando
bem mais cedo (18:00 Brasília / 21:00 UTC, longe desse pico) sobra margem de
sobra mesmo com atraso de várias horas, e o job dorme sem custo até a hora
certa em vez de ficar com o navegador aberto o tempo todo.
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
    #
    # Só que o GitHub Actions pode atrasar o disparo por HORAS (já vimos
    # atraso de quase 3h em dias de pico), não só minutos. Se isso empurrar
    # a execução para depois da meia-noite, "hoje" (durante a execução) já
    # É o dia de abertura — não precisa somar 1. Usamos um limiar amplo
    # (meio-dia) em vez de checar só "hora == 0", para tolerar atrasos de
    # várias horas com folga.
    agora = datetime.now(BRASILIA)
    hoje = agora.date()
    return hoje if agora.hour < 12 else hoje + timedelta(days=1)


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


def esperar_ate_horario_login(hora_login=23, minuto_login=40):
    """
    Dorme (SEM abrir navegador/sessão) até pouco antes da meia-noite, mesmo
    que o job tenha começado bem mais cedo (ex: 18:00, para dar folga
    contra atrasos grandes do agendador do GitHub). Se já passou desse
    horário (ou já é madrugada), retorna na hora, sem esperar.
    """
    agora = datetime.now(BRASILIA)
    if agora.hour < 12:
        # Já estamos de madrugada (o job começou atrasado, depois da meia-
        # noite) — não faz sentido esperar, já estamos "atrasados" mesmo.
        return
    alvo_hoje = agora.replace(hour=hora_login, minute=minuto_login, second=0, microsecond=0)
    if agora >= alvo_hoje:
        return  # já passou do horário de login hoje, segue direto

    segundos = (alvo_hoje - agora).total_seconds()
    logger.info(
        f"Job começou cedo (folga contra atraso do GitHub). "
        f"Dormindo {segundos/3600:.1f}h até {alvo_hoje} antes de logar..."
    )
    while True:
        restante = (alvo_hoje - datetime.now(BRASILIA)).total_seconds()
        if restante <= 0:
            break
        time.sleep(min(restante, 600))  # acorda a cada 10 min só para permitir logs
    logger.info("Chegou a hora de logar, iniciando o navegador.")


def esperar_ate_meia_noite():
    """Espera (com precisão) até 00:00:00 de Brasília. Se já passou, retorna já."""
    agora = datetime.now(BRASILIA)
    proxima_meia_noite = (agora + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    # Mesmo limiar amplo de calcular_abertura_date(): se já passamos da
    # meia-noite (mesmo por várias horas de atraso), dispara na hora, em
    # vez de esperar quase um dia inteiro pela PRÓXIMA meia-noite.
    if agora.hour < 12:
        logger.info("Já passou da meia-noite (cron atrasou). Disparando imediatamente.")
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


def navegar_com_retry(client, quadra, tentativas=3, espera_segundos=3):
    """
    Navega até a página da quadra, tentando de novo em caso de falha (ex:
    timeout por causa de sobrecarga do site bem na virada da meia-noite,
    quando muita gente tenta reservar ao mesmo tempo).
    """
    ultima_excecao = None
    for i in range(1, tentativas + 1):
        try:
            client.navegar_para_reserva_quadra(quadra)
            return
        except Exception as e:
            ultima_excecao = e
            logger.warning(f"Falha ao navegar até a quadra (tentativa {i}/{tentativas}): {e}")
            time.sleep(espera_segundos)
    raise ultima_excecao


def executar():
    dados = carregar_dados()
    abertura_date = calcular_abertura_date()
    pendentes = montar_pendentes(dados, abertura_date)

    if not pendentes:
        logger.info("Nenhuma reserva pendente para hoje. Encerrando.")
        return

    logger.info(f"{len(pendentes)} reserva(s) pendente(s) para hoje.")
    houve_mudanca = False

    esperar_ate_horario_login()

    with criar_cliente_do_env() as client:
        client.login()

        for reserva in pendentes:
            navegar_com_retry(client, reserva["quadra"])

        esperar_ate_meia_noite()

        for reserva in pendentes:
            data_desejada = datetime.strptime(reserva["data_desejada"], "%Y-%m-%d").date()
            try:
                navegar_com_retry(client, reserva["quadra"])
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
            except Exception as e:
                logger.error(f"❌ Erro inesperado processando {reserva['quadra']} "
                             f"{reserva['data_desejada']}: {e}")
                continue

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
