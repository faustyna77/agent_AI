from influxdb_client import InfluxDBClient, Point, WriteOptions

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
from datetime import datetime, timezone
import streamlit as st
import os

load_dotenv()
def ai_decision(df, model_name: str = "openai/gpt-3.5-turbo", num_records: int = 1) -> tuple[str, str]:
    import pandas as pd

    if df.empty:
        return "BRAK_DANYCH", "Brak danych wejściowych dla agenta."

    df = df.tail(num_records)
    latest_values = df.to_dict(orient="records")

    # Formatowanie danych do promptu
    formatted = "\n".join([f"{row['_time']}: {row['lux']} lux" for row in latest_values])

    prompt = f"""
Jesteś agentem sterującym oświetleniem LED w zależności od światła otoczenia.

Zasady:
- Jeśli poziom światła (lux) jest **poniżej 15** → decyzja: **LED_ON**
- Jeśli poziom światła (lux) jest **równa lub wyższa niż 15** → decyzja: **LED_OFF**

Dane z ostatnich pomiarów:
{formatted}

Na ich podstawie podejmij decyzję w formacie:
DECISION: ...
REASON: ...

Dozwolone decyzje: LED_ON, LED_OFF.
"""

    llm = ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        model=model_name,
        temperature=0.2,
    )

    response = llm.invoke([HumanMessage(content=prompt)])
    lines = response.content.splitlines()

    decision = ""
    reason = ""

    for line in lines:
        if line.upper().startswith("DECISION:"):
            decision = line.split(":", 1)[1].strip()
        elif line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()

    if decision:
        influx = InfluxDBClient(
            url=st.secrets["INFLUXDB_URL"],
            token=st.secrets["INFLUXDB_TOKEN"],
            org=st.secrets["INFLUXDB_ORG"]
        )
        write_api = influx.write_api(write_options=WriteOptions(batch_size=1))

        point = Point("ai_decisions") \
            .field("decision", decision) \
            .field("reason", reason) \
            .time(datetime.now(timezone.utc))

        write_api.write(bucket=os.getenv("INFLUXDB_BUCKET"), record=point)
        st.success("✅ Zapisano decyzję:", decision)
        st.success("📝 Uzasadnienie:", reason)
    else:
        st.error("⚠️ Nie udało się odczytać decyzji z odpowiedzi.")

    return decision, reason
