from concurrent.futures import ThreadPoolExecutor
import grpc
import sys
import os
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import mapper_service_pb2 as map_pb2
import mapper_service_pb2_grpc as map_pb2_grpc

class MapWorkerServicer(map_pb2_grpc.MapWorkerServicer):
    def __init__(self, worker_id):
        self.worker_id = worker_id
        # Intermediate results will be stored under "temp_results/worker_<id>"
        self.base_dir = os.path.join("temp_results", "worker_" + self.worker_id)
        Path(self.base_dir).mkdir(parents=True, exist_ok=True)
        self.reduce_count = 0
        self.task_type = 0

    def write_line(self, filename, text):
        with open(filename, "a") as fout:
            fout.write(text + "\n")

    def compute_partition(self, word):
        # A simple partitioning: hash based on word length modulo number of reducers.
        return str(len(word) % self.reduce_count)

    def process_word_count(self, file_path):
        with open(file_path, "r") as fin:
            for line in fin:
                for token in line.strip().split():
                    part = self.compute_partition(token)
                    out_file = os.path.join(self.base_dir, "part_" + part)
                    self.write_line(out_file, token.lower() + " 1")

    def process_inverted_index(self, file_id, file_path):
        with open(file_path, "r") as fin:
            for line in fin:
                for token in line.strip().split():
                    part = self.compute_partition(token)
                    out_file = os.path.join(self.base_dir, "part_" + part)
                    self.write_line(out_file, token.lower() + " " + str(file_id))

    def PerformMap(self, request, context):
        self.reduce_count = request.reduce_count
        self.task_type = request.task_type

        if self.task_type == 1:
            # Word Count mapping.
            for fname in request.file_names:
                full_path = os.path.join(request.data_dir, fname)
                self.process_word_count(full_path)
        elif self.task_type == 2:
            # Inverted Index mapping.
            for idx, fname in enumerate(request.file_names):
                full_path = os.path.join(request.data_dir, fname)
                self.process_inverted_index(request.file_ids[idx], full_path)

        return map_pb2.MapResp(temp_dir=self.base_dir, status=map_pb2.MapResp.ResultStatus.OK)

class MapWorker:
    def __init__(self, port, worker_id):
        self.port = port
        self.worker_id = worker_id

    def start_service(self):
        server = grpc.server(ThreadPoolExecutor(max_workers=10))
        map_pb2_grpc.add_MapWorkerServicer_to_server(MapWorkerServicer(self.worker_id), server)
        server.add_insecure_port("[::]:" + self.port)
        print(f"Map Worker {self.worker_id} running on port {self.port}")
        server.start()
        server.wait_for_termination()

if __name__ == "__main__":
    port_arg = sys.argv[1]
    worker_name = sys.argv[2]
    worker = MapWorker(port_arg, worker_name)
    worker.start_service()
