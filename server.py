from flask import Flask, render_template, jsonify
import paho.mqtt.client as mqtt
import json
import time

app = Flask(__name__)

# MQTT 설정
broker = "168.188.126.168"
port = 1883
topic = "esp32uwb/#"  # 모든 하위 토픽 구독

# 각 앵커의 최신 데이터를 저장하는 딕셔너리
latest_data = {}

# 고정된 앵커 위치 (물리 좌표, 단위: 미터)
anchor_positions = {
    "ANC3": (7.05, 5.85),
    "ANC4": (11.55, 2.9),
    "ANC6": (7.05, 0)
}


def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8")
    print(f"Received from {msg.topic}: {payload}")
    try:
        data = json.loads(payload)
        anchor_id = data.get("anchor_id")
        distance = data.get("distance")
        if anchor_id in ["ANC3", "ANC4", "ANC6"]:
            latest_data[anchor_id] = {
                "anchor_id": anchor_id,
                "distance": distance,
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
    # 세 앵커의 데이터가 모두 있어야 계산 가능
    if not all(anchor in latest_data for anchor in ["ANC3", "ANC4", "ANC6"]):
        return None
    try:
        r1 = float(latest_data["ANC3"]["distance"])
        r2 = float(latest_data["ANC4"]["distance"])
        r3 = float(latest_data["ANC6"]["distance"])

        (x1, y1) = anchor_positions["ANC3"]
        (x2, y2) = anchor_positions["ANC4"]
        (x3, y3) = anchor_positions["ANC6"]

        # 두 개의 원 방정식을 빼서 선형 방정식으로 변환
        A = 2 * (x2 - x1)
        B = 2 * (y2 - y1)
        C = r1 ** 2 - r2 ** 2 - (x1 ** 2 - x2 ** 2) - (y1 ** 2 - y2 ** 2)

        D = 2 * (x3 - x1)
        E = 2 * (y3 - y1)
        F = r1 ** 2 - r3 ** 2 - (x1 ** 2 - x3 ** 2) - (y1 ** 2 - y3 ** 2)

        denom = A * E - B * D
        if abs(denom) < 1e-6:
            return None

        x = (C * E - B * F) / denom
        y = (A * F - C * D) / denom

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