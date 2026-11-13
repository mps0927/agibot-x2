import base64,hashlib,json,socket,struct,threading,unittest
from unittest.mock import patch
from sensor_bridge import SensorBridge,Frames,client_frame,LIMIT
from sensor_cdr import deserialize_sensor


def server_frame(payload,opcode=1,final=True):
    header=bytes([(0x80 if final else 0)|opcode])
    return header+(bytes([len(payload)]) if len(payload)<126 else b'\x7e'+struct.pack('!H',len(payload)))+payload


class SensorBridgeContracts(unittest.TestCase):
    def test_fragmented_tcp_and_websocket_messages(self):
        parser=Frames();payload=json.dumps({'op':'advertise','channels':[]}).encode()
        raw=server_frame(payload[:12],1,False)+server_frame(b'ping',9)+server_frame(payload[12:],0)
        result=[]
        for byte in raw:result+=parser.feed(bytes([byte]))
        self.assertEqual(result,[(9,b'ping'),(1,payload)])

    def test_binary_cdr_payload_is_not_modified(self):
        payload=b'\x01'+struct.pack('<IQ',9,12345)+b'\x00\x01\x00\x00'+bytes(300)
        self.assertEqual(Frames().feed(server_frame(payload,2)),[(2,payload)])

    def test_oversize_and_masked_server_frames_are_rejected(self):
        with self.assertRaises(ValueError):Frames().feed(b'\x82\x7f'+struct.pack('!Q',LIMIT+1))
        with self.assertRaises(ValueError):Frames().feed(b'\x81\x81')
        with self.assertRaises(ValueError):Frames().feed(server_frame(b'bad',0))

    def test_outgoing_subscription_frames_are_masked(self):
        value={'op':'subscribe','subscriptions':[{'id':1,'channelId':10}]}
        payload=json.dumps(value).encode();raw=client_frame(payload);mask=raw[2:6]
        self.assertEqual(raw[0],0x81);self.assertTrue(raw[1]&0x80)
        self.assertEqual(bytes(v^mask[i%4] for i,v in enumerate(raw[6:])),payload)

    def test_cdr_nested_fields_padding_strings_and_arrays(self):
        schema='uint8 flag\nfloat64 temperature\nNested sample\nuint8[] data\n===\nMSG: test/Nested\nstring name\nint32 code\n'
        data=b'\x00\x01\x00\x00'+b'\x01'+bytes(7)+struct.pack('<d',12.5)
        data+=struct.pack('<I',4)+b'abc\x00'+struct.pack('<iI',-7,100)+bytes(100)
        result=deserialize_sensor(data,'test/msg/State',schema)
        self.assertEqual(result,dict(flag=1,temperature=12.5,sample=dict(name='abc',code=-7),data={'count':100}))

    def test_cdr_big_endian_and_invalid_data(self):
        self.assertEqual(deserialize_sensor(b'\x00\x00\x00\x00'+struct.pack('>I',123),'test/State','uint32 value'),{'value':123})
        for raw in (b'bad',b'\x00\x07\x00\x00'+bytes(8),b'\x00\x01\x00\x00'+bytes(2)):
            with self.assertRaises(ValueError):deserialize_sensor(raw,'test/State','uint32 value')
        with self.assertRaises(ValueError):deserialize_sensor(b'\x00\x01\x00\x00'+struct.pack('<I',1000000),'test/State','uint64[] values')

    def test_bridge_session_only_initializes_and_subscribes(self):
        client,server=socket.socketpair();sent=[];received=[];failures=[]
        bridge=SensorBridge(lambda item:item['topic']=='/sensor/lidar',lambda item,payload:(received.append(payload),bridge.stop.set()))
        def fixture():
            try:
                server.settimeout(3);data=b''
                while b'\r\n\r\n' not in data:data+=server.recv(4096)
                headers=dict(line.split(': ',1) for line in data.decode().split('\r\n')[1:] if ': ' in line)
                accept=base64.b64encode(hashlib.sha1((headers['Sec-WebSocket-Key']+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
                server.sendall(('HTTP/1.1 101 Switching Protocols\r\nSec-WebSocket-Accept: '+accept+'\r\nSec-WebSocket-Protocol: foxglove.websocket.v1\r\n\r\n').encode())
                buffer=bytearray()
                while len(sent)<2:
                    buffer.extend(server.recv(4096))
                    while len(buffer)>=2:
                        length=buffer[1]&127;offset=2
                        if length==126:
                            if len(buffer)<4:break
                            length=struct.unpack_from('!H',buffer,2)[0];offset=4
                        if len(buffer)<offset+4+length:break
                        mask=buffer[offset:offset+4];payload=bytes(v^mask[i%4] for i,v in enumerate(buffer[offset+4:offset+4+length]));del buffer[:offset+4+length]
                        message=json.loads(payload);sent.append(message)
                        if message['op']=='login':
                            server.sendall(server_frame(json.dumps(dict(op='advertise',channels=[dict(id=10,topic='/sensor/lidar',schemaName='sensor_msgs/msg/PointCloud2',encoding='cdr'),dict(id=11,topic='/joint/command',schemaName='test/Command',encoding='cdr')])).encode()))
                        elif message['op']=='subscribe':
                            server.sendall(server_frame(b'\x01'+struct.pack('<IQ',message['subscriptions'][0]['id'],0)+b'cdr-fixture',2))
            except Exception as exc:failures.append(exc)
        thread=threading.Thread(target=fixture);thread.start()
        try:
            with patch('sensor_bridge.socket.create_connection',return_value=client):bridge.session()
        finally:
            server.close();client.close();thread.join(timeout=3)
        self.assertEqual(failures,[]);self.assertEqual([value['op'] for value in sent],['login','subscribe'])
        self.assertEqual(sent[1]['subscriptions'],[{'id':1,'channelId':10}]);self.assertEqual(received,[b'cdr-fixture'])


if __name__=='__main__':unittest.main()
