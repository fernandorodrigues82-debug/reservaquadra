"""
Painel Streamlit — Reserva Automática de Quadra de Tênis (TownSq)

Rodar localmente:
    streamlit run app.py

O painel só CADASTRA os pedidos de reserva no banco de dados.
Quem efetivamente executa as reservas no horário certo é o
scheduler/scheduler_service.py, que deve rodar em paralelo
(veja instruções no README.md).
"""
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

import storage

st.set_page_config(page_title="Reserva Automática de Quadra", page_icon="🎾", layout="centered")
storage.init_db()

st.title("🎾 Reserva Automática de Quadra de Tênis")
st.caption("Configure quando a reserva abre e o sistema tenta reservar automaticamente nesse instante.")

DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

with st.form("nova_reserva", clear_on_submit=True):
    st.subheader("Nova reserva agendada")

    col1, col2 = st.columns(2)
    with col1:
        quadra = st.text_input("Nome da quadra (como aparece no TownSq)", value="Quadra de Tênis")
        dia_semana_desejado = st.selectbox("Dia da semana desejado", DIAS_SEMANA, index=5)
    with col2:
        horario_desejado = st.time_input("Horário desejado", value=datetime.strptime("10:00", "%H:%M").time())
        data_desejada = st.date_input(
            "Data concreta desejada",
            value=datetime.now().date() + timedelta(days=7),
            help="A data real em que você quer jogar."
        )

    st.markdown("**Regra de abertura da janela de reserva**")
    col3, col4 = st.columns(2)
    with col3:
        dias_antecedencia = st.number_input(
            "Reserva abre quantos dias antes da data desejada?",
            min_value=0, max_value=60, value=7,
        )
    with col4:
        hora_abertura = st.time_input(
            "Horário em que a janela abre",
            value=datetime.strptime("00:00", "%H:%M").time(),
        )

    submitted = st.form_submit_button("Agendar reserva automática", use_container_width=True)

    if submitted:
        storage.add_reservation(
            quadra=quadra,
            dia_semana_desejado=dia_semana_desejado,
            horario_desejado=horario_desejado.strftime("%H:%M"),
            data_desejada=data_desejada.strftime("%Y-%m-%d"),
            dias_antecedencia_abertura=int(dias_antecedencia),
            hora_abertura=hora_abertura.strftime("%H:%M"),
        )
        st.success("Reserva agendada! O robô vai tentar reservar automaticamente no horário de abertura.")
        st.rerun()

st.divider()
st.subheader("Reservas agendadas")

reservas = storage.list_reservations()
if not reservas:
    st.info("Nenhuma reserva agendada ainda.")
else:
    df = pd.DataFrame(reservas)
    df_view = df[[
        "id", "quadra", "data_desejada", "horario_desejado",
        "dias_antecedencia_abertura", "hora_abertura", "status"
    ]].rename(columns={
        "id": "ID",
        "quadra": "Quadra",
        "data_desejada": "Data desejada",
        "horario_desejado": "Horário",
        "dias_antecedencia_abertura": "Antecedência (dias)",
        "hora_abertura": "Abre às",
        "status": "Status",
    })

    def cor_status(val):
        cores = {
            "agendado": "background-color: #fff3cd",
            "executando": "background-color: #cfe2ff",
            "sucesso": "background-color: #d1e7dd",
            "falha": "background-color: #f8d7da",
            "cancelado": "background-color: #e2e3e5",
        }
        return cores.get(val, "")

    st.dataframe(
        df_view.style.applymap(cor_status, subset=["Status"]),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("**Cancelar uma reserva agendada**")
    ids_agendados = [r["id"] for r in reservas if r["status"] == "agendado"]
    if ids_agendados:
        id_para_cancelar = st.selectbox("Selecione o ID", ids_agendados)
        if st.button("Cancelar reserva selecionada"):
            storage.update_status(id_para_cancelar, "cancelado")
            st.rerun()
    else:
        st.caption("Nenhuma reserva com status 'agendado' no momento.")

st.divider()
st.subheader("Logs recentes")
logs = storage.list_logs(limit=50)
if logs:
    df_logs = pd.DataFrame(logs)[["timestamp", "reservation_id", "nivel", "mensagem"]]
    df_logs.columns = ["Quando", "ID Reserva", "Nível", "Mensagem"]
    st.dataframe(df_logs, use_container_width=True, hide_index=True)
else:
    st.caption("Sem logs ainda. Os logs aparecem assim que o scheduler começar a rodar.")

st.divider()
with st.expander("⚠️ Importante: como isso funciona por trás dos panos"):
    st.markdown("""
    - Este painel **apenas cadastra** o pedido de reserva.
    - Quem executa a reserva de fato é um processo separado (`scheduler/scheduler_service.py`)
      que precisa estar rodando ao mesmo tempo (localmente ou em um servidor).
    - Suas credenciais do TownSq ficam no arquivo `.env` (nunca suba esse arquivo pro GitHub).
    - Os seletores de tela usados na automação (`scraper/townsq_client.py`) são um ponto de partida
      e quase certamente precisarão de ajuste fino — veja instruções no topo desse arquivo.
    """)
