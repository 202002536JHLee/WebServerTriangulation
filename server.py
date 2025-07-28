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

# 칼만 필터 정의
class KalmanFilter:
    def __init__(self, trust=0.5):
        self.value = None
        self.trust = trust

    def update(self, measured):
        if self.value is None:
            self.value = measured
        else:
            self.value += self.trust * (measured - self.value)
        return self.value

kf_x = KalmanFilter()
kf_y = KalmanFilter()

# 태그 위치 계산 함수
def compute_tag_position():
    if not all(a in latest_data for a in anchor_positions):
        return None
    anchors = list(anchor_positions.keys())
    distances = [latest_data[a]["distance"] for a in anchors]
    coords = [anchor_positions[a] for a in anchors]

    # 기준 앵커
    x0, y0 = coords[0]
    r0 = distances[0]

    # Ax = b 형태로 변환
    A = []
    b = []
    for (xi, yi), ri in zip(coords[1:], distances[1:]):
        A.append([-2*(xi-x0), -2*(yi-y0)])
        b.append(ri**2 - r0**2 - (xi**2 - x0**2) - (yi**2 - y0**2))
    A = np.array(A)
    b = np.array(b)

    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    x_raw, y_raw = sol[0], sol[1]

    # 칼만 필터 적용
    x_f = kf_x.update(x_raw)
    y_f = kf_y.update(y_raw)
    return {"x": x_f, "y": y_f}

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
        INSERT INTO test_fingerprinting (
            rssi_anc0, rssi_anc2, rssi_anc4, rssi_anc6,
            distance_anc0, distance_anc2, distance_anc4, distance_anc6,
            tag_position, timestamp
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """

        def get_val(a, key):
            return latest_data.get(a, {}).get(key, None)

        # 태그 위치는 하드코딩 (실제 위치)
        placeholder = json.dumps({"x": 11.25, "y": 4.95})

        cur.execute(sql, (
            get_val("ANC0", "rssi"),
            get_val("ANC2", "rssi"),
            get_val("ANC4", "rssi"),
            get_val("ANC6", "rssi"),
            get_val("ANC0", "distance"),
            get_val("ANC2", "distance"),
            get_val("ANC4", "distance"),
            get_val("ANC6", "distance"),
            placeholder,
            datetime.now()
        ))

        conn.commit()
        cur.close()
        conn.close()
        print("[DB] 1초 주기 저장 완료")
    except Exception as e:
        print("[DB ERROR]", e)

# 1초 주기 자동 저장 스레드
def auto_save_loop():
    while True:
        if latest_data:
            insert_to_db()
        time.sleep(0.5)

# Flask 기본 페이지
@app.route("/")
def index():
    return render_template("index.html")

# 데이터 반환 API
@app.route("/data")
def get_data():
    return jsonify({
        "anchors": latest_data,
        "tag": compute_tag_position(),
        "anchor_positions": anchor_positions
    })

if __name__ == "__main__":
    threading.Thread(target=auto_save_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
