"""Receive CSI records from the ESP32-C6 probe over UDP and save them as JSONL.

Packet layout must match probe_hdr_t in firmware/csi_probe/main/app_main.c.
Run on the survey PC (wired to the router) for the whole walk survey:

    .venv/Scripts/python.exe scripts/csi_receiver.py            # until Ctrl+C
    .venv/Scripts/python.exe scripts/csi_receiver.py --seconds 60
"""

import argparse
import json
import socket
import struct
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median

PORT = 5005
HEADER = struct.Struct("<4sBBHBBbbBbBBBBHHIIIIIf")
FIELDS = (
    "magic version state point attempt rx_format rssi noise_floor agc_gain fft_gain "
    "channel rate first_word_invalid truncated csi_len sig_len boot_id seq "
    "rx_timestamp_us uptime_ms dropped compensate_gain"
).split()
STATE_NAMES = {0: "idle", 1: "walk away", 2: "RECORDING"}
OUT_DIR = Path("data/raw")


def parse(packet: bytes) -> dict | None:
    if len(packet) < HEADER.size or packet[:4] != b"EUTW":
        return None
    rec = dict(zip(FIELDS, HEADER.unpack_from(packet)))
    del rec["magic"]
    csi = packet[HEADER.size : HEADER.size + rec["csi_len"]]
    rec["csi"] = list(struct.unpack(f"<{len(csi)}b", csi))
    rec["boot_id"] = f"{rec['boot_id']:08x}"
    return rec


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=None, help="stop after this many seconds")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"csi_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", PORT))
    sock.settimeout(0.5)
    print(f"Listening on UDP {PORT}, writing {out_path}", flush=True)

    start = time.time()
    next_status = start + 1.0
    window = []
    last = None
    point_rssi = defaultdict(list)
    with out_path.open("w", encoding="utf-8") as out:
        while args.seconds is None or time.time() - start < args.seconds:
            try:
                packet, _ = sock.recvfrom(4096)
            except socket.timeout:
                packet = None
            if packet:
                rec = parse(packet)
                if rec:
                    rec["pc_time"] = round(time.time(), 3)
                    out.write(json.dumps(rec, separators=(",", ":")) + "\n")
                    window.append(rec["rssi"])
                    key = (rec["boot_id"], rec["point"], rec["attempt"])
                    if rec["state"] == 2:
                        point_rssi[key].append(rec["rssi"])
                    if last and last["state"] == 2 and rec["state"] != 2:
                        k = (last["boot_id"], last["point"], last["attempt"])
                        vals = point_rssi[k]
                        print(f"  -> point {k[1]} (attempt {k[2]}) done: {len(vals)} records, "
                              f"median RSSI {median(vals):.0f} dBm", flush=True)
                    last = rec
            if time.time() >= next_status:
                next_status += 1.0
                if last is None:
                    print("waiting for the probe ...", flush=True)
                elif window:
                    print(f"{len(window):3d}/s  point {last['point']:3d}  {STATE_NAMES.get(last['state'], '?'):10s} "
                          f"RSSI {median(window):.0f} dBm  dropped {last['dropped']}", flush=True)
                else:
                    print("no data in the last second", flush=True)
                window = []
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
