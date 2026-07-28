"""
Tenta reservar AGORA MESMO (sem esperar meia-noite) — usado quando a janela
de reserva já está aberta e o usuário quer garantir o horário na hora, em
vez de agendar para a próxima abertura.

Rodado pelo workflow `.github/workflows/reservar_agora.yml`, disparado pelo
painel Streamlit.

Uso:
    DATA=2026-08-03 HORARIO="07:00 - 08:00" CHAVE=abc123 python scraper/reservar_agora.py
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).parent))
from townsq_client import criar_cliente_do_env

OUTPUT_DIR = Path(__file__).parent.parent / "resultados_reservas"

MAX_TENTATIVAS = 10
INTERVALO_ENTRE_TENTATIVAS_SEGUNDOS = 2


def main():
    data_str = os.environ["DATA"]
    horario = os.environ["HORARIO"]
    chave = os.environ["CHAVE"]
    data_desejada = datetime.strptime(data_str, "%Y-%m-%d").date()
    mes_ano = data_desejada.strftime("%m-%Y")

    resultado = {
        "data": data_str,
        "horario_desejado": horario,
        "sucesso": False,
        "erro": None,
        "tentativas": 0,
    }

    try:
        with criar_cliente_do_env() as client:
            client.login()
            client.navegar_para_reserva_quadra("Quadra de Tênis", mes_ano=mes_ano)

            for tentativa in range(1, MAX_TENTATIVAS + 1):
                resultado["tentativas"] = tentativa
                ok = client.tentar_reservar(data_desejada, horario)
                if ok:
                    resultado["sucesso"] = True
                    break
                time.sleep(INTERVALO_ENTRE_TENTATIVAS_SEGUNDOS)
                client.recarregar_pagina_reserva()
    except Exception as e:
        resultado["erro"] = str(e)

    OUTPUT_DIR.mkdir(exist_ok=True)
    caminho = OUTPUT_DIR / f"{chave}.json"
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    print(f"Resultado salvo em {caminho}")
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
