from flask import Flask, render_template, jsonify
import paho.mqtt.client as mqtt
import json
import time
import numpy as np  # 파일 상단에 추가
app = Flask(__name__)

# MQTT 설정
broker = "monetgpu1.duckdns.org"
port = 1883
topic = "esp32uwb/#"  # 모든 하위 토픽 구독

# 각 앵커의 최신 데이터를 저장하는 딕셔너리
latest_data = {}

# 고정된 앵커 위치 (물리 좌표, 단위: 미터)
anchor_positions = {
    "ANC7": (4.3, 0),
    "ANC2": (4.3, 5.85),
    "ANC4": (11.55, 3.0),
    "ANC6": (7.05, 0)
}



def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8")
    print(f"Received from {msg.topic}: {payload}")
    try:
        data = json.loads(payload)
        anchor_id = data.get("anchor_id")
        # 앵커 ID 조건: ANC0, ANC2, ANC4, ANC6
        if anchor_id in ["ANC7", "ANC2", "ANC4", "ANC6"]:
            latest_data[anchor_id] = {
                "anchor_id": anchor_id,
                "distance": data.get("distance"),
                "timestamp": time.time()
            }
    except json.JSONDecodeError:
        print("Invalid JSON format")


client = mqtt.Client()
client.on_message = on_message


def connect_mqtt():
    while True:
        try:
            print("Attempting to connect to MQTT broker...")
            client.connect(broker, port)
            print("Connected to MQTT broker")
            break
        except Exception as e:
            print(f"Connection failed: {e}")
            time.sleep(5)


connect_mqtt()
client.subscribe(topic)
client.loop_start()


def compute_tag_position():
    # 4 앵커(ANC0, ANC2, ANC4, ANC6)의 데이터가 모두 있어야 계산 가능
    if not all(anchor in latest_data for anchor in ["ANC7", "ANC2", "ANC4", "ANC6"]):
        return None
    try:
        anchors = ["ANC7", "ANC2", "ANC4", "ANC6"]
        distances = [float(latest_data[a]["distance"]) for a in anchors]
        positions = [anchor_positions[a] for a in anchors]

        # 기준 앵커(ANC0) 설정
        x0, y0 = positions[0]
        r0 = distances[0]

        A = []
        b = []
        # 나머지 앵커(ANC2, ANC4, ANC6)에 대해 선형 방정식 구성
        for i in range(1, 4):
            xi, yi = positions[i]
            ri = distances[i]
            A.append([-2 * (xi - x0), -2 * (yi - y0)])
            b.append(ri ** 2 - r0 ** 2 - (xi ** 2 - x0 ** 2) - (yi ** 2 - y0 ** 2))

        A = np.array(A)
        b = np.array(b)

        # 최소제곱법으로 해 구하기
        sol, residuals, rank, s = np.linalg.lstsq(A, b, rcond=None)
        x, y = sol[0], sol[1]

        return {"x": x, "y": y}
    except Exception as e:
        print(f"Error in trilateration: {e}")
        return None


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/data")
def get_data():
    tag_position = compute_tag_position()
    return jsonify({
        "anchors": latest_data,
        "tag": tag_position,
        "anchor_positions": anchor_positions
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)