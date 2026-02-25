#! /usr/bin/python3
#
# parser for https://github.com/iovisor/bcc/blob/master/tools/biosnoop.py output
# TIME(s)     COMM           PID     DISK      T SECTOR     BYTES  LAT(ms)
# 0.000000    systemd-journa 456     nvme0n1   W 2036704120 4096   7.87
#
# (C) 2026 j.weigert@heinlein-support.de - distribute under GPLv2
#
# v0.1, 2026-02-23  initial draught.
# v0.2, 2026-02-25  prints nice bars.

import os, sys, time
from collections import deque       # list.pop(0) is O(n). deque.popleft() is O(1)

update_interval = 0.5   # seconds
time_window = 10.0      # seconds

bucket_sizes = [  4*1024, 16*1024, 64*1024, 256*1024, 1024*1024, 2*1024*1024, 4*1024*1024, 16*1024*1024, 64*1024*1024, 256*1024*1024 ]
bucket_names = ['<4k',  '<16k',  '<64k',  '<256k',  '<1M',     '<2M',       '<4M',       '<16M',       '<64M',       '<256M', '...' ]
def bucket(n):
    for i in range(len(bucket_sizes)):
        if n < bucket_sizes[i]:
            return i
    return len(bucket_sizes)


def print_stats(q):
    # for all buckets, increment
    r_counters = [0] * len(bucket_names)
    w_counters = [0] * len(bucket_names)
    for i in q:
        if i[1] == 'R':
            r_counters[i[2]] += 1
        else:
            w_counters[i[2]] += 1
    # print(r_counters, w_counters)

    cols, lines = os.get_terminal_size()
    bar_width = cols - 20
    maxval = max(r_counters + w_counters + [ bar_width ])

    for i in range(len(bucket_names)):
      print("\x1b[K%5s R %7d %s" % (bucket_names[i], r_counters[i],  "=" * int(r_counters[i] * bar_width / maxval)))
      print("\x1b[K%5s W %7d %s" % (             "", w_counters[i],  "#" * int(w_counters[i] * bar_width / maxval)))
    sys.stdout.flush()
    sys.stdout.write("\x1b[%dA" % 2*len(bucket_names))     # move cursor up again
    sys.stdout.flush()


printed_tstamp = 0.0

if sys.stdin.isatty():
  print("Usage:\n\t sudo python -u biosnoop.py | " + sys.argv[0])
  sys.exit(0)

queue = deque()

printcount = 0
for raw in sys.stdin:
    line = raw.split()
    if len(line) < 6:
        print("parse error: input did not look like it was from iovisor/tools/biosnoop.py: line too short")
        print(line)
        sys.exit(1)

    if line[4] == 'T' and line[5] == 'SECTOR' and line[6] == 'BYTES':
        continue
    for i in range(4, len(line)-2):
        if line[i] in ('W','R') and line[i+1].isdigit() and line[i+2].isdigit():
            break
    else:
        print("parse error: input did not look like it was from iovisor/tools/biosnoop.py: R/W column not found")
        print(line)
        sys.exit(1)

    now = time.time()
    queue.append([now, line[i], bucket(int(line[i+2]))])
    while len(queue) and queue[0][0] < now - time_window:
        queue.popleft()
        # print('x')

    if printed_tstamp + update_interval < now:
        printed_tstamp = now
        print_stats(queue)
        printcount += 1
        print("\\|/-"[printcount % 4] + "\r", end='', flush=True)

    # time.sleep(0.1)
