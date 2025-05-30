import os
import signal
import subprocess

# ps -aux | grep pytest
# ps -aux | grep python

output = subprocess.check_output(["ps", "-eo", "pid=,args="], text=True)

for line in output.splitlines():
    pid, *cmd_parts = line.strip().split()
    full_cmd = " ".join(cmd_parts)
    if "pytest" in full_cmd:
        print(f"Killing PID {pid}")
        os.kill(int(pid), signal.SIGKILL)
