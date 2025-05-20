import time
import argparse
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
import grpc
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

def client_request(client_id, service_name, payload, consul_host, consul_port):
    try:
        lb_address = discover_lb_service(consul_host, consul_port)
        lb_channel = grpc.insecure_channel(lb_address)
        lb_stub = load_balancer_pb2_grpc.LoadBalancerStub(lb_channel)
        server_request = load_balancer_pb2.ServerRequest(client_id=client_id, service_name=service_name)
        backend_info = lb_stub.GetBackend(server_request)
        if not backend_info or backend_info.id == "":
            return None, None, None
        backend_target = f"{backend_info.address}:{backend_info.port}"
        backend_channel = grpc.insecure_channel(backend_target)
        compute_stub = load_balancer_pb2_grpc.ComputeStub(backend_channel)
        start_time = time.time()
        task_request = load_balancer_pb2.TaskRequest(payload=payload)
        response = compute_stub.ComputeTask(task_request)
        end_time = time.time()
        response_time = end_time - start_time
        return response_time, backend_info.id, response.result
    except Exception as e:
        print(f"Client {client_id} encountered error: {e}")
        return None, None, None

def scale_test(num_clients, consul_host, consul_port):
    results = []
    backend_usage = {}
    start_test = time.time()
    
    with ThreadPoolExecutor(max_workers=num_clients) as executor:
        futures = []
        for i in range(num_clients):
            client_id = f"client-{i+1}"
            futures.append(executor.submit(client_request, client_id, "compute_service", "Hello, gRPC!", consul_host, consul_port))
        
        for future in as_completed(futures):
            response_time, backend_id, result = future.result()
            if response_time is not None:
                results.append(response_time)
                backend_usage[backend_id] = backend_usage.get(backend_id, 0) + 1
    end_test = time.time()
    test_duration = end_test - start_test
    throughput = len(results) / test_duration if test_duration > 0 else 0
    return results, backend_usage, throughput

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scale Testing for gRPC Load Balancing System")
    parser.add_argument("--num_clients", type=int, default=100, help="Number of concurrent clients")
    parser.add_argument("--consul_host", type=str, default="localhost", help="Consul host")
    parser.add_argument("--consul_port", type=int, default=8500, help="Consul port")
    args = parser.parse_args()
    
    print("Starting scale test...")
    response_times, backend_usage, throughput = scale_test(args.num_clients, args.consul_host, args.consul_port)
    
    if response_times:
        avg_time = statistics.mean(response_times)
        max_time = max(response_times)
        min_time = min(response_times)
        print(f"Scale Test Results with {args.num_clients} clients:")
        print(f"Average response time: {avg_time:.3f} sec")
        print(f"Max response time: {max_time:.3f} sec")
        print(f"Min response time: {min_time:.3f} sec")
        print(f"Throughput: {throughput:.2f} requests/sec")
    else:
        print("No successful responses recorded.")

    print("Backend usage distribution:")
    for backend, count in backend_usage.items():
        print(f"Backend {backend}: {count} requests")
