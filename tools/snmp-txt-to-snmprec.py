#!/usr/bin/env python3
# (C) 2026 j.weigert@heinlein-support.de
#
# Accepts a .txt file that has only two columns:
# .1.3.6.1.2.1.1.1.0 Linux PDU-6240-T01 4.4.57+ #1 Mon Nov 6 12:31:43 CET 2023 armv5tejl
# .1.3.6.1.2.1.1.2.0 .1.3.6.1.4.1.31770.2.1.3.7566
# .1.3.6.1.2.1.1.3.0 233558344
# .1.3.6.1.2.1.1.4.0 info@bachmann.com
# .1.3.6.1.2.1.1.5.0 PDU-6240-T01
# .1.3.6.1.2.1.1.6.0 Bachmann GmbH, Ernsthaldenstrasse 33, D-70565 Stuttgart
# .1.3.6.1.2.1.1.7.0 64
# .1.3.6.1.2.1.1.8.0 5132
# .1.3.6.1.2.1.1.9.1.2.22 .1.3.6.1.6.3.13.3.1.3
# .1.3.6.1.2.1.1.9.1.2.23 .1.3.6.1.2.1.92
# .1.3.6.1.2.1.1.9.1.3.1 The MIB module to manage a BlueNet2 PDU using the private Bachmann SNMP MIB.
# .1.3.6.1.2.1.1.9.1.3.2 The MIB module for SNMP entities containing all RFC1213 MIB-II groups.
# .1.3.6.1.2.1.1.9.1.3.3 The MIB module to manage host systems.
# .1.3.6.1.2.1.1.9.1.3.4 The MIB module to describe generic objects for network interface sub-layers.
#
# outputs a file, where instead of the first whitespace,  |type| is used, where type
# is one of the well known types 2,4,5,6,70,67,64,66
# - the output should be saved in a subfolder 
#	snmpsim-pdu-t01/public.snmprec
# - then snmpsimd can pick it up like this: 
#	snmpsimd --data-dir=$(pwd)/snmpsim-pdu-t01 --agent-udpv4-endpoint=0.0.0.0:2161 --v2c-arch --pid-file=$(pwd)/snmpsim-pdu-t01/snmpsim.pid


import re
import sys

import re
from datetime import datetime


def is_integer(value):
    """True if value is a plain integer."""
    return re.fullmatch(r'-?\d+', value) is not None

def is_unsigned_integer(value):
    """True if value is a non‑negative integer."""
    return re.fullmatch(r'\d+', value) is not None

def is_ip_address(value):
    """True if value looks like an IPv4 address."""
    ipv4_pat = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'
    if re.fullmatch(ipv4_pat, value):
        octets = [int(x) for x in value.split(".") if 0 <= int(x) <= 255]
        return len(octets) == 4
    return False

def is_oid(value):
    """True if value is an OID (starts with .1.3.6.1. etc.)."""
    return re.fullmatch(r'\.1\.3\.6\.1\.\S*', value) is not None

def is_timeticks(value):
    if not is_unsigned_integer(value):
        return False
    n = int(value)
    # Only treat clearly large non‑negative integers as TimeTicks
    return n >= 30000000  # or adjust as needed

def is_datetimeish(value):
    """Loose pattern for common SNMP‑like date/time strings."""
    # Example: "Fri Nov 3 15:05:28 CET 2023"
    dt_pat = r'[A-Za-z]{3}\s+[A-Za-z]{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\S+\s+\d{4}'
    return re.search(dt_pat, value) is not None

def is_counter64(value):
    """True if value is a large unsigned integer (likely Counter64)."""
    return re.fullmatch(r'\d+', value) is not None and len(value) > 10

def guess_type(value):
    """Return snmprec type code based on value content."""
    v = value.strip()

    if v == "":
        return "4"   # OCTET STRING (empty)

    if v.lower() in ("none", "null"):
        return "5"   # NULL

    if is_counter64(v):
        return "70"  # Counter64

    if is_timeticks(v):
        return "67"  # TimeTicks

    if is_oid(v):
        return "6"   # OBJECT IDENTIFIER

    if is_ip_address(v):
        return "64"  # IpAddress

    if is_unsigned_integer(v):
        # Distinguish Counter32 vs Gauge32 vs plain INTEGER
        # If you know the OID context, you can tune this further.
        # For generic guessing, assume non‑negative integers are Gauge32.
        return "66"  # Gauge32; use "65" if you prefer Counter32

    if is_integer(v):
        return "2"   # INTEGER

    if is_datetimeish(v):
        return "4"   # OCTET STRING (date/time string)

    # Everything else as OCTET STRING
    return "4"



def parse_line(line):
    """Parse one line from input and return snmprec tuple (oid, type, value)."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    # Split into OID part and the rest
    if " " not in line:
        return None
    first_space = line.find(" ")
    oid = line[:first_space].strip()
    if oid.startswith('.'):	# leading . are not allowed in .snmprec
        oid = oid[1:]
    rest = line[first_space:].strip()

    # Extract value up to the arrow (if present) or the whole rest
    if " --> " in rest:
        value = rest.split(" --> ", 1)[0].strip()
    else:
        value = rest

    typ = guess_type(value)
    return oid, typ, value

def main():
    infile = sys.argv[1] if len(sys.argv) > 1 else "/dev/stdin"

    with open(infile, "r", encoding="utf-8") as f:
        for line in f:
            parsed = parse_line(line)
            if parsed is None:
                continue
            oid, typ, value = parsed
            print(f"{oid}|{typ}|{value}")

if __name__ == "__main__":
    main()
