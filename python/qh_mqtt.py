"""Dependency-free MQTT 3.1.1: a built-in broker (the UNO Q is the server) and a client
for an external broker.

One asyncio loop runs in its own thread. The rest of the app uses the thread-safe
publish()/subscribe(); incoming messages arrive through on_message(topic, payload).
"""
import asyncio
import itertools
import threading
import time

CONNECT, CONNACK, PUBLISH, PUBACK, PUBREC, PUBREL, PUBCOMP = 1, 2, 3, 4, 5, 6, 7
SUBSCRIBE, SUBACK, UNSUBSCRIBE, UNSUBACK, PINGREQ, PINGRESP, DISCONNECT = 8, 9, 10, 11, 12, 13, 14


def topic_match(filt, topic):
    if topic.startswith("$") and filt[:1] in ("#", "+"):
        return False
    f, t = filt.split("/"), topic.split("/")
    for i, part in enumerate(f):
        if part == "#":
            return True
        if i >= len(t):
            return False
        if part != "+" and part != t[i]:
            return False
    return len(f) == len(t)


def enc_len(n):
    out = bytearray()
    while True:
        b = n % 128
        n //= 128
        if n:
            b |= 0x80
        out.append(b)
        if not n:
            return bytes(out)


def enc_str(s):
    b = s.encode("utf-8") if isinstance(s, str) else s
    return len(b).to_bytes(2, "big") + b


def packet(ptype, flags, body):
    return bytes([(ptype << 4) | flags]) + enc_len(len(body)) + body


def publish_packet(topic, payload, qos=0, retain=False, pid=0, dup=False):
    flags = (8 if dup else 0) | (qos << 1) | (1 if retain else 0)
    body = enc_str(topic) + (pid.to_bytes(2, "big") if qos else b"") + payload
    return packet(PUBLISH, flags, body)


async def read_packet(reader):
    b1 = (await reader.readexactly(1))[0]
    mult, n = 1, 0
    for _ in range(4):
        d = (await reader.readexactly(1))[0]
        n += (d & 127) * mult
        if not d & 128:
            break
        mult *= 128
    body = await reader.readexactly(n) if n else b""
    return b1 >> 4, b1 & 0x0F, body


def _str_at(buf, i):
    ln = int.from_bytes(buf[i:i + 2], "big")
    return buf[i + 2:i + 2 + ln], i + 2 + ln


class _Session:
    def __init__(self, cid, writer, keepalive, will):
        self.cid, self.writer, self.keepalive, self.will = cid, writer, keepalive, will
        self.subs = {}
        self.last = time.time()
        self.pids = itertools.cycle(range(1, 65535))
        self.addr = writer.get_extra_info("peername")

    def send(self, data):
        try:
            self.writer.write(data)
        except Exception:
            pass


class Broker:
    def __init__(self, hub, port, username="", password=""):
        self.hub, self.port, self.user, self.pw = hub, port, username, password
        self.sessions = {}
        self.retained = {}
        self.server = None

    async def start(self):
        self.server = await asyncio.start_server(self._handle, "0.0.0.0", self.port)
        self.hub.log("Built-in MQTT broker listening on port %d" % self.port)
        asyncio.ensure_future(self._watchdog())

    async def stop(self):
        for s in list(self.sessions.values()):
            s.writer.close()
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def _watchdog(self):
        while self.server and self.server.is_serving():
            await asyncio.sleep(5)
            now = time.time()
            for s in list(self.sessions.values()):
                if s.keepalive and now - s.last > s.keepalive * 1.5:
                    self.hub.log("MQTT client timed out: %s" % s.cid, "warn")
                    s.writer.close()

    def route(self, topic, payload, qos=0, retain=False):
        if retain:
            if payload:
                self.retained[topic] = (payload, qos)
            else:
                self.retained.pop(topic, None)
        for s in list(self.sessions.values()):
            best = -1
            for f, q in s.subs.items():
                if topic_match(f, topic):
                    best = max(best, q)
            if best >= 0:
                oq = min(qos, best, 1)
                s.send(publish_packet(topic, payload, oq, False, next(s.pids) if oq else 0))
        self.hub._deliver_local(topic, payload)

    async def _handle(self, reader, writer):
        sess = None
        try:
            ptype, _, body = await asyncio.wait_for(read_packet(reader), 10)
            if ptype != CONNECT:
                writer.close()
                return
            proto, i = _str_at(body, 0)
            level, cflags = body[i], body[i + 1]
            keepalive = int.from_bytes(body[i + 2:i + 4], "big")
            i += 4
            cid, i = _str_at(body, i)
            will = None
            if cflags & 0x04:
                wt, i = _str_at(body, i)
                wm, i = _str_at(body, i)
                will = (wt.decode(), wm, (cflags >> 3) & 3, bool(cflags & 0x20))
            user = pw = b""
            if cflags & 0x80:
                user, i = _str_at(body, i)
            if cflags & 0x40:
                pw, i = _str_at(body, i)
            if proto not in (b"MQTT", b"MQIsdp"):
                writer.write(packet(CONNACK, 0, b"\x00\x01"))
                writer.close()
                return
            if self.user and (user.decode() != self.user or pw.decode() != self.pw):
                writer.write(packet(CONNACK, 0, b"\x00\x05"))
                await writer.drain()
                writer.close()
                self.hub.log("MQTT connection refused: wrong user name or password", "warn")
                return
            cid = cid.decode() or "anon-%d" % id(writer)
            old = self.sessions.get(cid)
            if old:
                old.will = None
                old.writer.close()
            sess = _Session(cid, writer, keepalive, will)
            self.sessions[cid] = sess
            writer.write(packet(CONNACK, 0, b"\x00\x00"))
            self.hub.log("MQTT client connected: %s %s" % (cid, sess.addr))
            while True:
                ptype, flags, body = await read_packet(reader)
                sess.last = time.time()
                if ptype == PUBLISH:
                    qos = (flags >> 1) & 3
                    t, j = _str_at(body, 0)
                    pid = 0
                    if qos:
                        pid = int.from_bytes(body[j:j + 2], "big")
                        j += 2
                    self.route(t.decode(), body[j:], min(qos, 1), bool(flags & 1))
                    if qos == 1:
                        sess.send(packet(PUBACK, 0, pid.to_bytes(2, "big")))
                    elif qos == 2:
                        sess.send(packet(PUBREC, 0, pid.to_bytes(2, "big")))
                elif ptype == PUBREL:
                    sess.send(packet(PUBCOMP, 0, body[:2]))
                elif ptype == SUBSCRIBE:
                    pid, j, granted = body[:2], 2, bytearray()
                    newf = []
                    while j < len(body):
                        f, j = _str_at(body, j)
                        q = min(body[j], 1)
                        j += 1
                        sess.subs[f.decode()] = q
                        newf.append((f.decode(), q))
                        granted.append(q)
                    sess.send(packet(SUBACK, 0, pid + bytes(granted)))
                    for f, q in newf:
                        for t, (p, rq) in list(self.retained.items()):
                            if topic_match(f, t):
                                oq = min(q, rq)
                                sess.send(publish_packet(t, p, oq, True, next(sess.pids) if oq else 0))
                elif ptype == UNSUBSCRIBE:
                    pid, j = body[:2], 2
                    while j < len(body):
                        f, j = _str_at(body, j)
                        sess.subs.pop(f.decode(), None)
                    sess.send(packet(UNSUBACK, 0, pid))
                elif ptype == PINGREQ:
                    sess.send(packet(PINGRESP, 0, b""))
                elif ptype == DISCONNECT:
                    sess.will = None
                    break
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, asyncio.TimeoutError, OSError):
            pass
        except Exception as e:
            self.hub.log("MQTT broker problem: %r" % e, "err")
        finally:
            if sess and self.sessions.get(sess.cid) is sess:
                del self.sessions[sess.cid]
                if sess.will:
                    t, m, q, r = sess.will
                    self.route(t, m, min(q, 1), r)
                self.hub.log("MQTT client left: %s" % sess.cid)
            try:
                writer.close()
            except Exception:
                pass


class Client:
    def __init__(self, hub, host, port, username, password, client_id, will):
        self.hub, self.host, self.port = hub, host, port
        self.user, self.pw, self.cid, self.will = username, password, client_id, will
        self.writer = None
        self.connected = False
        self.task = None
        self.pids = itertools.cycle(range(1, 65535))
        self.error = ""

    async def start(self):
        self.task = asyncio.ensure_future(self._run())

    async def stop(self):
        if self.writer and self.connected:
            try:
                self.writer.write(packet(DISCONNECT, 0, b""))
                await self.writer.drain()
            except Exception:
                pass
        if self.task:
            self.task.cancel()
        if self.writer:
            self.writer.close()
        self.connected = False

    def send(self, data):
        if self.writer and self.connected:
            try:
                self.writer.write(data)
            except Exception:
                pass

    def subscribe(self, filters):
        if not filters:
            return
        body = next(self.pids).to_bytes(2, "big")
        for f in filters:
            body += enc_str(f) + b"\x00"
        self.send(packet(SUBSCRIBE, 2, body))

    async def _run(self):
        delay = 2
        while True:
            try:
                reader, self.writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), 10)
                flags = 0x02
                payload = enc_str(self.cid)
                if self.will:
                    t, m = self.will
                    flags |= 0x04 | 0x20
                    payload += enc_str(t) + enc_str(m)
                if self.user:
                    flags |= 0x80
                    payload += enc_str(self.user)
                    if self.pw:
                        flags |= 0x40
                        payload += enc_str(self.pw)
                var = enc_str("MQTT") + bytes([4, flags]) + (30).to_bytes(2, "big")
                self.writer.write(packet(CONNECT, 0, var + payload))
                await self.writer.drain()
                ptype, _, body = await asyncio.wait_for(read_packet(reader), 10)
                if ptype != CONNACK or body[1] != 0:
                    rc = body[1] if len(body) > 1 else -1
                    raise ConnectionError("broker refused the connection, code %s (5 = wrong user name or password)" % rc)
                self.connected = True
                self.error = ""
                delay = 2
                self.hub.log("Connected to MQTT broker %s:%d" % (self.host, self.port))
                self.subscribe(list(self.hub.local_filters))
                self.hub._on_connected()
                pinger = asyncio.ensure_future(self._ping())
                try:
                    while True:
                        ptype, flags, body = await read_packet(reader)
                        if ptype == PUBLISH:
                            qos = (flags >> 1) & 3
                            t, j = _str_at(body, 0)
                            if qos:
                                pid = body[j:j + 2]
                                j += 2
                                self.send(packet(PUBACK if qos == 1 else PUBREC, 0, pid))
                            self.hub._deliver_local(t.decode(), body[j:])
                        elif ptype == PUBREL:
                            self.send(packet(PUBCOMP, 0, body[:2]))
                finally:
                    pinger.cancel()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.error = str(e) or e.__class__.__name__
                if self.connected:
                    self.hub.log("MQTT connection lost: %s" % self.error, "warn")
                else:
                    self.hub.log("Cannot reach MQTT broker %s:%d: %s" % (self.host, self.port, self.error), "warn")
            self.connected = False
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)

    async def _ping(self):
        while True:
            await asyncio.sleep(20)
            self.send(packet(PINGREQ, 0, b""))


class MqttHub:
    """The one interface the engine uses."""

    def __init__(self, log, on_message, on_connected):
        self.log = log
        self.on_message = on_message
        self.on_connected_cb = on_connected
        self.local_filters = set()
        self.mode = "off"
        self.broker = None
        self.client = None
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self._thread, daemon=True, name="mqtt").start()

    def _thread(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _run(self, coro, wait=True):
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)
        if wait:
            try:
                return fut.result(15)
            except Exception as e:
                self.log("MQTT: %s" % e, "err")

    # ---- lifecycle ----
    def configure(self, s, node, avail_topic):
        self._run(self._configure(s, node, avail_topic))

    async def _configure(self, s, node, avail_topic):
        if self.broker:
            await self.broker.stop()
            self.broker = None
        if self.client:
            await self.client.stop()
            self.client = None
        self.mode = s.get("mode", "off")
        if self.mode == "internal":
            self.broker = Broker(self, int(s.get("port", 1883)), s.get("username", ""), s.get("password", ""))
            try:
                await self.broker.start()
            except OSError as e:
                self.log("Could not start the broker on port %s: %s" % (s.get("port"), e), "err")
                self.broker = None
                return
            self.loop.call_soon(self._on_connected)
        elif self.mode == "external":
            host = (s.get("host") or "").strip()
            if not host:
                self.log("The external broker address is empty", "warn")
                return
            self.client = Client(self, host, int(s.get("ext_port", 1883)), s.get("username", ""),
                                 s.get("password", ""), node, (avail_topic, b"offline"))
            await self.client.start()

    def _on_connected(self):
        try:
            self.on_connected_cb()
        except Exception as e:
            self.log("MQTT on_connected: %r" % e, "err")

    # ---- messaging ----
    def publish(self, topic, payload, retain=False):
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        self.loop.call_soon_threadsafe(self._publish, topic, payload, retain)

    def _publish(self, topic, payload, retain):
        if self.broker:
            self.broker.route(topic, payload, 0, retain)
        elif self.client and self.client.connected:
            self.client.send(publish_packet(topic, payload, 0, retain))

    def subscribe(self, filt):
        if filt in self.local_filters:
            return
        self.local_filters.add(filt)
        self.loop.call_soon_threadsafe(self._subscribed, filt)

    def _subscribed(self, filt):
        if self.client and self.client.connected:
            self.client.subscribe([filt])
        if self.broker:                       # hand over what the broker already retains
            for t, (p, _q) in list(self.broker.retained.items()):
                if topic_match(filt, t):
                    try:
                        self.on_message(t, p.decode("utf-8", "replace"))
                    except Exception as e:
                        self.log("Problem handling an MQTT message: %r" % e, "err")

    def _deliver_local(self, topic, payload):
        for f in list(self.local_filters):
            if topic_match(f, topic):
                try:
                    self.on_message(topic, payload.decode("utf-8", "replace"))
                except Exception as e:
                    self.log("Problem handling an MQTT message: %r" % e, "err")
                return

    def status(self):
        if self.mode == "internal":
            if not self.broker:
                return {"mode": "internal", "ok": False, "text": "broker could not start"}
            names = [s.cid for s in self.broker.sessions.values()]
            return {"mode": "internal", "ok": True, "clients": names,
                    "text": "broker on, %d clients" % len(names)}
        if self.mode == "external":
            c = self.client
            ok = bool(c and c.connected)
            return {"mode": "external", "ok": ok,
                    "text": "connected" if ok else ("connecting... " + (c.error if c else ""))}
        return {"mode": "off", "ok": False, "text": "off"}

    def shutdown(self, avail_topic):
        self._publish_sync(avail_topic, b"offline")

    def _publish_sync(self, topic, payload):
        async def f():
            self._publish(topic, payload, True)
            await asyncio.sleep(0.2)
        self._run(f())
