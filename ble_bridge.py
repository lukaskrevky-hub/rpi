import asyncio
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt
import sys
import subprocess

# ==========================================
# CÍLOVÁ MAC ADRESA
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
    pass # Ignorujeme spam z Linuxu, řešíme v hlavní smyčce

async def connect_and_listen():
    print(f"--- SPUŠTĚN ČISTÝ REŽIM PŘIPOJOVÁNÍ NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    consecutive_errors = 0
    
    while True:
        try:
            # 1. Najdeme zařízení
            device = await BleakScanner.find_device_by_address(TARGET_MAC, timeout=2.0)
            
            if device:
                publish_status("CONNECTING")
                
                # ZLATÉ PRAVIDLO: Předáváme 'device' objekt, NIKOLIV string TARGET_MAC!
                # Tím zakážeme BleakClientovi spouštět druhý sken, který ničil spojení.
                async with BleakClient(device, disconnected_callback=disconnected_callback, timeout=8.0) as client_ble:
                    publish_status("READY") 
                    print("+++ PŘIPOJENO! Ovladač je aktivní. +++")
                    consecutive_errors = 0
                    
                    await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                    
                    # Držíme, dokud ESP32 neusne
                    while client_ble.is_connected:
                        await asyncio.sleep(0.5)
                
                publish_status("SLEEP")
                await asyncio.sleep(0.5)
                
            else:
                await asyncio.sleep(0.5)
                
        except Exception as e:
            error_msg = str(e)
            print(f"   [Chyba] {error_msg}")
            publish_status("SLEEP")
            
            # ŘEŠENÍ CHYB
            if "discover services" in error_msg:
                # Modul má uloženou zkaženou mezipaměť. Musíme ji vymazat ('remove').
                print("!!! Poškozená mezipaměť Linuxu. Mažu profil ovladače...")
                subprocess.run(['bluetoothctl', 'remove', TARGET_MAC], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                await asyncio.sleep(2.0)
            
            elif "br-connection-canceled" in error_msg or "In Progress" in error_msg:
                # Zaseknutý proces
                subprocess.run(['bluetoothctl', 'disconnect', TARGET_MAC], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                consecutive_errors += 1
                await asyncio.sleep(1.0)
            
            else:
                await asyncio.sleep(1.0)
            
            # Tvrdý restart
            if consecutive_errors >= 3:
                print("!!! Tvrdý restart Bluetooth napájení...")
                subprocess.run(['bluetoothctl', 'power', 'off'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                await asyncio.sleep(1.0)
                subprocess.run(['bluetoothctl', 'power', 'on'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                consecutive_errors = 0
                await asyncio.sleep(2.0)

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
