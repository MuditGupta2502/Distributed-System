import os
import sys
import subprocess
import time
import shutil
from pathlib import Path
from multiprocessing.pool import ThreadPool
import grpc

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import mapper_service_pb2 as map_pb2
import mapper_service_pb2_grpc as map_pb2_grpc
import reducer_service_pb2 as red_pb2
import reducer_service_pb2_grpc as red_pb2_grpc

# Global list to collect intermediate directories from mappers.
intermediate_dirs = []

class MasterController:
    def __init__(self, op_type, input_dir, num_mappers, num_reducers, mapper_dict, reducer_dict, output_dir):
        self.op_type = op_type                # 1: Word Count, 2: Inverted Index
        self.input_dir = input_dir
        self.num_mappers = num_mappers
        self.num_reducers = num_reducers
        self.mapper_dict = mapper_dict
        self.reducer_dict = reducer_dict
        self.output_dir = output_dir

    def split_input_files(self):
        files = os.listdir(self.input_dir)
        print("Found input files:", files)
        total = len(files)
        distribution = {}
        per_mapper = total // self.num_mappers if self.num_mappers <= total else 1
        idx = 0
        mapper_index = 1
        while mapper_index <= self.num_mappers:
            flist = []
            fid_list = []
            for _ in range(per_mapper):
                if idx < total:
                    flist.append(files[idx])
                    fid_list.append(idx)
                    idx += 1
            if flist:
                distribution[mapper_index] = (flist, fid_list)
            mapper_index += 1
        # Distribute any remaining files round-robin.
        mapper_index = 1
        while idx < total:
            distribution[mapper_index][0].append(files[idx])
            distribution[mapper_index][1].append(idx)
            idx += 1
            mapper_index = (mapper_index % self.num_mappers) + 1
        return distribution

    def start_mappers(self):
        processes = []
        for m_name, port in self.mapper_dict.items():
            # Adjust path to locate the mapper service in the server folder.
            proc = subprocess.Popen(['python', '../server/mapper_service.py', str(port), m_name])
            print(f"Launching mapper {m_name} on port {port} (PID: {proc.pid})")
            processes.append(proc)
            time.sleep(1)
        return processes

    def start_reducers(self):
        processes = []
        for r_name, port in self.reducer_dict.items():
            proc = subprocess.Popen(['python', '../server/reducer_service.py', str(port), r_name])
            print(f"Launching reducer {r_name} on port {port} (PID: {proc.pid})")
            processes.append(proc)
            time.sleep(1)
        return processes

    def stop_processes(self, proc_list, proc_label):
        print(f"Stopping {proc_label} processes...")
        for proc in proc_list:
            proc.terminate()

    def call_mapper(self, file_assignment, mapper_item):
        # Determine the mapper index from the mapper_dict keys.
        mapper_idx = list(self.mapper_dict.keys()).index(mapper_item[0]) + 1
        # Check if this mapper has been assigned any files.
        if mapper_idx not in file_assignment:
            print(f"No files assigned to {mapper_item[0]}. Skipping mapping for this worker.")
            return
        port = mapper_item[1]
        with grpc.insecure_channel("localhost:" + str(port)) as channel:
            stub = map_pb2_grpc.MapWorkerStub(channel)
            req = map_pb2.MapReq(
                task_type=self.op_type,
                data_dir=self.input_dir,
                file_names=file_assignment[mapper_idx][0],
                file_ids=file_assignment[mapper_idx][1],
                reduce_count=self.num_reducers
            )
            response = stub.PerformMap(req)
            if response.status == map_pb2.MapResp.ResultStatus.OK:
                print(f"{mapper_item[0]} finished; intermediate data in: {response.temp_dir}")
                intermediate_dirs.append(response.temp_dir)
            else:
                print(f"{mapper_item[0]} encountered an error.")


    def call_reducer(self, inter_dirs, reducer_item):
        reducer_idx = list(self.reducer_dict.keys()).index(reducer_item[0])
        port = reducer_item[1]
        parts = []
        for idir in inter_dirs:
            # The partition file name is determined by the reducer index.
            part_file = os.path.join(idir, "part_" + str(reducer_idx))
            parts.append(part_file)
        with grpc.insecure_channel("localhost:" + str(port)) as channel:
            stub = red_pb2_grpc.ReduceWorkerStub(channel)
            req = red_pb2.ReduceReq(
                task_type=self.op_type,
                part_files=parts,
                output_dir=self.output_dir
            )
            resp = stub.PerformReduce(req)
            if resp.status == red_pb2.ReduceResp.ResultStatus.OK:
                print(f"{reducer_item[0]} completed; output available at: {resp.final_output}")
            else:
                print(f"{reducer_item[0]} failed.")

    def execute_mapping(self, assignment):
        jobs = []
        for item in self.mapper_dict.items():
            jobs.append((assignment, item))
        with ThreadPool() as pool:
            pool.starmap(self.call_mapper, jobs)

    def execute_reducing(self):
        jobs = []
        for item in self.reducer_dict.items():
            jobs.append((intermediate_dirs, item))
        with ThreadPool() as pool:
            pool.starmap(self.call_reducer, jobs)

if __name__ == "__main__":
    print("Select Operation:\n1. Word Count\n2. Inverted Index")
    op_choice = int(input("Enter operation number (1 or 2): "))
    # Adjust paths relative to the project root.
    input_directory = "../dataset"
    output_directory = "../output"
    mapper_num = int(input("Enter number of mappers: "))
    mapper_ports = input("Enter mapper ports (space separated, e.g., 5001 5002 ...): ").split()
    reducer_num = int(input("Enter number of reducers: "))
    reducer_ports = input("Enter reducer ports (space separated, e.g., 6001 6002 ...): ").split()

    # Remove previous temporary and output directories.
    if Path("temp_results").exists():
        shutil.rmtree("temp_results")
    if Path("../output").exists():
        shutil.rmtree("../output")

    # Build dictionaries mapping worker names to their ports.
    mapper_dict = {f"mapper_{i}": port for i, port in enumerate(mapper_ports, start=1)}
    reducer_dict = {f"reducer_{i}": port for i, port in enumerate(reducer_ports, start=1)}

    master_ctrl = MasterController(op_choice, input_directory, mapper_num, reducer_num, mapper_dict, reducer_dict, output_directory)
    assignment = master_ctrl.split_input_files()
    mappers_proc = master_ctrl.start_mappers()
    master_ctrl.execute_mapping(assignment)
    time.sleep(5)  # Allow mapping phase to finish
    master_ctrl.stop_processes(mappers_proc, "mapper")
    reducers_proc = master_ctrl.start_reducers()
    master_ctrl.execute_reducing()
    time.sleep(5)  # Allow reduce phase to finish
    master_ctrl.stop_processes(reducers_proc, "reducer")
