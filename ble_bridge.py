import asyncio
from bleak import BleakClient
import paho.mqtt.client as mqtt
import sys

# ==========================================
# CÍLOVÁ MAC ADRESA (Potvrzená)
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
    pass # Odpojení řešíme v hlavní smyčce, zamezuje spamu z Linuxu

# ASYNCHRONNÍ exekuce systémových příkazů (Nezmrazí Python smyčku!)
async def run_bt_cmd(*args):
    try:
        proc = await asyncio.create_subprocess_exec(
            'bluetoothctl', *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.wait()
    except Exception:
        pass

async def connect_and_listen():
    print(f"--- SPUŠTĚN ČISTÝ (INDEXOVÝ) REŽIM NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    while True:
        try:
            # NATIVNÍ PŘIPOJENÍ BEZ SKENERU
            async with BleakClient(TARGET_MAC, disconnected_callback=disconnected_callback, timeout=6.0) as client_ble:
                publish_status("READY") 
                print("+++ PŘIPOJENO! Ovladač je aktivní. +++")
                
                await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Udržujeme spojení, dokud pacient neustane v činnosti a ESP32 samo neusne
                while client_ble.is_connected:
                    await asyncio.sleep(0.5)
            
            # Zde jsme, pokud se ESP32 korektně odpojilo (usnulo)
            print("--- Spojení ukončeno (ovladač usnul) ---")
            publish_status("SLEEP")
            await asyncio.sleep(0.5)
            
        except Exception as e:
            # Očistíme text výjimky od případných bílých znaků
            error_msg = str(e).strip()
            
            # 1. TICHÁ ABSORPCE: Běžné stavy (spánek, prázdné výpisy při odpojení)
            # Zde zachytíme i ten tvůj prázdný výpis (kdy error_msg == "")
            if not error_msg or "was not found" in error_msg or "Device with address" in error_msg or "EOFError" in error_msg or "disconnected" in error_msg.lower():
                publish_status("SLEEP")
                await asyncio.sleep(0.5)
                continue
            
            # 2. IN PROGRESS: Není to chyba, Linux zrovna fyzicky navazuje spojení.
            if "In Progress" in error_msg:
                publish_status("CONNECTING") 
                await asyncio.sleep(0.5)
                continue
            
            # 3. ZRUŠENO SYSTÉMEM: Linux proces zařízl, musíme porty vyčistit.
            if "br-connection-canceled" in error_msg or "discover services" in error_msg:
                publish_status("CONNECTING")
                await run_bt_cmd('disconnect', TARGET_MAC)
                await asyncio.sleep(1.0)
                continue
            
            # Ostatní skutečné a nečekané chyby
            print(f"   [Drobný šum v Linuxu] {error_msg}")
            publish_status("SLEEP")
            await asyncio.sleep(1.0)

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
