"""
Consulta os horários disponíveis da Quadra de Tênis num dia específico e
salva o resultado como JSON em `horarios_disponiveis/{data}.json`.

Rodado pelo workflow `.github/workflows/consultar_horarios.yml`, disparado
pelo painel Streamlit quando o usuário quer ver os horários livres de uma
data antes de agendar uma reserva pontual.

Uso:
    DATA=2026-08-15 python scraper/consultar_horarios.py
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).parent))
from townsq_client import criar_cliente_do_env

OUTPUT_DIR = Path(__file__).parent.parent / "horarios_disponiveis"


def main():
    data_str = os.environ["DATA"]  # formato YYYY-MM-DD
    data_desejada = datetime.strptime(data_str, "%Y-%m-%d").date()
    mes_ano = data_desejada.strftime("%m-%Y")

    resultado = {"data": data_str, "horarios": [], "erro": None}

    try:
        with criar_cliente_do_env() as client:
            client.login()
            client.navegar_para_reserva_quadra("Quadra de Tênis", mes_ano=mes_ano)
            horarios = client.listar_horarios_disponiveis(data_desejada)
            resultado["horarios"] = horarios
    except Exception as e:
        resultado["erro"] = str(e)

    OUTPUT_DIR.mkdir(exist_ok=True)
    caminho = OUTPUT_DIR / f"{data_str}.json"
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    print(f"Resultado salvo em {caminho}")
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
