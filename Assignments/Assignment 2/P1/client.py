import grpc
import argparse
import consul

import load_balancer_pb2
import load_balancer_pb2_grpc

def discover_lb_service(consul_host="localhost", consul_port=8500):
    c = consul.Consul(host=consul_host, port=consul_port)
    index, services = c.catalog.service("lb-server")
    if services:
        service = services[0]
        address = service.get("ServiceAddress") or service.get("Address")
        port = service.get("ServicePort")
        lb_endpoint = f"{address}:{port}"
        print(f"Discovered LB server at {lb_endpoint} via Consul")
        return lb_endpoint
    else:
        raise Exception("No LB server found in Consul.")

def run(client_id, service_name, payload, consul_host, consul_port):
    lb_address = discover_lb_service(consul_host, consul_port)
    lb_channel = grpc.insecure_channel(lb_address)
    lb_stub = load_balancer_pb2_grpc.LoadBalancerStub(lb_channel)
    server_request = load_balancer_pb2.ServerRequest(client_id=client_id, service_name=service_name)
    backend_info = lb_stub.GetBackend(server_request)
    if not backend_info or backend_info.id == "":
        print("No backend server available.")
        return

    backend_target = f"{backend_info.address}:{backend_info.port}"
    print(f"Client '{client_id}' (service: '{service_name}') assigned backend: {backend_info.id} at {backend_target} (load: {backend_info.load})")

    backend_channel = grpc.insecure_channel(backend_target)
    compute_stub = load_balancer_pb2_grpc.ComputeStub(backend_channel)
    task_request = load_balancer_pb2.TaskRequest(payload=payload)
    response = compute_stub.ComputeTask(task_request)
    print(f"Received result from backend: {response.result}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Client for Load Balancing System using Consul for LB discovery")
    parser.add_argument("--client_id", type=str, default="client1", help="Unique client identifier")
    parser.add_argument("--service_name", type=str, default="compute_service", help="Name of the service requested")
    parser.add_argument("--payload", type=str, default="Hello, gRPC!", help="Payload for the compute task")
    parser.add_argument("--consul_host", type=str, default="localhost", help="Consul host (default: localhost)")
    parser.add_argument("--consul_port", type=int, default=8500, help="Consul port (default: 8500)")
    args = parser.parse_args()
    run(args.client_id, args.service_name, args.payload, args.consul_host, args.consul_port)
