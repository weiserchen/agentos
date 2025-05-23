from agentos.regional.monitor import RegionalAgentMonitor
from agentos.regional.gateway import RegionalGateway
import multiprocessing

class RegionalManager:
    host: str
    gateway_port: int
    monitor_port: int

    def __init__(self, host: str = "0.0.0.0", gateway_port: int = 8100, monitor_port: int = 8101):
        self.host = host
        self.gateway_port = gateway_port
        self.monitor_port = monitor_port

    def run(self):
        agent_monitor = RegionalAgentMonitor()

        def agent_monitor_worker():
            agent_monitor.run(self.host, self.monitor_port)

        agent_monitor_process = multiprocessing.Process(target=agent_monitor_worker)
        agent_monitor_process.start()
        agent_monitor_addr = f'http://{self.host}:{self.monitor_port}'

        gateway = RegionalGateway(agent_monitor_addr)
        def gateway_worker():
            gateway.run(self.host, self.web_port)

        gateway_process = multiprocessing.Process(target=gateway_worker)
        gateway_process.start()

        try:
            agent_monitor_process.join()
            gateway_process.join()
        except KeyboardInterrupt:
            print("Stopping servers...")
            agent_monitor_process.terminate()
            gateway_process.terminate()