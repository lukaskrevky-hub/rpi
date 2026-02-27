import asyncio
from bleak import BleakClient
import paho.mqtt.client as mqtt
import sys
import subprocess

# ==========================================
# CÍLOVÁ MAC ADRESA (Potvrzená Bluetooth adresa ESP32)
TARGET_MAC = "10:06:1C:B5:A7:36"
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

# Globální paměť pro zamezení duplicitních výpisů
current_status = ""

def publish_status(status):
    global current_status
    if current_status != status:
        print(f"STAV -> {status}") 
        client.publish(TOPIC_STATUS, status, retain=True)
        current_status = status

def notification_handler(sender, data):
    command = data.decode('utf-8').strip()
    print(f"Přijato z BLE: {command}")
    client.publish(MQTT_TOPIC, command)

def disconnected_callback(client_ble):
    publish_status("SLEEP")

async def connect_and_listen():
    print(f"--- SPUŠTĚN NATIVNÍ REŽIM PŘIPOJOVÁNÍ NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    while True:
        try:
            # NATIVNÍ PŘIPOJENÍ BEZ SKENERU
            # Zcela jsme zahodili BleakScanner. Necháme BleakClienta, aby si sám
            # interně a bezpečně vyřešil hledání i připojení v jednom kroku.
            async with BleakClient(TARGET_MAC, disconnected_callback=disconnected_callback, timeout=5.0) as client_ble:
                
                publish_status("READY") 
                print("+++ PŘIPOJENO! Ovladač je aktivní. +++")
                
                await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                while client_ble.is_connected:
                    await asyncio.sleep(0.5)
            
            # Po korektním odpojení (uspání ESP32)
            print("Spojení korektně ukončeno.")
            publish_status("SLEEP")
            await asyncio.sleep(0.5)
            
        except Exception as e:
            error_msg = str(e)
            
            # Tiše ignorujeme stav, kdy ESP32 spí a BleakClient ho po 5s hledání nenajde
            if "Device with address" not in error_msg and "was not found" not in error_msg:
                print(f"Drobná chyba spojení: {error_msg}")
            
            publish_status("SLEEP")
            
            # Záchranná brzda pouze pro případ fatálního záseku Linuxu
            if "In Progress" in error_msg or "br-connection-canceled" in error_msg:
                subprocess.run(['bluetoothctl', 'disconnect', TARGET_MAC], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                await asyncio.sleep(1.0)
            else:
                await asyncio.sleep(0.2)

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
