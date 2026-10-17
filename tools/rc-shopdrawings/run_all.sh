set -x
rm -f out/ZONES/sheet_seq.json          # running sheet numbers rebuilt in zone order
python3 slab_scan.py
python3 gen_zones.py
python3 gen_zone_necks.py
python3 gen_zone_cores.py
python3 gen_zone_stairs.py
python3 gen_zone_strip.py
python3 gen_zone_gb.py
python3 gen_zone_sog.py
python3 gen_zone_cd.py
echo ALLDONE
