import asyncio
from bleak import BleakClient, BleakScanner, BleakError
import paho.mqtt.client as mqtt
import sys
import time

# ==========================================
# NASTAVENÍ
DEVICE_NAME = "ESP-JOY"        # Jméno zařízení (musí souhlasit s ESP32)
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
TOPIC_STATUS = "joystick/status"
# ==========================================

# --- MQTT SETUP ---
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
    # Ignorujeme heartbeat
    if command == "PING":
        return
    print(f"Přijato z BLE: {command}")
    client.publish(MQTT_TOPIC, command)

def disconnected_callback(client):
    print(">>> Ztráta spojení (Joystick usnul nebo je mimo dosah).")
    publish_status("SLEEP")

async def find_device(timeout=10.0):
    """Naskenuje okolí a vrátí první zařízení se jménem DEVICE_NAME."""
    print(f"Hledám zařízení '{DEVICE_NAME}' (timeout {timeout}s)...")
    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
    for addr, (dev, adv) in devices.items():
        if dev.name and dev.name == DEVICE_NAME:
            print(f"   Nalezeno: {dev.name} ({addr})")
            return dev
    return None

async def connect_and_listen():
    print(f"--- SPUŠTĚN SKENOVACÍ REŽIM (hledám {DEVICE_NAME}) ---")
    publish_status("SLEEP")
    
    while True:
        try:
            # 1. Najdi zařízení
            device = await find_device(timeout=10)
            if not device:
                print("Zařízení nenalezeno, čekám 2s a zkusím znovu...")
                await asyncio.sleep(2)
                continue

            # 2. Pokus o připojení
            print(f"Pokouším se připojit k {device.address} ...")
            publish_status("CONNECTING")
            
            # Předchozí odpojení (pro jistotu)
            try:
                old_client = BleakClient(device.address)
                await old_client.disconnect()
            except:
                pass

            async with BleakClient(device, 
                                   disconnected_callback=disconnected_callback, 
                                   timeout=60.0) as client_ble:
                print("Navazuji spojení...")
                await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                print("PŘIPOJENO! Ovladač je aktivní.")
                publish_status("READY")
                
                # Udržovací smyčka
                while client_ble.is_connected:
                    await asyncio.sleep(1)
            
            print("Spojení ztraceno, návrat do smyčky hledání.")
            publish_status("SLEEP")
            
        except asyncio.TimeoutError:
            print("Timeout při připojování")
            await asyncio.sleep(2)
        except Exception as e:
            print(f"Chyba připojení: {e}")
            await asyncio.sleep(2)

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
