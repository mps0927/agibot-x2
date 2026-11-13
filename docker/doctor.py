"""Read-only connection and LiDAR topic check on the existing SDK board."""
import asyncio
import shlex
import sys
from pathlib import Path
sys.path.insert(0,str(Path('/app/x2_motion')))
import asyncssh
from configuration import load_config,remote_paths,ssh_options
from preflight import check_robot
from lidar import DEFAULT_TOPIC

async def main():
    load_config()
    await check_robot()
    home,sdk=remote_paths()
    command=('source /opt/ros/humble/setup.bash\nsource '+shlex.quote(sdk+'/install/setup.bash')+
             "\nros2 topic list -t | awk 'tolower($0) ~ /lidar|pointcloud2/'\nros2 topic info "+shlex.quote(DEFAULT_TOPIC))
    async with asyncssh.connect(**ssh_options()) as connection:
        result=await connection.run('bash --noprofile --norc -c '+shlex.quote(command),timeout=20)
    topics=[line for line in result.stdout.splitlines() if line.startswith('/')]
    print('LiDAR / PointCloud2 topics:',flush=True)
    if topics:
        for topic in topics:print(topic,flush=True)
    else:print('점군 토픽을 찾지 못했습니다. 로봇 센서·ROS 설정을 확인하세요.',flush=True)
    counts=[line for line in result.stdout.splitlines() if line.startswith(('Publisher count:','Subscription count:'))]
    for line in counts:print(line,flush=True)
    if 'Publisher count: 0' in counts:
        print('직접 SDK의 점군 발행자가 없습니다. 기존 센서 브리지 경로를 확인합니다.',flush=True)
    probe=('import json,sys,time\nfrom pathlib import Path\nsys.path.insert(0,'+repr(home+'/agibot_dashboard')+')\n'
           'from sensor_bridge import SensorBridge\nfrom rclpy.serialization import deserialize_message\n'
           'from sensor_msgs.msg import PointCloud2\nreceived=[]\n'
           'def receive(channel,payload):\n'
           '    message=deserialize_message(payload,PointCloud2)\n'
           '    received.append(dict(points=message.width*message.height,frame_id=message.header.frame_id))\n'
           'bridge=SensorBridge(lambda channel:channel["topic"]=='+repr(DEFAULT_TOPIC)+',receive)\n'
           'bridge.start();time.sleep(5)\n'
           'print("X2_BRIDGE_RESULT "+json.dumps(dict(connected=bridge.connected,frames=len(received),latest=received[-1] if received else None,error=bridge.error)))\n'
           'bridge.close()\n')
    command='source /opt/ros/humble/setup.bash\nsource '+shlex.quote(sdk+'/install/setup.bash')+'\npython3 -c '+shlex.quote(probe)
    async with asyncssh.connect(**ssh_options()) as connection:
        result=await connection.run('bash --noprofile --norc -c '+shlex.quote(command),timeout=15)
    lines=[line for line in result.stdout.splitlines() if line.startswith('X2_BRIDGE_RESULT ')]
    for line in lines:print(line,flush=True)
    if not lines:print('센서 브리지 검사 도구를 준비 중입니다. 대시보드 실행 후 다시 확인하세요.',flush=True)

if __name__=='__main__':
    try:asyncio.run(main())
    except Exception as exc:print('연결 진단 실패:',str(exc),file=sys.stderr);sys.exit(1)
