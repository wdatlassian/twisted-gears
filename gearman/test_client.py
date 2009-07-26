import struct

from zope.interface import implements

from twisted.trial import unittest
from twisted.internet import interfaces, reactor, defer

import client, constants

class TestTransport(object):

    implements(interfaces.ITransport)

    disconnecting = False

    def __init__(self):
        self.received = []
        self.disconnected = 0

    def write(self, data):
        self.received.append(data)

    def writeSequence(self, data):
        self.received.extend(data)

    def loseConnection(self):
        self.disconnected += 1

    def getPeer(self):
        return None

    def getHost(self):
        return None

class ExpectedFailure(Exception):
    pass

class GearmanProtocolTest(unittest.TestCase):

    def setUp(self):
        self.trans = TestTransport()
        self.gp = client.GearmanProtocol()
        self.gp.makeConnection(self.trans)

    def assertReceived(self, cmd, data):
        self.assertEquals(["\0REQ",
                           struct.pack(">II", cmd, len(data)),
                           data],
                          self.trans.received)

    def write_response(self, cmd, data):
        self.gp.dataReceived("\0RES")
        self.gp.dataReceived(struct.pack(">II", cmd, len(data)))
        self.gp.dataReceived(data)

    def test_makeConnection(self):
        self.assertEquals(0, self.gp.receivingCommand)
        self.assertEquals([], list(self.gp.deferreds))
        self.assertEquals([], list(self.gp.unsolicited_handlers))

    def test_send_raw(self):
        self.gp.send_raw(11, "some data")
        self.assertReceived(11, "some data")
        self.assertEquals(0, len(self.gp.deferreds))

    def test_send(self):
        self.gp.send(11, "some data")
        self.assertReceived(11, "some data")
        self.assertEquals(1, len(self.gp.deferreds))

    def test_connectionLost(self):
        d = self.gp.send(11, "test")
        d.addCallback(lambda x: unittest.FailTest())
        d.addErrback(lambda x: x.trap(ExpectedFailure))
        self.gp.connectionLost(ExpectedFailure())
        return d

    def test_badResponse(self):
        self.assertEquals(0, self.trans.disconnected)
        self.trans.shouldLoseConnection = True
        self.gp.dataReceived("X" * constants.HEADER_LEN)
        reactor.callLater(0, self.assertEquals, 1, self.trans.disconnected)

    def test_pre_sleep(self):
        d = self.gp.pre_sleep()
        self.assertReceived(constants.PRE_SLEEP, "")

    def test_send_echo(self):
        d = self.gp.echo()
        self.assertReceived(constants.ECHO_REQ, "hello")

    def test_echoRt(self):
        """Test an echo round trip."""
        d = self.gp.echo()
        d.addCallback(lambda x:
                          self.assertEquals(x,
                                            (constants.ECHO_RES, "hello")))
        self.write_response(constants.ECHO_RES, "hello")
        return d

    def test_register_unsolicited(self):
        def cb(cmd, data):
            pass
        self.gp.register_unsolicited(cb)
        self.assertEquals(1, len(self.gp.unsolicited_handlers))
        self.gp.register_unsolicited(cb)
        self.assertEquals(1, len(self.gp.unsolicited_handlers))
        self.gp.register_unsolicited(lambda a,b: True)
        self.assertEquals(2, len(self.gp.unsolicited_handlers))

    def test_unregister_unsolicited(self):
        def cb(cmd, data):
            pass
        self.gp.register_unsolicited(cb)
        self.assertEquals(1, len(self.gp.unsolicited_handlers))
        self.gp.unregister_unsolicited(cb)
        self.assertEquals(0, len(self.gp.unsolicited_handlers))

    def test_unsolicitedCallbackHandling(self):
        d = defer.Deferred()
        self.gp.register_unsolicited(lambda cmd, data: d.callback(True))
        self.write_response(constants.WORK_COMPLETE, "test\0")
        return d

