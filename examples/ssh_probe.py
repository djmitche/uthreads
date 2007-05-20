# A "scanner" that gets the first line on port 22 from each of the
# hosts supplied on the command line.  This takes advantage of the
# microthreaded parallelism to check "all" of the hosts at once.

from ulib import socket
import uthreads
import sys
import re

def probe_host(host):
    s = socket.socket()
    try:
        yield s.connect((host, 22))
    except socket.error, why:
        print "%s: %s" % (host, why.args[1])
        return

    data = ''
    while True:
        try:
            d = yield s.recv(1024)
        except socket.error, why:
            print "%s: %s" % (host, why.args[1])
            return
        if not d: break
        data += d
        if '\n' in data: break # exit on first newline
    print "%s: %s" % (host, data.split('\n', 1)[0].strip())
    s.close()

def get_iprange(hostname):
    mo = re.match('([0-9]{1,3}).([0-9]{1,3}).([0-9]{1,3}).([0-9]{1,3})/([0-9]+)', hostname)
    if mo:
        ip1, ip2, ip3, ip4, bitlen = mo.groups()
        ip = (long(ip1) << 24) + (long(ip2) << 16) + (long(ip3) << 8) + (long(ip4))
        nm = (1 << (32-int(bitlen))) - 1

        # clear off stray bits
        ip = ip & ~nm
        for _ in xrange(nm+1):
            yield "%d.%d.%d.%d" % (
                (ip >> 24),
                (ip >> 16) & 0xff,
                (ip >> 8) & 0xff,
                ip & 0xff)
            ip += 1
    else:
        yield hostname

def main():
    for host in sys.argv[1:]:
        for ip in get_iprange(host):
            yield uthreads.spawn(probe_host(ip))

if __name__ == "__main__":
    uthreads.run(main)
