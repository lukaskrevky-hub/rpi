import asyncio
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt
import sys

# ==========================================
# ODSTRANĚNA MAC ADRESA! 
# Systém si ovladač najde sám podle názvu "ESP-JOY"
# ==========================================

UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
TOPIC_STATUS = "joystick/status" 

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

try:
    client.connect(MQTT_BROKER, 1883, 60)
    client.loop_start()
    print("MQTT připojeno.")
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1)

def publish_status(status):
    print(f"STAV -> {status}") 
    client.publish(TOPIC_STATUS, status, retain=True)

def notification_handler(sender, data):
    command = data.decode('utf-8').strip()
    print(f"Přijato z BLE: {command}")
    client.publish(MQTT_TOPIC, command)

def disconnected_callback(client):
    print(">>> Ztráta spojení (Joystick usnul nebo je mimo dosah).")
    publish_status("SLEEP")

# Filtr pro nalezení ESP32 podle jména
def is_esp_joy(device, adv_data):
    if device.name and "ESP-JOY" in device.name:
        return True
    if adv_data.local_name and "ESP-JOY" in adv_data.local_name:
        return True
    return False

async def connect_and_listen():
    print("--- SPUŠTĚNO AUTODETEKČNÍ HLEDÁNÍ OVLADAČE 'ESP-JOY' ---")
    publish_status("SLEEP")
    
    while True:
        try:
            print("Skener: Čekám na probuzení joysticku ve vzduchu...")
            
            # Skener běží 3 vteřiny a hledá cokoliv s názvem ESP-JOY
            device = await BleakScanner.find_device_by_filter(is_esp_joy, timeout=3.0)
            
            if not device:
                # Nic jsme nenašli, jdeme hledat znovu (rychlá smyčka)
                continue
                
            print(f">>> NALEZENO! Adresa: {device.address} (Síla signálu: {device.rssi} dBm) <<<")
            publish_status("CONNECTING") 
            
            # Připojujeme se přímo přes NALEZENÝ OBJEKT (Nejstabilnější metoda pro Linux)
            async with BleakClient(device, disconnected_callback=disconnected_callback, timeout=5.0) as client_ble:
                print("+++ PŘIPOJENO! Ovladač je aktivní. +++")
                publish_status("READY") 
                
                await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Udržujeme spojení, dokud ho ESP32 (po 15s) samo neukončí
                while client_ble.is_connected:
                    await asyncio.sleep(0.5)
            
        except Exception as e:
            # Tichý restart smyčky při případné kolizi na Bluetooth
            await asyncio.sleep(0.2)

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
