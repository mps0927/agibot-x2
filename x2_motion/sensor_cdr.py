"""Bounded CDR1 reader for sensor schemas advertised by the robot bridge.

Used only for telemetry absent from the installed Python SDK. Never creates
ROS types, publishers, requests, or executable code from advertised schemas.
"""
import math
import re
import struct

NUMBERS={'bool':('?',1),'byte':('B',1),'char':('B',1),'octet':('B',1),
    'int8':('b',1),'uint8':('B',1),'int16':('h',2),'uint16':('H',2),
    'int32':('i',4),'uint32':('I',4),'int64':('q',8),'uint64':('Q',8),
    'float32':('f',4),'float64':('d',8)}


def definitions(name,schema):
    if not isinstance(schema,str) or len(schema)>1024*1024:raise ValueError('Sensor schema size invalid')
    normalize=lambda value:value.replace('/msg/','/')
    name=normalize(name);current=name;types={current:[]}
    for line in schema.splitlines():
        line=line.split('#',1)[0].strip()
        if line.startswith('MSG:'):
            current=normalize(line[4:].strip());types.setdefault(current,[]);continue
        if not line or line.startswith('='):continue
        parts=line.split(None,2)
        if len(parts)<2 or '=' in parts[1] or (len(parts)>2 and parts[2].startswith('=')) or not re.fullmatch(r'[A-Za-z_]\w*',parts[1]):continue
        datatype=normalize(parts[0])
        if not re.fullmatch(r'[A-Za-z_]\w*(?:/[A-Za-z_]\w*)?(?:<=\d+)?(?:\[(?:<=)?\d*\])?',datatype):
            raise ValueError('Unsupported sensor field type')
        types[current].append((datatype,parts[1]))
        if sum(len(fields) for fields in types.values())>2000:raise ValueError('Sensor schema too complex')
    return name,types


def deserialize_sensor(payload,name,schema):
    if len(payload)<4 or len(payload)>1024*1024 or payload[:2] not in (b'\x00\x00',b'\x00\x01'):
        raise ValueError('Expected bounded CDR1 sensor data')
    endian='<' if payload[1]==1 else '>';data=memoryview(payload)[4:];position=0;budget=20000
    name,types=definitions(name,schema)

    def number(kind):
        nonlocal position,budget
        budget-=1
        if budget<0:raise ValueError('Sensor decode budget exceeded')
        code,size=NUMBERS[kind];position+=(size-position%size)%size
        if position+size>len(data):raise ValueError('Truncated sensor CDR data')
        value=struct.unpack_from(endian+code,data,position)[0];position+=size
        return value if not isinstance(value,float) or math.isfinite(value) else None

    def field(datatype,package,depth):
        nonlocal position
        if depth>16:raise ValueError('Sensor nesting limit exceeded')
        array=re.fullmatch(r'(.+)\[(.*)\]',datatype)
        if array:
            base,length=array.groups();count=number('uint32') if not length or length.startswith('<=') else int(length)
            if count>100000 or count<0:raise ValueError('Sensor array too large')
            if count>32 and base in NUMBERS:
                size=NUMBERS[base][1];position+=(size-position%size)%size;position+=count*size
                if position>len(data):raise ValueError('Truncated sensor array')
                return {'count':count}
            values=[]
            for index in range(count):
                value=field(base,package,depth+1)
                if index<32:values.append(value)
            return values if count<=32 else {'count':count,'first':values}
        if datatype in NUMBERS:return number(datatype)
        if datatype.startswith('string'):
            length=number('uint32')
            if length<1 or position+length>len(data):raise ValueError('Invalid sensor string')
            value=bytes(data[position:position+min(length-1,800)]).decode('utf-8',errors='replace');position+=length
            return value[:200]
        key=datatype if '/' in datatype else package+'/'+datatype
        if key not in types:raise ValueError('Missing nested sensor type: '+key)
        return {label:field(kind,key.split('/')[0],depth+1) for kind,label in types[key]}

    return field(name,name.split('/')[0],0)
