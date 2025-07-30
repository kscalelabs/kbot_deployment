#!/usr/bin/env bash

selected="$*"

declare -A actuators=(
    [11]="Lsp"
    [12]="Lsr"
    [13]="Lsy"
    [14]="Lep"
    [15]="Lwr"
    [21]="Rsp"
    [22]="Rsr"
    [23]="Rsy"
    [24]="Rep"
    [25]="Rwr"
    [31]="Lhp"
    [32]="Lhr"
    [33]="Lhy"
    [34]="Lkp"
    [35]="Lap"
    [41]="Rhp"
    [42]="Rhr"
    [43]="Rhy"
    [44]="Rkp"
    [45]="Rap"
)

declare -A max_torques=(
     [11]=42.0
     [12]=42.0
     [13]=11.9
     [14]=11.9
     [15]=9.8
     [21]=42.0
     [22]=42.0
     [23]=11.9
     [24]=11.9
     [25]=9.8
     [31]=84.0
     [32]=42.0
     [33]=42.0
     [34]=84.0
     [35]=11.9
     [41]=84.0
     [42]=42.0
     [43]=42.0
     [44]=84.0
     [45]=11.9

#    [11]=60.0
#    [12]=60.0
#    [13]=17.0
#    [14]=17.0
#    [15]=14.0
#    [21]=60.0
#    [22]=60.0
#    [23]=17.0
#    [24]=17.0
#    [25]=14.0
#    [31]=115.0
#    [32]=60.0
#    [33]=60.0
#    [34]=115.0
#    [35]=17.0
#    [41]=115.0
#    [42]=60.0
#    [43]=60.0
#    [44]=115.0
#    [45]=17.0
)

echo "Setting up CAN interfaces..."

ifaces="$(ip link show | grep -oP 'can[0-9]+' | sort -u)"

for interface in $ifaces; do
    echo "Bringing up $interface..."
    sudo ip link set $interface down
    sudo ip link set $interface type can bitrate 1000000
    sudo ip link set $interface txqueuelen 1000
    sudo ip link set $interface up
done

# TODO Discover actuators
# read -p "Press enter to discover actuators..."

selected="$(for i in {1..4}; do for j in {1..5}; do echo $i$j; done; done)"

for id_dec in $selected; do
    id=$(printf "%.2X" "$id_dec")

    val="${max_torques[$id_dec]}"
    val_hex="$(python -c "import numpy; print(numpy.float32($val).tobytes().hex())")"
    val_littleendian="${val_hex:0:2}.${val_hex:2:2}.${val_hex:4:2}.${val_hex:6:2}"

    resp=""

    for interface in $ifaces; do
	# read -p "Send 1200FD${id}#0B.70.00.00.${val_littleendian} ?"
        resp="$(candump  -T 25 $interface,0200${id}FD:0000FF00 & sleep .01;
		cansend $interface 1200FD${id}#0B.70.00.00.${val_littleendian})"
        if [ "$resp" ]; then
            echo "Set max_torque to $val on actuator $id_dec (${actuators[$id_dec]}): $resp"
            break
        fi
    done

    if [ -z "$resp" ]; then
        echo "No response from actuator $id_dec (${actuators[$id_dec]})"
    fi
done
