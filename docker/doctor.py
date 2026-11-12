"""Read-only connection and LiDAR topic check on the existing SDK board."""
import asyncio
import shlex
import sys
from pathlib import Path
sys.path.insert(0,str(Path('/app/x2_motion')))
import asyncssh
from configuration import load_config,remote_paths,ssh_options
from preflight import check_robot,verify

async def main():
    load_config()
    print('Source checksums:',verify(),flush=True)
    await check_robot()
    _,sdk=remote_paths()
    command=('source /opt/ros/humble/setup.bash\nsource '+shlex.quote(sdk+'/install/setup.bash')+
             "\nros2 topic list -t | awk 'tolower($0) ~ /lidar|pointcloud2/'")
    async with asyncssh.connect(**ssh_options()) as connection:
        result=await connection.run('bash --noprofile --norc -c '+shlex.quote(command),timeout=20,check=True)
    topics=[line for line in result.stdout.splitlines() if line.startswith('/')]
    print('LiDAR / PointCloud2 topics:',flush=True)
    if topics:
        for topic in topics:print(topic,flush=True)
    else:print('점군 토픽을 찾지 못했습니다. 로봇 센서·ROS 설정을 확인하세요.',flush=True)

if __name__=='__main__':
    try:asyncio.run(main())
    except Exception as exc:print('연결 진단 실패:',str(exc),file=sys.stderr);sys.exit(1)
