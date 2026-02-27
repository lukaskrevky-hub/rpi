import asyncio
from bleak import BleakClient
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
    client.publish(MQTT_TOPIC, command)

async def connect_and_listen():
    print(f"--- SPUŠTĚN CHYTRÝ REŽIM NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    # Čistý stůl po předchozích experimentech
    subprocess.run(['bluetoothctl', 'disconnect', TARGET_MAC], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    while True:
        try:
            # BleakClient si pod kapotou sám skenuje a čeká.
            # Timeout 10 vteřin dává Linuxu dostatek času transakci dokončit.
            async with BleakClient(TARGET_MAC, timeout=10.0) as client_ble:
                publish_status("READY") 
                print("\n+++ PŘIPOJENO! Ovladač je aktivní. +++")
                
                await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Držíme spojení
                while client_ble.is_connected:
                    await asyncio.sleep(0.5)
            
            # Ovladač usnul a korektně se odpojil
            print("--- Ovladač usnul ---")
            publish_status("SLEEP")
            await asyncio.sleep(1.0)
            
        except Exception as e:
            error_msg = str(e)
            
            # 1. BĚŽNÝ SPÁNEK: Ovladač prostě spí, BleakClient ho nenajde.
            if "was not found" in error_msg or "Device with address" in error_msg:
                publish_status("SLEEP")
                await asyncio.sleep(0.5)
                continue
                
            # 2. ZMĚNA STRATEGIE: "In Progress" znamená "Právě se připojuji!"
            # Nezabíjíme to! Dáme systému chvíli na dokončení operace na pozadí.
            if "In Progress" in error_msg:
                publish_status("CONNECTING")
                await asyncio.sleep(1.5)
                continue
                
            # 3. OPRAVDOVÁ CHYBA: Spojení bylo Linuxem opravdu zrušeno.
            publish_status("SLEEP")
            if "br-connection-canceled" in error_msg or "discover services" in error_msg:
                print("   [Uklízím zrušené spojení...]")
                subprocess.run(['bluetoothctl', 'disconnect', TARGET_MAC], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                await asyncio.sleep(1.0)
            else:
                await asyncio.sleep(1.0)

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
