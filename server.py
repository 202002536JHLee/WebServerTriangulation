from flask import Flask, render_template, jsonify
import paho.mqtt.client as mqtt
import json
import time
import numpy as np
import psycopg2
from datetime import datetime
import threading

app = Flask(__name__)

# MQTT 설정
broker = "monetgpu1.duckdns.org"
port = 1883
topic = "esp32uwb/#"

latest_data = {}

# 앵커 좌표
anchor_positions = {
    "ANC0": (0.54,  1.4),
    "ANC2": (4.3,   5.85),
    "ANC4": (11.55, 2.7),
    "ANC6": (7.05,  0.0)
}

# MQTT 메시지 수신 처리
def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        aid = data.get("anchor_id")
        if aid in anchor_positions:
            latest_data[aid] = {
                "distance": float(data.get("distance")),
                "rssi": float(data.get("rssi")),
                "timestamp": time.time()
            }
    except Exception:
        pass

client = mqtt.Client()
client.on_message = on_message

def connect_mqtt():
    while True:
        try:
            client.connect(broker, port)
            client.subscribe(topic)
            client.loop_start()
            break
        except Exception:
            time.sleep(5)

connect_mqtt()

# PostgreSQL 저장 함수
def insert_to_db():
    try:
        conn = psycopg2.connect(
            host="168.188.128.82",
            port=5432,
            dbname="ljh_uwb",
            user="gpuadmin",
            password="monet1234"
        )
        cur = conn.cursor()

        sql = """
        INSERT INTO fingerprinting (
            rssi_anc0, rssi_anc2, rssi_anc4, rssi_anc6,
            distance_anc0, distance_anc2, distance_anc4, distance_anc6,
            tag_position, timestamp
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """

        def get_val(a, key):
            return latest_data.get(a, {}).get(key, None)

        cur.execute(sql, (
            get_val("ANC0", "rssi"),
            get_val("ANC2", "rssi"),
            get_val("ANC4", "rssi"),
            get_val("ANC6", "rssi"),
            get_val("ANC0", "distance"),
            get_val("ANC2", "distance"),
            get_val("ANC4", "distance"),
            get_val("ANC6", "distance"),
            json.dumps({"x": 0, "y": 0}),
            datetime.now()
        ))

        conn.commit()
        cur.close()
        conn.close()
        print("[DB] 1초 주기 저장 완료")
    except Exception as e:
        print("[DB ERROR]", e)

# ✅ 1초 주기 자동 저장 스레드
def auto_save_loop():
    while True:
        if latest_data:  # 데이터가 존재할 때만 저장
            insert_to_db()
        time.sleep(1)  # 1초 간격

# Flask 기본 페이지
@app.route("/")
def index():
    return render_template("index.html")

# 데이터 반환 API
@app.route("/data")
def get_data():
    return jsonify({
        "anchors": latest_data,
        "tag": None,
        "anchor_positions": anchor_positions
    })

if __name__ == "__main__":
    # ✅ 백그라운드 저장 스레드 시작
    threading.Thread(target=auto_save_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
