import asyncio
from bleak import BleakClient
import paho.mqtt.client as mqtt
import sys
import subprocess

# ==========================================
# CÍLOVÁ MAC ADRESA (Nyní 100% potvrzená)
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
    print(f"--- SPUŠTĚNO RYCHLÉ PŘÍMÉ PŘIPOJOVÁNÍ NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    while True:
        try:
            # PŘÍMÉ PŘIPOJENÍ (Direct Connect) - Zahozen pomalý skener!
            # Timeout 3.0s: Pokud joystick spí, malina to zjistí za 3 vteřiny a zkusí to znovu.
            # Jakmile se joystick probudí, malina ho chytí prakticky okamžitě.
            async with BleakClient(TARGET_MAC, disconnected_callback=disconnected_callback, timeout=3.0) as client_ble:
                
                publish_status("CONNECTING")
                print("+++ PŘIPOJENO! Ovladač je aktivní. +++")
                publish_status("READY") 
                
                # Zapneme příjem zpráv z joysticku
                await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Udržujeme spojení, dokud se ovladač sám neuspí
                while client_ble.is_connected:
                    await asyncio.sleep(0.5)
            
        except Exception as e:
            error_msg = str(e)
            
            # Nebudeme spamovat terminál chybou "Device not found" (když joystick běžně spí)
            if "was not found" not in error_msg and "EOFError" not in error_msg:
                print(f"Drobný výpadek spojení: {error_msg}")
            
            # Záchranná brzda: Pokud se BlueZ zasekne na starém pokusu, pročistíme to
            if "In Progress" in error_msg or "br-connection-canceled" in error_msg:
                print("!!! Zjištěno zaseknutí modulu. Čistím Linuxovou paměť...")
                subprocess.run(["bluetoothctl", "disconnect", TARGET_MAC], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                await asyncio.sleep(1.0)
            
            # Krátká pauza před dalším pokusem
            await asyncio.sleep(0.5)

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
