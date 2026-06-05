#!/bin/bash
# Manual enrichment - target profil tertentu by name
# Usage: ./nyicil_manual.sh "Nama Profil 1" "Nama Profil 2" ...
#        ./nyicil_manual.sh --all (semua unenriched)
# No lockfile, no counter - run freely

if [ $# -eq 0 ]; then
    echo "Usage: $0 \"Nama Profil\" [\"Nama Profil 2\" ...]"
    echo "       $0 --all"
    exit 1
fi

/usr/bin/python3 /home/ubuntu/nyicil_enrich.py --manual "$@" >> /home/ubuntu/nyicil_manual.log 2>&1
