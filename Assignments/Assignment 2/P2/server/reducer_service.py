from concurrent.futures import ThreadPoolExecutor
import grpc
import sys
import os
from pathlib import Path
import itertools

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import reducer_service_pb2 as red_pb2
import reducer_service_pb2_grpc as red_pb2_grpc

class ReduceWorkerServicer(red_pb2_grpc.ReduceWorkerServicer):
    def __init__(self, worker_id):
        self.worker_id = worker_id
        self.result_data = {}
        self.out_dir = ""

    def append_line(self, file_path, content):
        with open(file_path, "a") as fout:
            fout.write(content + "\n")

    def reduce_word_count(self, key, counts):
        total = sum(counts)
        out_file = os.path.join(self.out_dir, self.worker_id)
        self.append_line(out_file, key + " " + str(total))
        return out_file

    def reduce_inverted_index(self, key, file_ids):
        unique_ids = sorted(set(file_ids))
        out_file = os.path.join(self.out_dir, self.worker_id)
        self.append_line(out_file, key + " " + ", ".join(unique_ids))
        return out_file

    def perform_reduce(self, part_files, task_type):
        self.result_data = {}
        for pf in part_files:
            if os.path.exists(pf):
                with open(pf, "r") as fin:
                    for line in fin:
                        parts = line.strip().split()
                        if not parts:
                            continue
                        k = parts[0]
                        val = parts[1]
                        if task_type == 1:
                            val = int(val)
                        self.result_data.setdefault(k, []).append(val)
        final_out = ""
        if task_type == 1:
            for k, counts in self.result_data.items():
                final_out = self.reduce_word_count(k, counts)
        elif task_type == 2:
            for k, ids in self.result_data.items():
                final_out = self.reduce_inverted_index(k, ids)
        return final_out

    def PerformReduce(self, request, context):
        self.out_dir = request.output_dir
        Path(self.out_dir).mkdir(parents=True, exist_ok=True)
        final_output_path = self.perform_reduce(request.part_files, request.task_type)
        return red_pb2.ReduceResp(status=red_pb2.ReduceResp.ResultStatus.OK, final_output=final_output_path)

class ReduceWorker:
    def __init__(self, port, worker_id):
        self.port = port
        self.worker_id = worker_id

    def start_service(self):
        server = grpc.server(ThreadPoolExecutor(max_workers=10))
        red_pb2_grpc.add_ReduceWorkerServicer_to_server(ReduceWorkerServicer(self.worker_id), server)
        server.add_insecure_port("[::]:" + self.port)
        print(f"Reduce Worker {self.worker_id} running on port {self.port}")
        server.start()
        server.wait_for_termination()

if __name__ == "__main__":
    port_arg = sys.argv[1]
    worker_name = sys.argv[2]
    worker = ReduceWorker(port_arg, worker_name)
    worker.start_service()
