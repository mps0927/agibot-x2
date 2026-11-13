"""Read-only access to the robot's existing local coBridge sensor server.

Only login metadata and subscribe/unsubscribe/pong are sent. No publisher,
service call, parameter mutation, or additional host port is exposed.
"""
import base64
import hashlib
import json
import os
import select
import socket
import struct
import threading
import time

LIMIT=16*1024*1024
PROTOCOL='foxglove.websocket.v1'


def client_frame(payload,opcode=1):
    if len(payload)>LIMIT:raise ValueError('Sensor bridge message too large')
    mask=os.urandom(4);length=len(payload)
    header=bytes([0x80|opcode,0x80|length]) if length<126 else bytes([0x80|opcode,0xfe])+struct.pack('!H',length) if length<65536 else bytes([0x80|opcode,0xff])+struct.pack('!Q',length)
    return header+mask+bytes(value^mask[index%4] for index,value in enumerate(payload))


class Frames:
    def __init__(self):self.buffer=bytearray();self.fragments=bytearray();self.fragment_opcode=None

    def feed(self,chunk):
        self.buffer.extend(chunk);messages=[]
        while len(self.buffer)>=2:
            first,second=self.buffer[:2];length=second&127;position=2
            if first&0x70 or second&0x80:raise ValueError('Unsupported sensor WebSocket frame')
            if length==126:
                if len(self.buffer)<4:break
                length=struct.unpack_from('!H',self.buffer,2)[0];position=4
            elif length==127:
                if len(self.buffer)<10:break
                length=struct.unpack_from('!Q',self.buffer,2)[0];position=10
            if length>LIMIT:raise ValueError('Sensor bridge frame too large')
            if len(self.buffer)<position+length:break
            payload=bytes(self.buffer[position:position+length]);del self.buffer[:position+length]
            opcode=first&15;final=bool(first&0x80)
            if opcode in (8,9,10):
                if not final or length>125:raise ValueError('Invalid sensor WebSocket control frame')
                messages.append((opcode,payload));continue
            if opcode in (1,2):
                if self.fragment_opcode is not None:raise ValueError('Overlapping sensor messages')
                if final:messages.append((opcode,payload));continue
                self.fragment_opcode=opcode;self.fragments.extend(payload)
            elif opcode==0 and self.fragment_opcode is not None:
                self.fragments.extend(payload)
                if final:
                    messages.append((self.fragment_opcode,bytes(self.fragments)))
                    self.fragments.clear();self.fragment_opcode=None
            else:raise ValueError('Invalid sensor WebSocket continuation')
            if len(self.fragments)>LIMIT:raise ValueError('Sensor bridge message too large')
        if len(self.buffer)>LIMIT+10:raise ValueError('Sensor bridge buffer too large')
        return messages


class SensorBridge:
    def __init__(self,wanted,on_message):
        self.wanted=wanted;self.on_message=on_message
        self.channels={};self.connected=False;self.error='';self.stop=threading.Event()
        self.lock=threading.Lock();self.thread=None

    def start(self):
        self.thread=threading.Thread(target=self.run,daemon=True,name='x2-sensor-bridge');self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=3)

    def topics(self):
        with self.lock:
            return [(item['topic'],[item['schemaName']]) for item in self.channels.values()]

    def available(self,topic):
        with self.lock:return self.connected and any(item['topic']==topic for item in self.channels.values())

    def run(self):
        while not self.stop.is_set():
            try:self.session()
            except (OSError,ValueError,KeyError,RuntimeError) as exc:self.error=str(exc)[:300]
            finally:
                self.connected=False
                with self.lock:self.channels={}
            self.stop.wait(2)

    def session(self):
        with socket.create_connection(('127.0.0.1',21274),timeout=2) as stream:
            stream.settimeout(2)
            key=base64.b64encode(os.urandom(16)).decode()
            request=('GET / HTTP/1.1\r\nHost: localhost:21274\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                     'Sec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: '+PROTOCOL+'\r\nSec-WebSocket-Key: '+key+'\r\n\r\n')
            stream.sendall(request.encode());received=b''
            while b'\r\n\r\n' not in received:
                chunk=stream.recv(4096)
                if not chunk:raise ConnectionError('Sensor bridge closed during handshake')
                received+=chunk
                if len(received)>65536:raise ValueError('Sensor bridge handshake too large')
            header,pending=received.split(b'\r\n\r\n',1)
            lines=header.decode('ascii').split('\r\n');headers={k.lower().strip():v.strip() for k,v in (line.split(':',1) for line in lines[1:] if ':' in line)}
            expected=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
            if ' 101 ' not in lines[0] or headers.get('sec-websocket-accept')!=expected or headers.get('sec-websocket-protocol')!=PROTOCOL:
                raise ValueError('Sensor bridge handshake rejected')
            def send(value):stream.sendall(client_frame(json.dumps(value,separators=(',',':')).encode()))
            send(dict(op='login',userId='local-x2-dashboard',username='X2 local dashboard'))
            decoder=Frames();subscriptions={};next_id=1;update_at=0.
            self.connected=True;self.error=''
            while not self.stop.is_set():
                if pending:
                    for opcode,payload in decoder.feed(pending):
                        if opcode==8:raise ConnectionError('Sensor bridge closed')
                        if opcode==9:stream.sendall(client_frame(payload,10))
                        elif opcode==1:
                            message=json.loads(payload)
                            if message.get('op')=='advertise':
                                with self.lock:
                                    for item in message.get('channels',[]):
                                        if item.get('encoding')=='cdr' and type(item.get('id')) is int and isinstance(item.get('topic'),str) and isinstance(item.get('schemaName'),str):self.channels[item['id']]=item
                            elif message.get('op')=='unadvertise':
                                with self.lock:
                                    for ident in message.get('channelIds',[]):self.channels.pop(ident,None)
                            elif message.get('op')=='status' and message.get('level')==2:self.error=str(message.get('message',''))[:300]
                        elif opcode==2 and len(payload)>=13 and payload[0]==1:
                            subscription=struct.unpack_from('<I',payload,1)[0]
                            item=next((item for item,sid in subscriptions.values() if sid==subscription),None)
                            if item and self.wanted(item):
                                try:self.on_message(item,payload[13:])
                                except Exception as exc:self.error=str(exc)[:300]
                    pending=b''
                if time.monotonic()>=update_at:
                    with self.lock:channels=dict(self.channels)
                    removed=[sid for ident,(item,sid) in subscriptions.items() if ident not in channels or not self.wanted(item)]
                    if removed:
                        send(dict(op='unsubscribe',subscriptionIds=removed))
                        subscriptions={ident:value for ident,value in subscriptions.items() if value[1] not in removed}
                    added=[]
                    for ident,item in channels.items():
                        if ident not in subscriptions and self.wanted(item):
                            subscriptions[ident]=(item,next_id);added.append(dict(id=next_id,channelId=ident));next_id+=1
                    if added:send(dict(op='subscribe',subscriptions=added))
                    update_at=time.monotonic()+.5
                if select.select([stream],[],[],.2)[0]:
                    pending=stream.recv(65536)
                    if not pending:raise ConnectionError('Sensor bridge disconnected')
