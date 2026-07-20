"""
Camada de persistência simples usando SQLite.
Guarda:
  - reservations: os pedidos de reserva que o usuário configurou no painel
  - logs: histórico de tentativas (sucesso/erro) de cada execução do bot
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "bookings.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quadra TEXT NOT NULL,
                dia_semana_desejado TEXT NOT NULL,     -- ex: "Sábado"
                horario_desejado TEXT NOT NULL,        -- ex: "10:00"
                data_desejada TEXT,                    -- data concreta calculada, ex: "2026-08-01"
                dias_antecedencia_abertura INTEGER NOT NULL, -- quantos dias antes a reserva abre
                hora_abertura TEXT NOT NULL,           -- horário em que a janela de reserva libera, ex: "00:00"
                status TEXT NOT NULL DEFAULT 'agendado', -- agendado | executando | sucesso | falha | cancelado
                criado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER,
                timestamp TEXT NOT NULL,
                mensagem TEXT NOT NULL,
                nivel TEXT NOT NULL DEFAULT 'INFO'  -- INFO | ERRO | SUCESSO
            )
        """)


def add_reservation(quadra, dia_semana_desejado, horario_desejado,
                     data_desejada, dias_antecedencia_abertura, hora_abertura):
    now = datetime.now().isoformat()
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO reservations
            (quadra, dia_semana_desejado, horario_desejado, data_desejada,
             dias_antecedencia_abertura, hora_abertura, status, criado_em, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?, 'agendado', ?, ?)
        """, (quadra, dia_semana_desejado, horario_desejado, data_desejada,
              dias_antecedencia_abertura, hora_abertura, now, now))
        return cur.lastrowid


def list_reservations():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM reservations ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


def update_status(reservation_id, status):
    with get_conn() as conn:
        conn.execute(
            "UPDATE reservations SET status = ?, atualizado_em = ? WHERE id = ?",
            (status, datetime.now().isoformat(), reservation_id)
        )


def delete_reservation(reservation_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM reservations WHERE id = ?", (reservation_id,))


def add_log(reservation_id, mensagem, nivel="INFO"):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO logs (reservation_id, timestamp, mensagem, nivel) VALUES (?, ?, ?, ?)",
            (reservation_id, datetime.now().isoformat(), mensagem, nivel)
        )


def list_logs(reservation_id=None, limit=200):
    with get_conn() as conn:
        if reservation_id:
            rows = conn.execute(
                "SELECT * FROM logs WHERE reservation_id = ? ORDER BY id DESC LIMIT ?",
                (reservation_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
