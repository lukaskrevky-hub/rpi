import asyncio
from bleak import BleakClient, BleakScanner, BleakError
import paho.mqtt.client as mqtt
import sys

# ==========================================
# OPRAVA: SPRÁVNÁ MAC ADRESA (končí 34)
TARGET_MAC = "10:06:1C:B5:A7:34"
# ==========================================

UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# MQTT Konfigurace
MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
TOPIC_STATUS = "joystick/status" 

# --- MQTT SETUP ---
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

try:
    client.connect(MQTT_BROKER, 1883, 60)
    client.loop_start()
    print("MQTT připojeno.")
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1)

# --- POMOCNÉ FUNKCE ---

def publish_status(status):
    """Odeslání stavu do MQTT"""
    print(f"STAV -> {status}") 
    client.publish(TOPIC_STATUS, status, retain=True)

def notification_handler(sender, data):
    """Zpracování dat přijatých z ESP32."""
    command = data.decode('utf-8').strip()
    print(f"Přijato z BLE: {command}")
    client.publish(MQTT_TOPIC, command)

def disconnected_callback(client):
    """Zavolá se, když se ESP32 odpojí (usne)."""
    print(">>> Ztráta spojení (Joystick usnul).")
    publish_status("SLEEP")

# --- HLAVNÍ SMYČKA PRO PŘIPOJENÍ ---

async def connect_and_listen():
    print(f"--- SPUŠTĚN SKENER A CONNECT NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    while True:
        try:
            print(f"Hledám signál z joysticku ({TARGET_MAC})...")
            
            # KOMUNITNÍ ŘEŠENÍ (Best Practice): 
            # Nejdříve fyzicky najdeme zařízení ve vzduchu pomocí skeneru.
            # Tím obejdeme zaseknutou BlueZ mezipaměť (cache) v Linuxu.
            device = await BleakScanner.find_device_by_address(TARGET_MAC, timeout=5.0)
            
            if not device:
                # Zařízení spí, skener nic neslyšel, jedeme znovu
                continue
                
            print(f"Signál zachycen (RSSI: {device.rssi} dBm)! Navazuji spojení...")
            publish_status("CONNECTING") 
            
            # Předáváme zjištěný fyzický OBJEKT (device), nikoliv jen textovou MAC adresu
            async with BleakClient(device, disconnected_callback=disconnected_callback, timeout=5.0) as client_ble:
                
                # Zapneme notifikace
                await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                print("PŘIPOJENO! Ovladač je aktivní.")
                publish_status("READY") 
                
                # Udržujeme spojení
                while client_ble.is_connected:
                    await asyncio.sleep(0.5)
            
            # Zde se kód dostane po odpojení
            
        except Exception as e:
            # Rychlý spánek a nový pokus, pokud ESP zrovna nebylo dostupné nebo signál zarušila Wi-Fi
            print(f"Chyba při spojení: {e}")
            await asyncio.sleep(0.5)

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
