import grpc
from concurrent import futures
import time
import threading
import argparse
import random
import consul

import load_balancer_pb2
import load_balancer_pb2_grpc

current_load = 0.0

def discover_lb_service(consul_host="localhost", consul_port=8500):
    c = consul.Consul(host=consul_host, port=consul_port)
    index, services = c.catalog.service("lb-server")
    if services:
        # Choose the first LB server found
        service = services[0]
        address = service.get("ServiceAddress") or service.get("Address")
        port = service.get("ServicePort")
        print(f"Discovered LB server at {address}:{port} via Consul")
        return f"{address}:{port}"
    else:
        raise Exception("No LB server found in Consul.")

class ComputeServicer(load_balancer_pb2_grpc.ComputeServicer):
    def ComputeTask(self, request, context):
        global current_load
        processing_time = random.uniform(0.5, 2.0)
        print(f"Processing task with payload: {request.payload}. Estimated time: {processing_time:.2f} sec")
        time.sleep(processing_time)
        result = request.payload[::-1]
        current_load = processing_time
        return load_balancer_pb2.TaskResponse(result=result)

def report_load_periodically(lb_address, backend_id, interval):
    while True:
        global current_load
        try:
            channel = grpc.insecure_channel(lb_address)
            stub = load_balancer_pb2_grpc.LoadBalancerStub(channel)
            report = load_balancer_pb2.LoadReport(id=backend_id, load=current_load)
            response = stub.ReportLoad(report)
            print(f"Reported load {current_load} for backend {backend_id}. LB Response: {response.message}")
        except Exception as e:
            print(f"Error reporting load: {e}")
        time.sleep(interval)

def serve(backend_id, backend_port, consul_host, consul_port, report_interval):
    lb_address = discover_lb_service(consul_host, consul_port)
    # Register with LB server
    channel = grpc.insecure_channel(lb_address)
    lb_stub = load_balancer_pb2_grpc.LoadBalancerStub(channel)
    backend_info = load_balancer_pb2.BackendInfo(id=backend_id, address="localhost", port=backend_port, load=0.0)
    reg_response = lb_stub.RegisterBackend(backend_info)
    print(f"Registration with LB: {reg_response.message}")

    reporter_thread = threading.Thread(target=report_load_periodically, args=(lb_address, backend_id, report_interval), daemon=True)
    reporter_thread.start()

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    load_balancer_pb2_grpc.add_ComputeServicer_to_server(ComputeServicer(), server)
    server.add_insecure_port(f'[::]:{backend_port}')
    server.start()
    print(f"Backend server '{backend_id}' started on port {backend_port}.")
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backend Server")
    parser.add_argument("--id", type=str, required=True, help="Unique ID for the backend server")
    parser.add_argument("--port", type=int, required=True, help="Port for the backend server")
    parser.add_argument("--consul_host", type=str, default="localhost", help="Consul host (default: localhost)")
    parser.add_argument("--consul_port", type=int, default=8500, help="Consul port (default: 8500)")
    parser.add_argument("--report_interval", type=int, default=5, help="Interval (in seconds) for reporting load")
    args = parser.parse_args()
    serve(args.id, args.port, args.consul_host, args.consul_port, args.report_interval)
