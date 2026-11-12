"""Container regression: root HOME must not survive privilege dropping.

Run with a fixture config mount and --entrypoint python --network none.
"""
import asyncio
import os
from pathlib import Path
import pwd
import sys

sys.path.insert(0,'/app/docker')
sys.path.insert(0,'/app/x2_motion')
from entrypoint import prepare


async def check():
    import asyncssh
    from configuration import load_config,ssh_options
    load_config()
    options=asyncssh.SSHClientConnectionOptions(**ssh_options())
    assert options.known_hosts=='/data/ssh/known_hosts'
    assert Path.home()==Path(pwd.getpwuid(os.getuid()).pw_dir)
    assert os.getuid()==10001
    class Fixture(asyncssh.SSHServer):
        def begin_auth(self,username):return True
        def password_auth_supported(self):return True
        def validate_password(self,username,password):return username=='agi' and password=='fixture-only'
    async def process(channel):
        channel.stdout.write('sdk-fixture\n');channel.exit(0)
    key=asyncssh.generate_private_key('ssh-ed25519')
    server=await asyncssh.create_server(Fixture,'127.0.0.1',0,server_host_keys=[key],process_factory=process)
    try:
        port=server.get_port()
        with Path(options.known_hosts).open('xb') as output:
            output.write(('[127.0.0.1]:'+str(port)+' ').encode()+key.export_public_key())
        async with asyncssh.connect(**dict(ssh_options(),port=port)) as connection:
            result=await connection.run('fixture',check=True)
            assert result.stdout.strip()=='sdk-fixture'
    finally:
        server.close();await server.wait_closed()
    print('PASS: uid=10001; home=/home/x2; SSH initialization and password authentication')


if __name__=='__main__':
    # Reproduce the inherited root environment even if the image sets HOME.
    os.environ['HOME']='/root'
    prepare()
    asyncio.run(check())
