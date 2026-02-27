import asyncio
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt
import sys

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
    client.publish(MQTT_TOPIC, command)

async def connect_and_listen():
    print(f"--- SPUŠTĚN KOMUNITNÍ ROBUSTNÍ REŽIM NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    # Exponenciální backoff pro uklidnění BlueZ
    backoff = 1.0 
    
    while True:
        try:
            # 1. Hledáme zařízení pomocí standardního skeneru
            device = await BleakScanner.find_device_by_address(TARGET_MAC, timeout=3.0)
            
            if not device:
                # Ovladač spí
                publish_status("SLEEP")
                await asyncio.sleep(0.5)
                continue
                
            publish_status("CONNECTING")
            
            # ZLATÉ PRAVIDLO KOMUNITY: Zastavení skeneru není okamžité. 
            # BlueZ potřebuje přesně 2 vteřiny na uvolnění D-Bus sběrnice.
            await asyncio.sleep(2.0)
            
            # 2. Samotné připojení
            async with BleakClient(device, timeout=15.0) as client_ble:
                publish_status("READY") 
                print("\n+++ PŘIPOJENO! Ovladač je aktivní. +++")
                backoff = 1.0 # Reset backoffu po úspěšném připojení
                
                await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Sledujeme spojení
                while client_ble.is_connected:
                    await asyncio.sleep(0.5)
            
            # Korektní odpojení
            print("--- Ovladač se odpojil ---")
            publish_status("SLEEP")
            await asyncio.sleep(1.0)
            
        except Exception as e:
            error_msg = str(e)
            
            if "was not found" in error_msg:
                await asyncio.sleep(1.0)
                continue
                
            print(f"   [BlueZ Chyba] {error_msg}")
            
            # ŘEŠENÍ PODLE INTERNETU (Home Assistant komunita):
            if "In Progress" in error_msg:
                # Modul se zablokoval. Exponenciálně prodlužujeme čekání, 
                # abychom mu dali šanci se vzpamatovat bez vynuceného restartu.
                print(f"   -> Čekám {backoff} vteřin na uvolnění modulu...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 8.0) # Max 8 vteřin
                
            elif "br-connection-canceled" in error_msg or "abort-by-local" in error_msg:
                # HW interference (Wi-Fi vs Bluetooth). Krátká pauza na obnovu.
                print("   -> Spojení zrušeno hardwarem. Zkouším znovu...")
                await asyncio.sleep(2.0)
                
            else:
                await asyncio.sleep(2.0)

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
