#! /usr/bin/twistd -noy
"""The most basic chat protocol possible.

run me with twistd -y chatserver.py, and then connect with multiple
telnet clients to port 1025
"""
# based on the example "chatserver.py" from http://twistedmatrix.com/projects/core/documentation/examples/chatserver.py

from twisted.protocols import basic
from twisted.internet import reactor
import datetime

def is_day_366():
    today = datetime.date.today() 
    if today - datetime.date(today.year, 1, 1) == 365:
        return True

class MyChat(basic.LineReceiver):
    def connectionMade(self):
        print "Got new caller!"
        self.sayHello()

    def connectionLost(self, reason):
        print "Lost a caller!"

    def lineReceived(self, line):
        print "received", repr(line)
        self.state(line)

    # states

    def sayHello(self):
        self.transport.write(">> Hello.  Thank you for contacting Zune technical support.\n")
        self.transport.write(">> Please enter your name.\n")
        self.state = self.getName

    def getName(self, line):
        self.name = line.strip()
        self.transport.write(">> Welcome, %s!\n" % self.name)
        self.transport.write(">> Please state your problem.\n")
        self.state = self.getProblem

    def getProblem(self, line):
        self.problem = line.strip()
        self.transport.write(">> Thank you.\n")
        if is_day_366():
            self.transport.write(">> Due to the overwhelming demand for the new DRM+ Zune, we are experiencing a heavy call volume.  Do you want to stay on the line?\n")
            self.state = self.getStayOnLine
            return
        self.startTryResetting()

    def getStayOnLine(self, line):
        if line.strip() == "no":
            self.transport.loseConnection()
            return
        self.startTryResetting()

    def startTryResetting(self):
        self.transport.write(">> Have you tried hard-resetting your Zune?\n")
        self.state = self.triedResetting

    def triedResetting(self, line):
        if line.strip() == "OPERATOR!":
            self.transport.write(">> Have a nice day!\n")
            self.transport.loseConnection()
            return

        self.transport.write(">> Let me run some tests..\n")
        reactor.callLater(1.0, self.startTryResetting)


from twisted.internet import protocol
from twisted.application import service, internet

factory = protocol.ServerFactory()
factory.protocol = MyChat
factory.clients = []

application = service.Application("chatserver")
internet.TCPServer(1025, factory).setServiceParent(application)
