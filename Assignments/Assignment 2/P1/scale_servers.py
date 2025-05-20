import subprocess
import time
import argparse

def spawn_backend_servers(num_servers, starting_port, consul_host, consul_port, report_interval):
    processes = []
    for i in range(num_servers):
        backend_id = f"backend{i+1}"
        port = starting_port + i
        cmd = [
            "python3", "backend_server.py",
            "--id", backend_id,
            "--port", str(port),
            "--consul_host", consul_host,
            "--consul_port", str(consul_port),
            "--report_interval", str(report_interval)
        ]
        print(f"Starting server {backend_id} on port {port}: {' '.join(cmd)}")
        p = subprocess.Popen(cmd)
        processes.append(p)
    return processes

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spawn multiple backend servers.")
    parser.add_argument("--num_servers", type=int, default=10, help="Number of backend servers to spawn")
    parser.add_argument("--starting_port", type=int, default=50052, help="Starting port for backend servers")
    parser.add_argument("--consul_host", type=str, default="localhost", help="Consul host")
    parser.add_argument("--consul_port", type=int, default=8500, help="Consul port")
    parser.add_argument("--report_interval", type=int, default=5, help="Interval (in seconds) for reporting load")
    args = parser.parse_args()

    processes = spawn_backend_servers(args.num_servers, args.starting_port, args.consul_host, args.consul_port, args.report_interval)

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("Terminating backend servers...")
        for p in processes:
            p.terminate()
