from .monitor import RegionalAgentMonitor
from .webserver import RegionalWebServer
import multiprocessing

class RegionalManager:
    host: str
    web_port: int
    monitor_port: int

    def __init__(self, host: str = "0.0.0.0", web_port: int = 8100, monitor_port: int = 8101):
        self.host = host
        self.web_port = web_port
        self.monitor_port = monitor_port

    def run(self):
        agent_monitor = RegionalAgentMonitor()

        def agent_monitor_worker():
            agent_monitor.run(self.host, self.monitor_port)

        agent_monitor_process = multiprocessing.Process(target=agent_monitor_worker)
        agent_monitor_process.start()
        agent_monitor_addr = f'http://{self.host}:{self.monitor_port}'

        web_server = RegionalWebServer(agent_monitor_addr)
        def web_server_worker():
            web_server.run(self.host, self.web_port)

        web_server_process = multiprocessing.Process(target=web_server_worker)
        web_server_process.start()

        try:
            agent_monitor_process.join()
            web_server_process.join()
        except KeyboardInterrupt:
            print("Stopping servers...")
            agent_monitor_process.terminate()
            web_server_process.terminate()