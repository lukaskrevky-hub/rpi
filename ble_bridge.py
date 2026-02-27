import asyncio
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt
import sys

# ==========================================
# CÍLOVÁ MAC ADRESA
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
            print("\nSkener: Prohledávám okolí (4 vteřiny)...")
            
            # Najdeme ÚPLNĚ VŠECHNA zařízení v okolí
            devices = await BleakScanner.discover(timeout=4.0)
            target_device = None
            
            # Zkusíme v nich najít náš ovladač (buď podle MAC, nebo podle jména)
            for d in devices:
                if d.address.lower() == TARGET_MAC.lower() or (d.name and "ESP-JOY" in d.name):
                    target_device = d
                    break
            
            if not target_device:
                print("\n--- DIAGNOSTIKA: Náš ovladač nenalezen. Co malina vlastně vidí? ---")
                if len(devices) == 0:
                    print("!!! RPi nevidí VŮBEC NIC. Zřejmě je zablokovaný Bluetooth modul.")
                    print("!!! Zkuste v terminálu: sudo systemctl restart bluetooth")
                else:
                    print(f"RPi vidí celkem {len(devices)} jiných zařízení:")
                    for d in devices:
                        # Vypíšeme nalezená zařízení pro kontrolu
                        name = d.name if d.name else "Neznámé zařízení"
                        print(f" - Jméno: {name} | MAC: {d.address} | RSSI: {d.rssi} dBm")
                print("-------------------------------------------------------------------")
                await asyncio.sleep(2.0)
                continue
                
            print(f"\n>>> NALEZENO NÁŠ OVLADAČ! (Jméno: {target_device.name}, MAC: {target_device.address}, RSSI: {target_device.rssi} dBm) <<<")
            publish_status("CONNECTING") 
            
            async with BleakClient(target_device, disconnected_callback=disconnected_callback, timeout=10.0) as client_ble:
                print("+++ PŘIPOJENO! Ovladač je aktivní. +++")
                publish_status("READY") 
                
                await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
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
