import os
import sqlite3
import asyncio
from datetime import datetime, timezone
import requests
from icalendar import Calendar
from dotenv import load_dotenv
from telegram import Bot

# --------------------------
# Cargar variables del entorno
# --------------------------
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "TOKEN_AQUI")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "000000000"))
ICS_URL = os.getenv(
    "ICS_URL",
    "https://senati.blackboard.com/webapps/calendar/calendarFeed/TU_ID/learn.ics",
)
REMINDER_HOURS = int(os.getenv("REMINDER_HOURS", "24"))
DB_PATH = os.getenv("DB_PATH", "./bb_alerts.db")

# --------------------------
# Inicializar Bot
# --------------------------
bot = Bot(token=TELEGRAM_TOKEN)

# --------------------------
# Base de datos
# --------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS sent (
            uid TEXT PRIMARY KEY,
            sent_at TEXT
        )"""
    )
    conn.commit()
    return conn

# --------------------------
# Descargar y analizar el ICS
# --------------------------
def fetch_ics(url):
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print("❌ Error al descargar ICS:", e)
        return None

def parse_ics(ics_text):
    cal = Calendar.from_ical(ics_text)
    events = []
    for component in cal.walk():
        if component.name == "VEVENT":
            uid = str(component.get("uid"))
            summary = str(component.get("summary", "Sin título"))
            description = str(component.get("description", ""))
            dtstart = component.get("dtstart").dt
            events.append(
                {
                    "uid": uid,
                    "summary": summary,
                    "description": description,
                    "dtstart": dtstart,
                }
            )
    return events

# --------------------------
# Funciones auxiliares
# --------------------------
def should_send(event_dt, now, hours_before):
    delta = event_dt - now
    return 0 <= delta.total_seconds() <= hours_before * 3600

async def send_telegram_message(text):
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode="Markdown")
    except Exception as e:
        print("⚠️ Error al enviar mensaje:", e)

# --------------------------
# Lógica principal
# --------------------------
async def main():
    conn = init_db()
    c = conn.cursor()

    ics_text = fetch_ics(ICS_URL)
    if not ics_text:
        return

    events = parse_ics(ics_text)
    now = datetime.now(timezone.utc)

    print(f"📅 Verificando eventos dentro de {REMINDER_HOURS} horas... ({now})")

    for ev in events:
        ev_time = ev["dtstart"]
        if ev_time.tzinfo is None:
            ev_time = ev_time.replace(tzinfo=timezone.utc)

        if should_send(ev_time, now, REMINDER_HOURS):
            uid = ev["uid"]
            c.execute("SELECT 1 FROM sent WHERE uid = ?", (uid,))
            if c.fetchone():
                continue  # Ya enviado

            text = (
                f"📚 *Recordatorio Blackboard*\n\n"
                f"📝 {ev['summary']}\n"
                f"📅 {ev_time.strftime('%Y-%m-%d %H:%M %Z')}\n\n"
                f"{ev['description']}"
            )
            await send_telegram_message(text)
            c.execute(
                "INSERT INTO sent (uid, sent_at) VALUES (?, ?)",
                (uid, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            print("✅ Enviado:", ev["summary"])

    conn.close()
    print("✅ Proceso finalizado correctamente.")

if __name__ == "__main__":
    asyncio.run(main())
