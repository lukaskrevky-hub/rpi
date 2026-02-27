import asyncio
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt
import sys

# ==========================================
# POTVRZENÁ SPRÁVNÁ MAC ADRESA
TARGET_MAC = "10:06:1C:B5:A7:34"
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

async def connect_and_listen():
    print(f"--- SPUŠTĚNO SKENOVÁNÍ A PŘIPOJOVÁNÍ NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    while True:
        try:
            print("Skener: Hledám zařízení ve vzduchu...")
            
            # Nejdříve zařízení vždy fyzicky vyhledáme. Tím obejdeme 99 % chyb v Linuxu.
            device = await BleakScanner.find_device_by_address(TARGET_MAC, timeout=4.0)
            
            if not device:
                print("Zařízení zatím nenalezeno. Zkouším to znovu...")
                continue
                
            print(f">>> NALEZENO! (Síla signálu: {device.rssi} dBm) <<<")
            publish_status("CONNECTING") 
            
            # Připojujeme se přímo přes nalezený objekt, ne jen přes textovou MAC
            async with BleakClient(device, disconnected_callback=disconnected_callback, timeout=10.0) as client_ble:
                print("+++ PŘIPOJENO! Ovladač je aktivní. +++")
                publish_status("READY") 
                
                await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Udržujeme spojení, dokud se zařízení neodpojí
                while client_ble.is_connected:
                    await asyncio.sleep(0.5)
            
        except Exception as e:
            print(f"Chyba při komunikaci: {e}")
            await asyncio.sleep(1.0)

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
