"""供本地浏览器 QA 使用的短生命周期网关进程。"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import local_gateway


local_gateway.start_gateway(18765)
while True:
    time.sleep(1)
