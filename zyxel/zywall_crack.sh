#!/bin/sh

# Automatize cracking of ZyWALL update passwords
# Uses InfoZip 2.32

# Quick path:
# ZyWALL USG 20 330BDQ7C0: key0=32fc995b, key1=df28965e, key2=8a8dae5b

ZIP232=~/zip232/zip
PKCRACK=~/pkcrack-1.2.2/src/pkcrack
PKEXTRACT=~/pkcrack-1.2.2/src/extract

FWNAME=$1

if [ "x$FWNAME" = "x" ]; then
	echo "Please provide the name of the update"
	exit 1
fi
echo "Provided update name: $FWNAME"

TEMP_ZIP=$FWNAME_temp.zip

echo "Generating plaintext"
$ZIP232 -9 $TEMP_ZIP $FWNAME.conf
$PKEXTRACT $TEMP_ZIP $FWNAME.conf $FWNAME.plaintext
rm $TEMP_ZIP

echo "Starting pkcrack"
$PKCRACK -C $FWNAME.bin -c db/etc/zyxel/ftp/conf/system-default.conf -p $FWNAME.plaintext

echo "Done!"
