#!/bin/bash

# ==========================================
# Skript pro automatické nahrání IR ovladače
# ==========================================

BRAND=$1
DEVICE="/dev/lirc1" # Nastaveno na lirc1 (přijímač). Pokud by nefungovalo, změň na lirc0.

if [ -z "$BRAND" ]; then
    echo "CHYBA: Nezadali jste značku televize!"
    echo "Použití: ./record_ir.sh <znacka>"
    echo "Příklad: ./record_ir.sh sony"
    exit 1
fi

DIR="/home/lukas/rpi/ir_codes/$BRAND"

# Vytvoření složky, pokud neexistuje
mkdir -p "$DIR"
echo "=== Spouštím nahrávání ovladače: $BRAND ==="
echo "Kódy se budou ukládat do: $DIR"
echo "Používám přijímač: $DEVICE"
echo "==========================================="

# Seznam tlačítek, které tvůj web.py očekává
BUTTONS=("power" "ch_up" "ch_down" "vol_up" "vol_down")

for btn in "${BUTTONS[@]}"; do
    echo ""
    echo ">>> Připravte si ovladač pro tlačítko: [$btn] <<<"
    read -p "Stiskněte ENTER, namiřte ovladač na senzor a krátce stiskněte tlačítko..."
    
    # OPRAVA: Přidán parametr -1 (One-Shot). 
    # Program nahraje jeden stisk a sám se hned ukončí.
    ir-ctl -r -1 -d $DEVICE > "$DIR/$btn.txt"
    
    echo "Uloženo: $btn.txt"
    sleep 1 # Vteřina pauza pro jistotu, než přejdeme na další tlačítko
done

echo ""
echo "==========================================="
echo "HOTOVO! Všechna tlačítka pro $BRAND jsou úspěšně nahrána."
echo "Nyní je můžete okamžitě používat ve webovém rozhraní."
