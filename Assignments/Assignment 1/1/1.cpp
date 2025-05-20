#include <mpi.h>
#include <vector>
#include <iostream>
#include <climits>
#include <set>

using namespace std;

void parallel_bfs(int rank, int size, const vector<vector<pair<int, int>>>& graph, int exit_node, int V, vector<int>& distances, const set<int>& blocked);

int main(int argc, char** argv) {
    MPI_Init(&argc, &argv);

    int rank, size;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &size);

    /*MPI_Barrier(MPI_COMM_WORLD);
    double time_beginning = MPI_Wtime();*/

    int V, E;
    vector<vector<pair<int, int>>> graph;
    vector<int> start_nodes;
    int exit_node;
    set<int> blocked;

    if (rank == 0) {
        cin >> V >> E;
        graph.resize(V);

        for (int i = 0; i < E; ++i) {
            int u, v, d;
            cin >> u >> v >> d;
            graph[v].emplace_back(u, d);
            if (d == 1) graph[u].emplace_back(v, d);  // Add reverse edge for undirected
        }

        int k;
        cin >> k;
        start_nodes.resize(k);
        for (int i = 0; i < k; ++i) {
            cin >> start_nodes[i];
        }

        cin >> exit_node;

        int b;
        cin >> b;  
        for (int i = 0; i < b; ++i) {
            int blocked_node;
            cin >> blocked_node;
            blocked.insert(blocked_node);
        }

       
        for (int node : start_nodes) {
            blocked.erase(node);
        }
    }

    MPI_Bcast(&V, 1, MPI_INT, 0, MPI_COMM_WORLD);
    MPI_Bcast(&exit_node, 1, MPI_INT, 0, MPI_COMM_WORLD);

    vector<int> flat_graph;
    if (rank == 0) {
        for (const auto& neighbors : graph) {
            flat_graph.push_back(neighbors.size());
            for (const auto& [v, d] : neighbors) {
                flat_graph.push_back(v);
                flat_graph.push_back(d);
            }
        }
    }

    int flat_size = flat_graph.size();
    MPI_Bcast(&flat_size, 1, MPI_INT, 0, MPI_COMM_WORLD);
    if (rank != 0) {
        flat_graph.resize(flat_size);
    }
    MPI_Bcast(flat_graph.data(), flat_size, MPI_INT, 0, MPI_COMM_WORLD);

    if (rank != 0) {
        graph.resize(V);
        int idx = 0;
        for (int i = 0; i < V; ++i) {
            int num_neighbors = flat_graph[idx++];
            for (int j = 0; j < num_neighbors; ++j) {
                int v = flat_graph[idx++];
                int d = flat_graph[idx++];
                graph[i].emplace_back(v, d);
            }
        }
    }

    int k = start_nodes.size();
    MPI_Bcast(&k, 1, MPI_INT, 0, MPI_COMM_WORLD);
    if (rank != 0) {
        start_nodes.resize(k);
    }
    MPI_Bcast(start_nodes.data(), k, MPI_INT, 0, MPI_COMM_WORLD);

    vector<int> blocked_list(blocked.begin(), blocked.end());
    int blocked_size = blocked_list.size();
    MPI_Bcast(&blocked_size, 1, MPI_INT, 0, MPI_COMM_WORLD);
    if (rank != 0) {
        blocked_list.resize(blocked_size);
    }
    MPI_Bcast(blocked_list.data(), blocked_size, MPI_INT, 0, MPI_COMM_WORLD);

    set<int> global_blocked(blocked_list.begin(), blocked_list.end());

    vector<int> distances(V, INT_MAX);
    parallel_bfs(rank, size, graph, exit_node, V, distances, global_blocked);

    if (rank == 0) {
        for (int start_node : start_nodes) {
            int result = distances[start_node];
            if (result == INT_MAX) result = -1;
            cout << result << " ";
        }
        cout << endl;
    }
    
    /*MPI_Barrier(MPI_COMM_WORLD);
    double elapsedTime = MPI_Wtime() - time_beginning;
    double maxTime;
    MPI_Reduce(&elapsedTime, &maxTime, 1, MPI_DOUBLE, MPI_MAX, 0, MPI_COMM_WORLD);
    if (rank == 0) {
        printf("Total time (s): %f\n", maxTime);
    }*/

    MPI_Finalize();
    return 0;
}

void parallel_bfs(int rank, int size, const vector<vector<pair<int, int>>>& graph, int exit_node, int V, vector<int>& distances, const set<int>& blocked) {
    int local_start, local_end;
    if (rank >= V) {
        local_start = 0;
        local_end = 0;
    } else {
        int basic_size = V / size;
        int remainder = V % size;

        if (rank < remainder) {
            local_start = rank * (basic_size + 1);
            local_end = local_start + basic_size + 1;
        } else {
            local_start = rank * basic_size + remainder;
            local_end = local_start + basic_size;
        }
    }

    vector<int> local_distances(V, INT_MAX);
    if ((exit_node >= local_start && exit_node < local_end)){
        local_distances[exit_node] = 0;
    }

    bool global_active = true;
    while (global_active) {
        vector<int> next_level_distances(local_distances);  // Start with the current distances
        bool local_active = false;

        for (int u = local_start; u < local_end; ++u) {
            if (local_distances[u] == INT_MAX || blocked.count(u)) continue;  // Skip if distance is INT_MAX or node is blocked

            for (const auto& [v, d] : graph[u]) {
                if (blocked.count(v)) continue;  

                if (d == 0) {  
                    if (local_distances[u] != INT_MAX && local_distances[u] + 1 < next_level_distances[v]) {
                        next_level_distances[v] = local_distances[u] + 1;
                        local_active = true;
                    }
                } else if (d == 1) {  
                    if (local_distances[u] != INT_MAX && local_distances[u] + 1 < next_level_distances[v]) {
                        next_level_distances[v] = local_distances[u] + 1;
                        local_active = true;
                    }
                    if (local_distances[v] != INT_MAX && local_distances[v] + 1 < next_level_distances[u]) {
                        next_level_distances[u] = local_distances[v] + 1;
                        local_active = true;
                    }
                }
            }
        }

        MPI_Allreduce(next_level_distances.data(), local_distances.data(), V, MPI_INT, MPI_MIN, MPI_COMM_WORLD);

        MPI_Allreduce(&local_active, &global_active, 1, MPI_C_BOOL, MPI_LOR, MPI_COMM_WORLD);
    }

    distances = local_distances;
}
