"""
Painel Streamlit — Reserva Automática de Quadra de Tênis (TownSq)

Este painel lê e grava o arquivo `reservations.json` DIRETO no seu
repositório do GitHub (via API), então qualquer alteração feita aqui já
vale para a próxima execução do robô (GitHub Actions), sem precisar editar
o JSON manualmente.

Rodar localmente:
    streamlit run app.py

Configuração necessária (Streamlit secrets — veja README.md):
    GITHUB_TOKEN = "seu_token_com_permissao_contents_read_write"
    GITHUB_REPO  = "usuario/repositorio"   # ex: "fernandorodrigues82-debug/reservaquadra"
"""
import base64
import json
from datetime import datetime, timedelta

import requests
import streamlit as st

st.set_page_config(page_title="Reserva Automática de Quadra", page_icon="🎾", layout="centered")

GITHUB_API = "https://api.github.com"
DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sabado", "domingo"]


def get_config():
    token = st.secrets.get("GITHUB_TOKEN")
    repo = st.secrets.get("GITHUB_REPO")
    if not token or not repo:
        st.error(
            "Faltam configurar os secrets do Streamlit: GITHUB_TOKEN e GITHUB_REPO. "
            "Veja o README.md para instruções."
        )
        st.stop()
    return token, repo


def github_headers(token):
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


@st.cache_data(ttl=10, show_spinner=False)
def carregar_reservations_json(_token, repo):
    resp = requests.get(
        f"{GITHUB_API}/repos/{repo}/contents/reservations.json",
        headers=github_headers(_token),
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    conteudo = base64.b64decode(data["content"]).decode("utf-8")
    return json.loads(conteudo), data["sha"]


def salvar_reservations_json(token, repo, dados, sha, mensagem):
    conteudo_b64 = base64.b64encode(
        json.dumps(dados, ensure_ascii=False, indent=2).encode("utf-8")
    ).decode("utf-8")
    resp = requests.put(
        f"{GITHUB_API}/repos/{repo}/contents/reservations.json",
        headers=github_headers(token),
        json={"message": mensagem, "content": conteudo_b64, "sha": sha},
        timeout=15,
    )
    resp.raise_for_status()
    st.cache_data.clear()


token, repo = get_config()

st.title("🎾 Reserva Automática de Quadra de Tênis")
st.caption(f"Conectado ao repositório: `{repo}`")

try:
    dados, sha = carregar_reservations_json(token, repo)
except Exception as e:
    st.error(f"Erro ao carregar reservations.json do GitHub: {e}")
    st.stop()

dados.setdefault("regras_recorrentes", [])
dados.setdefault("reservas", [])

tab_recorrente, tab_pontual = st.tabs(["🔁 Regra recorrente (toda semana)", "📅 Reserva pontual (data única)"])

# ---------------------------------------------------------------------------
# ABA 1 — Regras recorrentes
# ---------------------------------------------------------------------------
with tab_recorrente:
    st.subheader("Regras ativas")
    if not dados["regras_recorrentes"]:
        st.info("Nenhuma regra recorrente cadastrada ainda.")
    for i, regra in enumerate(dados["regras_recorrentes"]):
        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(
                    f"**{regra['quadra']}** — toda **{regra['dia_semana']}**, "
                    f"horário: **{regra['horario']}**"
                )
                st.caption(
                    f"Abre {regra['dias_antecedencia_abertura']} dias antes, à meia-noite · "
                    f"Status: {'✅ ativo' if regra['status'] == 'ativo' else '⏸️ pausado'}"
                )
            with col2:
                if regra["status"] == "ativo":
                    if st.button("Pausar", key=f"pausar_{i}", use_container_width=True):
                        dados["regras_recorrentes"][i]["status"] = "pausado"
                        salvar_reservations_json(token, repo, dados, sha, f"Pausa regra recorrente #{i}")
                        st.rerun()
                else:
                    if st.button("Ativar", key=f"ativar_{i}", use_container_width=True):
                        dados["regras_recorrentes"][i]["status"] = "ativo"
                        salvar_reservations_json(token, repo, dados, sha, f"Ativa regra recorrente #{i}")
                        st.rerun()
                if st.button("🗑️ Excluir", key=f"excluir_regra_{i}", use_container_width=True):
                    dados["regras_recorrentes"].pop(i)
                    salvar_reservations_json(token, repo, dados, sha, f"Remove regra recorrente #{i}")
                    st.rerun()

    st.divider()
    st.subheader("Nova regra recorrente")
    with st.form("nova_regra", clear_on_submit=True):
        quadra = st.text_input("Nome da quadra (exatamente como aparece no TownSq)", value="Quadra de Tênis")
        dia_semana = st.selectbox("Dia da semana desejado", DIAS_SEMANA, index=1)
        tipo_horario = st.radio(
            "Horário", ["Primeiro horário disponível", "Horário fixo"], horizontal=True
        )
        horario_fixo = None
        if tipo_horario == "Horário fixo":
            horario_fixo = st.text_input(
                "Horário exato (formato igual ao TownSq)", placeholder="ex: 10:00 - 11:00"
            )
        dias_antecedencia = st.number_input(
            "Reserva abre quantos dias antes?", min_value=1, max_value=60, value=7
        )

        if st.form_submit_button("Adicionar regra recorrente", use_container_width=True):
            horario_final = "primeiro_disponivel" if tipo_horario == "Primeiro horário disponível" else horario_fixo
            if tipo_horario == "Horário fixo" and not horario_fixo:
                st.error("Informe o horário fixo desejado.")
            else:
                dados["regras_recorrentes"].append({
                    "quadra": quadra,
                    "dia_semana": dia_semana,
                    "horario": horario_final,
                    "dias_antecedencia_abertura": int(dias_antecedencia),
                    "status": "ativo",
                })
                salvar_reservations_json(token, repo, dados, sha, "Adiciona nova regra recorrente")
                st.success("Regra adicionada!")
                st.rerun()

# ---------------------------------------------------------------------------
# ABA 2 — Reservas pontuais
# ---------------------------------------------------------------------------
with tab_pontual:
    st.subheader("Reservas pontuais agendadas")
    if not dados["reservas"]:
        st.info("Nenhuma reserva pontual agendada ainda.")
    for i, r in enumerate(dados["reservas"]):
        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{r['quadra']}** — {r['data_desejada']} às **{r['horario_desejado']}**")
                st.caption(
                    f"Abre {r['dias_antecedencia_abertura']} dias antes · "
                    f"Status: {'✅ agendado' if r['status'] == 'agendado' else '❌ cancelado'}"
                )
            with col2:
                if r["status"] == "agendado":
                    if st.button("Cancelar", key=f"cancelar_{i}", use_container_width=True):
                        dados["reservas"][i]["status"] = "cancelado"
                        salvar_reservations_json(token, repo, dados, sha, f"Cancela reserva pontual #{i}")
                        st.rerun()
                if st.button("🗑️ Excluir", key=f"excluir_pontual_{i}", use_container_width=True):
                    dados["reservas"].pop(i)
                    salvar_reservations_json(token, repo, dados, sha, f"Remove reserva pontual #{i}")
                    st.rerun()

    st.divider()
    st.subheader("Nova reserva pontual")
    with st.form("nova_pontual", clear_on_submit=True):
        quadra_p = st.text_input(
            "Nome da quadra", value="Quadra de Tênis", key="quadra_pontual"
        )
        data_desejada = st.date_input(
            "Data em que você quer jogar", value=datetime.now().date() + timedelta(days=7)
        )
        tipo_horario_p = st.radio(
            "Horário", ["Primeiro horário disponível", "Horário fixo"], horizontal=True, key="tipo_pontual"
        )
        horario_fixo_p = None
        if tipo_horario_p == "Horário fixo":
            horario_fixo_p = st.text_input(
                "Horário exato (formato igual ao TownSq)", placeholder="ex: 10:00 - 11:00", key="horario_pontual"
            )
        dias_antecedencia_p = st.number_input(
            "Reserva abre quantos dias antes?", min_value=1, max_value=60, value=7, key="antecedencia_pontual"
        )

        if st.form_submit_button("Agendar reserva pontual", use_container_width=True):
            horario_final_p = (
                "primeiro_disponivel" if tipo_horario_p == "Primeiro horário disponível" else horario_fixo_p
            )
            if tipo_horario_p == "Horário fixo" and not horario_fixo_p:
                st.error("Informe o horário fixo desejado.")
            else:
                dados["reservas"].append({
                    "quadra": quadra_p,
                    "data_desejada": data_desejada.strftime("%Y-%m-%d"),
                    "horario_desejado": horario_final_p,
                    "dias_antecedencia_abertura": int(dias_antecedencia_p),
                    "status": "agendado",
                })
                salvar_reservations_json(token, repo, dados, sha, "Adiciona nova reserva pontual")
                st.success("Reserva pontual agendada!")
                st.rerun()

st.divider()
with st.expander("⚠️ Como isso funciona por trás dos panos"):
    st.markdown("""
    - Este painel lê e grava `reservations.json` **direto no seu repositório GitHub**.
    - Quem executa a reserva de fato é o **GitHub Actions** (`.github/workflows/reserva.yml`),
      que dispara automaticamente todo dia às 23:40 (Brasília) e verifica se alguma
      regra ou reserva pontual "abre" naquela meia-noite.
    - Suas credenciais do TownSq ficam nos **Secrets** do repositório GitHub — nunca aparecem aqui.
    - Se quiser acompanhar os logs de cada execução, veja a aba **Actions** do GitHub.
    """)
