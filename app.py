import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from influxdb_client import InfluxDBClient
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
from agent import ai_decision
from streamlit_autorefresh import st_autorefresh

# Ładowanie .env
load_dotenv()

# Konfiguracja aplikacji
st.set_page_config(page_title="Lux Monitoring & AI Agent", layout="wide")
st.title("💡 Monitorowanie oświetlenia i agent AI")

# Auto-refresh co 30s jeśli agent włączony
if st.session_state.get("auto_agent", False):
    st_autorefresh(interval=30_000, limit=100, key="auto_refresh")

# Zmienne środowiskowe
INFLUXDB_URL = st.secrets["INFLUXDB_URL"]
INFLUXDB_TOKEN = st.secrets["INFLUXDB_TOKEN"]
INFLUXDB_ORG = st.secrets["INFLUXDB_ORG"]
INFLUXDB_BUCKET = st.secrets["INFLUXDB_BUCKET", "ESP32"]

# Sprawdzenie połączenia
if not all([INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, INFLUXDB_BUCKET]):
    st.error("Brakuje zmiennych środowiskowych!")
    st.stop()

try:
    client = InfluxDBClient(
        url=INFLUXDB_URL,
        token=INFLUXDB_TOKEN,
        org=INFLUXDB_ORG
    )
except Exception as e:
    st.error(f"Błąd połączenia z InfluxDB: {e}")
    st.stop()

# Funkcja pobierająca dane lux
def query_lux_data(start_time, end_time):
    query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
        |> range(start: {start_time}, stop: {end_time})
        |> filter(fn: (r) => r["_measurement"] == "agent_lux")
        |> filter(fn: (r) => r["_field"] == "lux")
        |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
        |> yield(name: "mean")
    '''
    try:
        df = client.query_api().query_data_frame(query)
        if not df.empty:
            df['_time'] = pd.to_datetime(df['_time'])
            return df[['_time', '_value']].rename(columns={'_value': 'lux'})
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Błąd pobierania danych lux: {e}")
        return pd.DataFrame()

# Zakres czasu
st.sidebar.header("📅 Zakres czasu")
time_range = st.sidebar.selectbox(
    "Zakres:",
    ["godzina", "24 godziny", "7 dni", "30 dni"]
)

now = datetime.utcnow()
if time_range == "godzina":
    start_time = now - timedelta(hours=1)
elif time_range == "24 godziny":
    start_time = now - timedelta(days=1)
elif time_range == "7 dni":
    start_time = now - timedelta(days=7)
else:
    start_time = now - timedelta(days=30)
end_time = now

# Pobranie danych
df_lux = query_lux_data(start_time.isoformat() + "Z", end_time.isoformat() + "Z")

# Wykres
st.subheader("📈 Natężenie oświetlenia (lux)")
if not df_lux.empty:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_lux['_time'], y=df_lux['lux'],
                             mode='lines+markers', name='lux'))
    fig.update_layout(
        title="Oświetlenie w czasie",
        xaxis_title="Czas",
        yaxis_title="Lux",
        template="plotly_white"
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("Brak danych do wykresu.")

# Sterowanie agentem ręcznie
st.subheader("🧠 Wysteruj agenta AI ręcznie")
if not df_lux.empty:
    model_option = st.selectbox(
        "Model AI:",
        (
            "microsoft/mai-ds-r1:free",
            "gpt-3.5-turbo",
            "opengvlab/internvl3-14b:free"
        ),
        key="lux_model_select"
    )

    num_records = st.slider(
        "Ile ostatnich pomiarów analizować?",
        min_value=1,
        max_value=min(30, len(df_lux)),
        step=5,
        value=5,
        key="lux_num_records"
    )

    if st.button("🚀 Wysteruj agenta AI"):
        decision, reason = ai_decision(df_lux, model_option, num_records)
        st.success(f"✅ Decyzja: **{decision}**")
        st.markdown(f"📌 Uzasadnienie: {reason}")
else:
    st.info("Brak danych – nie można wysterować agenta.")

# Tryb automatyczny
st.subheader("🔁 Agent niezależny (automatyczny tryb)")
if "auto_agent" not in st.session_state:
    st.session_state["auto_agent"] = False

col1, col2 = st.columns(2)
if not st.session_state["auto_agent"]:
    if col1.button("✅ Pozwól agentowi działać niezależnie"):
        st.session_state["auto_agent"] = True
        st.success("Agent aktywowany.")
else:
    if col2.button("⛔ Zatrzymaj agenta"):
        st.session_state["auto_agent"] = False
        st.warning("Agent zatrzymany.")

# Działanie agenta automatycznie co 30s
if st.session_state["auto_agent"]:
    st.info("Agent działa niezależnie – analizuje dane co 30 sekund.")
    if not df_lux.empty:
        decision, reason = ai_decision(df_lux, model_name="gpt-3.5-turbo", num_records=1)
        st.success(f"🧠 Decyzja automatyczna: **{decision}**")
        st.caption(f"📌 Uzasadnienie: {reason}")
    else:
        st.warning("Brak danych do analizy.")
