import asyncio
from bleak import BleakClient, BleakScanner
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
    # Callback úmyslně prázdný. Odpojení řešíme metodicky v hlavní smyčce, 
    # abychom zamezili Linuxovému spamu, kdy volá odpojení 10x po sobě.
    pass

async def connect_and_listen():
    print(f"--- SPUŠTĚN INVESTIČNÍ REŽIM PŘIPOJOVÁNÍ NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    while True:
        try:
            # 1. PASIVNÍ VYČKÁVÁNÍ
            # Tiše a bez zátěže systému skenujeme vzduch.
            device = await BleakScanner.find_device_by_address(TARGET_MAC, timeout=1.5)
            
            if device:
                publish_status("CONNECTING")
                await asyncio.sleep(0.5) # Důležitý oddech po skenování
                
                # 2. METODICKÝ VSTUP DO POZICE (Až 3 klidné pokusy)
                for attempt in range(1, 4):
                    try:
                        # Používáme přímo TARGET_MAC místo objektu 'device'
                        async with BleakClient(TARGET_MAC, disconnected_callback=disconnected_callback, timeout=6.0) as client_ble:
                            publish_status("READY") 
                            print("+++ PŘIPOJENO! Ovladač je aktivní. +++")
                            
                            await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                            
                            # Držíme pozici, dokud pacient nevypne ovladač (neusne)
                            while client_ble.is_connected:
                                await asyncio.sleep(0.5)
                            
                            print("Spojení korektně ukončeno (ovladač usnul).")
                            break # Úspěšně dokončeno, vyskakujeme z retry smyčky
                            
                    except Exception as e:
                        # Vypíšeme chybu, abychom viděli, co se skutečně děje
                        print(f"   [Tržní šum - Pokus {attempt}/3] {e}")
                        
                        if attempt == 3:
                            # Kompletní restart adaptéru místo pouhého odpojení
                            print("!!! Modul je tvrdě zacyklený. Provádím kompletní restart Bluetooth napájení...")
                            subprocess.run(['bluetoothctl', 'power', 'off'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            await asyncio.sleep(1.0)
                            subprocess.run(['bluetoothctl', 'power', 'on'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            await asyncio.sleep(2.0)
                        else:
                            await asyncio.sleep(1.0)
                
                # Po korektním odpojení nebo vyčerpání pokusů jdeme zpět do spánku
                publish_status("SLEEP")
                await asyncio.sleep(1.0)
                
        except Exception as e:
            # Ochrana proti pádu samotného skeneru
            await asyncio.sleep(1.0)

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
