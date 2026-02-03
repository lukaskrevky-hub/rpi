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
    "connection": "SLEEP",  # Výchozí stav (než přijde první zpráva)
    "last_action": None
}

# --- DEFINICE MENU ---
MENU_ITEMS = [
    {"id": 0, "label": "MÁM ŽÍZEŇ", "icon": "fa-glass-water", "color": "primary", "speech": "Mám žízeň, prosím vodu."},
    {"id": 1, "label": "MÁM HLAD", "icon": "fa-utensils", "color": "warning", "speech": "Mám hlad."},
    {"id": 2, "label": "SVĚTLO", "icon": "fa-lightbulb", "color": "success", "speech": "Přepínám světlo.", "type": "zigbee"},
    {"id": 3, "label": "POTŘEBUJI POMOC", "icon": "fa-hand-holding-medical", "color": "danger", "speech": "Prosím, pojďte sem, potřebuji pomoc!"}
]

# --- MQTT CALLBACK ---
def on_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload = msg.payload.decode()
        
        # 1. Zpracování STAVU (z ble_bridge.py)
        if topic == "joystick/status":
            print(f"Změna stavu: {payload}")
            system_state["connection"] = payload
            
        # 2. Zpracování PŘÍKAZŮ (z joysticku)
        elif topic == "joystick/command":
            # print(f"Příkaz: {payload}") # Debug
            if payload == "UP" or payload == "LEFT":
                system_state["selected_index"] = (system_state["selected_index"] - 1) % len(MENU_ITEMS)
            elif payload == "DOWN" or payload == "RIGHT":
                system_state["selected_index"] = (system_state["selected_index"] + 1) % len(MENU_ITEMS)
            elif payload == "SELECT":
                trigger_action(system_state["selected_index"])
                
    except Exception as e:
        print(f"Chyba MQTT: {e}")

# --- MQTT SETUP ---
# Používáme VERSION2 pro novější knihovny
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_message = on_message

def start_mqtt():
    while True:
        try:
            print("Připojuji se k MQTT...")
            mqtt_client.connect("localhost", 1883, 60)
            # Odebíráme vše pod joystick/ (tedy command i status)
            mqtt_client.subscribe("joystick/#")
            mqtt_client.loop_forever()
        except Exception as e:
            print(f"Chyba MQTT (zkusím za 5s): {e}")
            time.sleep(5)

# --- FUNKCE AKCÍ ---
def trigger_action(index):
    item = MENU_ITEMS[index]
    system_state["message"] = f"Aktivováno: {item['label']}"
    system_state["last_action"] = time.time()
    
    # 1. Hlasový výstup (TTS)
    threading.Thread(target=speak, args=(item['speech'],)).start()
    
    # 2. Zigbee / IoT Akce
    if "type" in item and item["type"] == "zigbee":
        print(f"--> Zigbee akce: {item['label']}")
        # Zde bude později: mqtt_client.publish("zigbee2mqtt/zasuvka/set", '{"state":"TOGGLE"}')

def speak(text):
    try:
        subprocess.run(['espeak-ng', '-v', 'cs', text])
    except: pass

# --- FLASK WEBOVÉ CESTY (ROUTES) ---

@app.route('/')
def index():
    return render_template('index.html', menu=MENU_ITEMS)

@app.route('/api/status')
def get_status():
    # Tuto adresu volá JavaScript každých 300ms
    return jsonify(system_state)

@app.route('/api/click/<int:item_id>', methods=['POST'])
def web_click(item_id):
    trigger_action(item_id)
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    # Spuštění MQTT na pozadí
    threading.Thread(target=start_mqtt, daemon=True).start()
    # Spuštění Web Serveru
    app.run(host='0.0.0.0', port=5000, debug=False)
