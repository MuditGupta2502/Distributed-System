import grpc
from concurrent import futures
import time
import threading
import argparse
import random  # <-- Import random for selection among candidates

import load_balancer_pb2
import load_balancer_pb2_grpc

# Global list to store registered backends and a lock for thread safety
backend_servers = []
backend_lock = threading.Lock()

def register_lb_service(lb_port, consul_host="localhost", consul_port=8500):
    import consul
    c = consul.Consul(host=consul_host, port=consul_port)
    service_id = f"lb-server-{lb_port}"
    # Register LB server with Consul under service name "lb-server"
    c.agent.service.register(
        name="lb-server",
        service_id=service_id,
        address="localhost",
        port=lb_port
    )
    print(f"Registered LB server with Consul as service 'lb-server' (ID: {service_id})")

class LoadBalancerServicer(load_balancer_pb2_grpc.LoadBalancerServicer):
    def __init__(self, policy):
        self.policy = policy
        self.round_robin_index = 0

    def RegisterBackend(self, request, context):
        global backend_servers
        with backend_lock:
            exists = any(backend.id == request.id for backend in backend_servers)
            if not exists:
                print(f"Registering backend: {request.id} at {request.address}:{request.port}")
                backend_servers.append(request)
            else:
                print(f"Backend {request.id} already registered.")
        return load_balancer_pb2.RegisterResponse(success=True, message="Registered successfully.")

    def ReportLoad(self, request, context):
        global backend_servers
        updated = False
        with backend_lock:
            for i, backend in enumerate(backend_servers):
                if backend.id == request.id:
                    backend_servers[i] = load_balancer_pb2.BackendInfo(
                        id=backend.id,
                        address=backend.address,
                        port=backend.port,
                        load=request.load
                    )
                    updated = True
                    print(f"Updated load for backend {backend.id} to {request.load}")
                    break
        if not updated:
            print(f"Backend {request.id} not found for load update.")
        return load_balancer_pb2.RegisterResponse(success=updated, message="Load updated." if updated else "Backend not found.")

    def GetBackend(self, request, context):
        global backend_servers
        with backend_lock:
            if not backend_servers:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("No backend servers available.")
                return load_balancer_pb2.BackendInfo()
            # Policy-based selection:
            if self.policy == "pick_first":
                selected = backend_servers[0]
            elif self.policy == "round_robin":
                selected = backend_servers[self.round_robin_index]
                self.round_robin_index = (self.round_robin_index + 1) % len(backend_servers)
            elif self.policy == "least_load":
                # Find the minimum load value
                min_load = min(b.load for b in backend_servers)
                # Define tolerance for "equal" load (here 0.001 sec tolerance)
                tolerance = 0.001
                # Get all backends with load nearly equal to min_load
                candidates = [b for b in backend_servers if abs(b.load - min_load) < tolerance]
                if candidates:
                    selected = random.choice(candidates)
                else:
                    # If no candidate within tolerance, pick the one with min load
                    selected = min(backend_servers, key=lambda b: b.load)
            else:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("Invalid load balancing policy")
                return load_balancer_pb2.BackendInfo()
            print(f"Client '{request.client_id}' assigned to backend {selected.id} (load: {selected.load})")
            return selected

def serve(lb_port, policy, consul_host, consul_port):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    load_balancer_pb2_grpc.add_LoadBalancerServicer_to_server(LoadBalancerServicer(policy), server)
    server.add_insecure_port(f'[::]:{lb_port}')
    server.start()
    print(f"Load Balancer started on port {lb_port} with policy '{policy}'.")
    register_lb_service(lb_port, consul_host, consul_port)
    try:
        while True:
            time.sleep(86400)  # run forever
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load Balancer Server")
    parser.add_argument("--port", type=int, default=50051, help="Port for the LB server")
    parser.add_argument("--policy", type=str, choices=["pick_first", "round_robin", "least_load"], default="pick_first",
                        help="Load balancing policy")
    parser.add_argument("--consul_host", type=str, default="localhost", help="Consul host (default: localhost)")
    parser.add_argument("--consul_port", type=int, default=8500, help="Consul port (default: 8500)")
    args = parser.parse_args()
    serve(args.port, args.policy, args.consul_host, args.consul_port)
