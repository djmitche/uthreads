#! /usr/bin/twistd -noy
"""The most basic chat protocol possible.

run me with twistd -y chatserver.py, and then connect with multiple
telnet clients to port 1025
"""
# based on the example "chatserver.py" from http://twistedmatrix.com/projects/core/documentation/examples/chatserver.py

from twisted.protocols import basic
from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.python import failure
import datetime
import uthreads
import uthreads.sync

def is_day_366():
    today = datetime.date.today() 
    if today - datetime.date(today.year, 1, 1) == 365:
        return True

class ConnectionLost(Exception): pass

class MyChat(basic.LineReceiver):
    def __init__(self):
        self.lines = uthreads.sync.Queue()
        self.line_deferred = None

    def connectionMade(self):
        print "Got new caller!"
        uthreads.spawn(self.handleConnection())

    def connectionLost(self, reason):
        print "Lost a caller!"
        self.lines.put_nowait('')

    def lineReceived(self, line):
        print "received", repr(line)
        self.lines.put_nowait(line)

    @uthreads.uthreaded
    def handleConnection(self):
        try:
            yield self.handleCall()
        except ConnectionLost:
            print "connection lost!"
        finally:
            self.transport.loseConnection()

    @uthreads.uthreaded
    def getLine(self):
        line = yield self.lines.get()
        if line == '':
            raise EOFError
        raise StopIteration(line)

    @uthreads.uthreaded
    def handleCall(self):
        self.transport.write(">> Hello, Thank you for contacting Zune technical support.\n")
        self.transport.write(">> Please enter your name.\n")
        name = (yield self.getLine()).strip()
        self.transport.write(">> Welcome, %s!\n" % name)
        self.transport.write(">> Please state your problem.\n")
        problem = (yield self.getLine()).strip()
        self.transport.write(">> Thank you.\n")
        if is_day_366():
            self.transport.write(">> Due to the overwhelming demand for the new DRM+ Zune, we are experiencing a heavy call volume.  Do you want to stay on the line?\n")
            yn = (yield self.getLine()).strip()
            if yn == "no":
                return
        
        while True:
            self.transport.write(">> Have you tried hard-resetting your Zune?\n")
            thatsnice = (yield self.getLine()).strip()
            if thatsnice == "OPERATOR!":
                self.transport.write(">> have a nice day!\n")
                return
            self.transport.write(">> Let me run some tests..\n")
            yield uthreads.sleep(1)

from twisted.internet import protocol
from twisted.application import service, internet

factory = protocol.ServerFactory()
factory.protocol = MyChat
factory.clients = []

application = service.Application("chatserver")
internet.TCPServer(1025, factory).setServiceParent(application)
