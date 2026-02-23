#! /usr/bin/python3
#
# parser for https://github.com/iovisor/bcc/blob/master/tools/biosnoop.py output
# TIME(s)     COMM           PID     DISK      T SECTOR     BYTES  LAT(ms)
# 0.000000    systemd-journa 456     nvme0n1   W 2036704120 4096   ?    7.87

import sys, time
from collections import deque       # list.pop(0) is O(n). deque.popleft() is O(1)

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
    print(r_counters, w_counters)


printed_tstamp = 0.0
update_interval = 1.0   # seconds
time_window = 10.0      # seconds

queue = deque()

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

    time.sleep(0.1)
