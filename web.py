from flask import Flask, render_template, jsonify, request
import paho.mqtt.client as mqtt
import threading
import time
import subprocess

app = Flask(__name__)

# --- STAV SYSTÉMU ---
system_state = {
    "selected_index": 0,
    "message": "Načítám...",
    "connection": "OFFLINE", # Nový stav pro web
    "last_action": None
}

MENU_ITEMS = [
    {"id": 0, "label": "MÁM ŽÍZEŇ", "icon": "fa-glass-water", "color": "primary", "speech": "Mám žízeň, prosím vodu."},
    {"id": 1, "label": "MÁM HLAD", "icon": "fa-utensils", "color": "warning", "speech": "Mám hlad."},
    {"id": 2, "label": "SVĚTLO", "icon": "fa-lightbulb", "color": "success", "speech": "Přepínám světlo.", "type": "zigbee"},
    {"id": 3, "label": "POTŘEBUJI POMOC", "icon": "fa-hand-holding-medical", "color": "danger", "speech": "Prosím, pojďte sem, potřebuji pomoc!"}
]

def on_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload = msg.payload.decode()
        
        # 1. Zpracování STAVU (z ble_bridge)
        if topic == "joystick/status":
            print(f"Nový stav připojení: {payload}")
            system_state["connection"] = payload
            
        # 2. Zpracování PŘÍKAZŮ (z joysticku)
        elif topic == "joystick/command":
            print(f"Příkaz: {payload}")
            if payload == "UP" or payload == "LEFT":
                system_state["selected_index"] = (system_state["selected_index"] - 1) % len(MENU_ITEMS)
            elif payload == "DOWN" or payload == "RIGHT":
                system_state["selected_index"] = (system_state["selected_index"] + 1) % len(MENU_ITEMS)
            elif payload == "SELECT":
                trigger_action(system_state["selected_index"])
                
    except Exception as e:
        print(f"Chyba MQTT: {e}")

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_message = on_message

def start_mqtt():
    try:
        mqtt_client.connect("localhost", 1883, 60)
        # Odebíráme vše pod joystick/ (tedy command i status)
        mqtt_client.subscribe("joystick/#")
        mqtt_client.loop_forever()
    except Exception as e:
        print(f"Chyba MQTT: {e}")

def trigger_action(index):
    item = MENU_ITEMS[index]
    system_state["message"] = f"Aktivováno: {item['label']}"
    system_state["last_action"] = time.time()
    threading.Thread(target=speak, args=(item['speech'],)).start()

def speak(text):
    try: subprocess.run(['espeak-ng', '-v', 'cs', text])
    except: pass

@app.route('/')
def index():
    return render_template('index.html', menu=MENU_ITEMS)

@app.route('/api/status')
def get_status():
    return jsonify(system_state)

@app.route('/api/click/<int:item_id>', methods=['POST'])
def web_click(item_id):
    trigger_action(item_id)
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    threading.Thread(target=start_mqtt, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=False)
