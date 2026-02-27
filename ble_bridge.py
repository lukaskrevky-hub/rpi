import asyncio
from bleak import BleakClient, BleakScanner
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

def publish_status(status):
    print(f"STAV -> {status}") 
    client.publish(TOPIC_STATUS, status, retain=True)

def notification_handler(sender, data):
    command = data.decode('utf-8').strip()
    print(f"Přijato z BLE: {command}")
    client.publish(MQTT_TOPIC, command)

def disconnected_callback(client):
    print(">>> Ztráta spojení (Joystick usnul nebo byl výpadek).")
    publish_status("SLEEP")

async def connect_and_listen():
    print(f"--- SPUŠTĚN STABILNÍ REŽIM PŘIPOJOVÁNÍ NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    consecutive_errors = 0
    
    while True:
        try:
            # 1. Použijeme krátký skener
            device = await BleakScanner.find_device_by_address(TARGET_MAC, timeout=3.0)
            
            if device:
                print("Nalezeno! Dávám Bluetooth modulu 1 vteřinu na přípravu...")
                # ZLATÉ PRAVIDLO: Po skenování nesmíme na Linux tlačit okamžitě. 
                # Tato pauza zabrání chybám 'br-connection-canceled' a 'failed to discover services'
                await asyncio.sleep(1.0)
                
                publish_status("CONNECTING")
                
                # 2. Připojíme se
                async with BleakClient(device, disconnected_callback=disconnected_callback, timeout=10.0) as client_ble:
                    print("+++ PŘIPOJENO! Ovladač je aktivní. +++")
                    publish_status("READY") 
                    consecutive_errors = 0 # Vynulujeme počítadlo chyb po úspěšném připojení
                    
                    await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                    
                    while client_ble.is_connected:
                        await asyncio.sleep(0.5)
                
                # 3. Odpojení
                print("Dávám systému 1.5 vteřiny na vyčištění socketů...")
                await asyncio.sleep(1.5)
                
            else:
                await asyncio.sleep(0.5)
                
        except Exception as e:
            error_msg = str(e)
            print(f"Výpadek: {error_msg}")
            
            if "In Progress" in error_msg:
                # Pokud již probíhá připojování, počkáme déle, než se pokusíme o další,
                # abychom nenarušili probíhající proces
                print("Připojení již probíhá, čekám 3 vteřiny...")
                await asyncio.sleep(3.0)
                consecutive_errors += 1
            elif "br-connection-canceled" in error_msg or "discover services" in error_msg:
                print("!!! Zjištěn zásek Linuxu. Čekám 2 vteřiny...")
                await asyncio.sleep(2.0)
                consecutive_errors += 1
            else:
                await asyncio.sleep(1.0)
            
            # Tvrdý restart aplikujeme až po opakovaných selháních, 
            # ne při každé chybě In Progress
            if consecutive_errors >= 3:
                print("!!! Vícečetné selhání připojení. Provádím tvrdý úklid...")
                proc = await asyncio.create_subprocess_exec(
                    'bluetoothctl', 'disconnect', TARGET_MAC,
                    stdout=asyncio.subprocess.DEVNULL, 
                    stderr=asyncio.subprocess.DEVNULL
                )
                await proc.wait()
                await asyncio.sleep(3.0)
                consecutive_errors = 0 # Vynulujeme počítadlo po tvrdém úklidu

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
