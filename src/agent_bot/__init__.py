from . import server_vars
from . import global_vars
from .uptime import *

try:
    from . import agent
except ImportError:
    agent = None
