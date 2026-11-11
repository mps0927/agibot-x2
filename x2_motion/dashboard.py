"""Repository entry point, corresponding to g1_motion/dashboard.py."""
from aiohttp import web
from app import create_app,parse_args

if __name__=='__main__':
    args=parse_args()
    web.run_app(create_app(args),host='127.0.0.1',port=args.port,access_log=None,shutdown_timeout=3)
