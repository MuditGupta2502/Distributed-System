import subprocess
import sys
import time
import argparse

def spawn_servers(num_generals, traitor_indices, base_port=50051, host="localhost"):
    processes = []
    # Build peers string in format: id:host:port.
    peers = []
    for i in range(num_generals):
        port = base_port + i
        peers.append(f"{i}:{host}:{port}")
    peers_str = ",".join(peers)
    for i in range(num_generals):
        port = base_port + i
        is_traitor = (i in traitor_indices)
        cmd = [sys.executable, "distributed_server.py",
               "--id", str(i),
               "--port", str(port),
               "--peers", peers_str]
        if is_traitor:
            cmd.append("--traitor")
        print(f"Spawning server for general {i} on port {port} {'(traitor)' if is_traitor else ''}")
        proc = subprocess.Popen(cmd)
        processes.append(proc)
    return processes

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Scale Distributed Byzantine General Servers")
    parser.add_argument("--num_generals", type=int, required=True, help="Total number of generals")
    parser.add_argument("--traitors", type=str, required=True, 
                        help="Comma-separated list of traitor indices, e.g., 3,4,7")
    parser.add_argument("--base_port", type=int, default=50051, help="Base port for servers")
    args = parser.parse_args()
    
    traitor_indices = [int(x.strip()) for x in args.traitors.split(',')]
    processes = spawn_servers(args.num_generals, traitor_indices, args.base_port)
    print("All servers spawned. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        print("Terminating servers...")
        for proc in processes:
            proc.terminate()
