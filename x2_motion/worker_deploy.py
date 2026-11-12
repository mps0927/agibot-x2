"""Sync this app's robot worker into its own unprivileged directory."""
WORKER_FILES=('x2_worker.py','lidar.py','capabilities.py','control_policy.py','posture_actions.py','joint_contract.py','robot_profile.json','sdk_catalog.py','sdk_interfaces.json')

async def install_worker(connection,root,target='/home/agi/agibot_dashboard'):
    async with connection.start_sftp_client() as sftp:
        await sftp.makedirs(target,exist_ok=True)
        for name in WORKER_FILES:
            await sftp.put(str(root/name),target+'/'+name)
