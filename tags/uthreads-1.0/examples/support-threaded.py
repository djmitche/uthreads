#! /usr/bin/python

import os
import time
import socket
import threading
import datetime

def is_day_366():
    today = datetime.date.today() 
    if today - datetime.date(today.year, 1, 1) == 365:
        return True

def handle_connection(sock, addr):
    # wrap the sock in an os file
    sockf = os.fdopen(sock.fileno(), "r+")
    print >>sockf, ">> Hello, %s, Thank you for contacting Zune technical support." % (addr,)
    print >>sockf, ">> Please enter your name."
    name = sockf.readline().strip()
    print >>sockf, ">> Welcome, %s!" % name
    print >>sockf, ">> Please state your problem."
    problem = sockf.readline().strip()
    print >>sockf, ">> Thank you."
    if is_day_366():
        print >>sockf, ">> Due to the overwhelming demand for the new DRM+ Zune, we are experiencing a heavy call volume.  Do you want to stay on the line?"
        yn = sockf.readline().strip()
        if yn == "no":
            return
    
    while True:
        print >>sockf, ">> Have you tried hard-resetting your Zune?"
        thatsnice = sockf.readline().strip()
        if thatsnice == "OPERATOR!":
            print >>sockf, ">> have a nice day!"
            return
        print >>sockf, ">> Let me run some tests.."
        sockf.flush()
        time.sleep(1)

def main():
    listening = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listening.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listening.bind(("", 1025))
    print "listening on %s" % (listening.getsockname(),)
    listening.listen(5)
    while 1:
        sock, addr = listening.accept()
        threading.Thread(target=handle_connection, args=(sock, addr)).start()

main()
