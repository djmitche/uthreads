# A simple, stupid SMTP client demonstrating socket operations with
# ulib.  Does not do any error checking, etc.

import uthreads
from ulib import socket

def client(host, helo, mailfrom, rcpttos, data):
    s = socket.socket()
    yield s.connect((host, 25))
    buf = ''

    while '\n' not in buf:
        try:
            d = yield s.recv(1024)
        except socket.error, why:
            print why.args[1]
            return
        if not d: return
        buf += d
    line, buf = buf.split('\n', 1)
    print line.strip()

    yield s.send('HELO %s\n' % helo)

    while '\n' not in buf:
        try:
            d = yield s.recv(1024)
        except socket.error, why:
            print why.args[1]
            return
        if not d: return
        buf += d
    line, buf = buf.split('\n', 1)
    print line.strip()

    yield s.send('MAIL From:<%s>\n' % mailfrom)

    while '\n' not in buf:
        try:
            d = yield s.recv(1024)
        except socket.error, why:
            print why.args[1]
            return
        if not d: return
        buf += d
    line, buf = buf.split('\n', 1)
    print line.strip()

    for rcptto in rcpttos:
        yield s.send('RCPT To:<%s>\n' % rcptto)

        while '\n' not in buf:
            try:
                d = yield s.recv(1024)
            except socket.error, why:
                print why.args[1]
                return
            if not d: return
            buf += d
        line, buf = buf.split('\n', 1)
        print line.strip()

    yield s.send('DATA\n')

    while '\n' not in buf:
        try:
            d = yield s.recv(1024)
        except socket.error, why:
            print why.args[1]
            return
        if not d: return
        buf += d
    line, buf = buf.split('\n', 1)
    print line.strip()

    yield s.send(data.replace('\n.\n', '\n..\n'))
    yield s.send('.\n')

    while '\n' not in buf:
        try:
            d = yield s.recv(1024)
        except socket.error, why:
            print why.args[1]
            return
        if not d: return
        buf += d
    line, buf = buf.split('\n', 1)
    print line.strip()

    yield s.send('QUIT\n')

    while '\n' not in buf:
        try:
            d = yield s.recv(1024)
        except socket.error, why:
            print why.args[1]
            return
        if not d: return
        buf += d
    line, buf = buf.split('\n', 1)
    print line.strip()

    yield s.close()

def main():
    yield client("localhost", "localhost", "dustin@v.igoro.us", [ "dustin@v.igoro.us" ],
"""From: dustin@v.igoro.us
To: dustin@v.igoro.us
Subject: test

Hi
""")

uthreads.run(main)
