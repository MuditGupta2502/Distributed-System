#include <bits/stdc++.h>
#include <mpi.h>
using namespace std;

map<char, char> change_direction = {{'R', 'D'}, {'L', 'U'}, {'U', 'R'}, {'D', 'L'}};
map<char, char> reverse_direction = {{'R', 'L'}, {'L', 'R'}, {'U', 'D'}, {'D', 'U'}};

int lowerlimit;
int upperlimit;

struct Particle {
    int id, x, y;
    char direction;
    
    Particle() {}
    
    Particle(int p1, int p2, int p3, char p4) {
        id = p1;
        x = p2;
        y = p3;
        direction = p4;
    }
    
    bool operator<(const Particle& other) const {
        return id < other.id;
    }
    
    vector<int> serialize() const {  // Add const here
        return vector<int>{id, x, y, direction};
    }
    
    void move_ahead(int M, int N) {
        // Handle circular grid movement
        if (direction == 'L') {
            y = (y - 1 + N) % N;
        }
        else if (direction == 'R') {
            y = (y + 1) % N;
        }
        else if (direction == 'U') {
            x = (x - 1 + M) % M;
        }
        else if (direction == 'D') {
            x = (x + 1) % M;
        }
    }
    
    void collideTwo() {
        direction = change_direction[direction];
    }
    
    void collideFour() {
        direction = reverse_direction[direction];
    }
};



vector<Particle> list_crossed_upperlimit, list_crossed_lowerlimit;

void move_particles_ahead(map<int, Particle>& my_particles, int m, int n) {
    vector<int> crossed_particles;
    
    for (auto& itr : my_particles) {
        Particle& p = itr.second;
        int old_x = p.x;
        p.move_ahead(m, n);
        
        // Check if particle crossed process boundaries
        bool crossed = false;
        if ((old_x < p.x && p.x >= upperlimit) || 
            (old_x > p.x && p.x < lowerlimit) ||
            (old_x == m-1 && p.x == 0) ||
            (old_x == 0 && p.x == m-1)) {
            crossed = true;
        }
        
        if (crossed) {
            if ((old_x == m-1 && p.x == 0)) {
                list_crossed_upperlimit.push_back(p);
            }
            else if(old_x == 0 and p.x==m-1){
                list_crossed_lowerlimit.push_back(p);
            }
            else if(p.x>=upperlimit){
                list_crossed_upperlimit.push_back(p);
            }
            else{
                list_crossed_lowerlimit.push_back(p);
            }
            crossed_particles.push_back(itr.first);
        }
    }
    
    for (auto i : crossed_particles) {
        my_particles.erase(i);
    }
}

void handle_collisions(map<pair<int, int>, vector<int>>& positions, map<int, Particle>& my_particles) {
    for (auto& [pos, ids] : positions) {
        if (ids.size() == 2) {
            // Handle two-particle collision
            for (int id : ids) {
                my_particles[id].collideTwo();
            }
        } 
        else if (ids.size() == 4) {
            // Handle four-particle collision
            for (int id : ids) {
                my_particles[id].collideFour();
            }
        }
        // For three particles, no direction change needed
    }
}

int main(int argc, char* argv[]) {
    MPI_Init(&argc, &argv);
    int rank, size;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &size);

    /*MPI_Barrier(MPI_COMM_WORLD);
    double time_beginning = MPI_Wtime();*/

    int m, n, k, t, actual_process_size;
    int portion_length;
    
    if (rank == 0) {
        cin >> m >> n >> k >> t;
        portion_length = ceil((double)m / size);
        actual_process_size = ceil((double)m/portion_length);
    }
    MPI_Bcast(&m, 1, MPI_INT, 0, MPI_COMM_WORLD);
    MPI_Bcast(&n, 1, MPI_INT, 0, MPI_COMM_WORLD);
    MPI_Bcast(&k, 1, MPI_INT, 0, MPI_COMM_WORLD);
    MPI_Bcast(&t, 1, MPI_INT, 0, MPI_COMM_WORLD);
    MPI_Bcast(&portion_length, 1, MPI_INT, 0, MPI_COMM_WORLD);
    MPI_Bcast(&actual_process_size, 1, MPI_INT, 0, MPI_COMM_WORLD);
    
    map<int, Particle> my_particles;
    
    if (rank == 0) {
        map<int, vector<Particle>> process_particle_map;
        for (int i = 0; i < k; i++) {
            int x, y;
            char dir;
            cin >> x >> y >> dir;
            process_particle_map[x / portion_length].push_back(Particle(i, x, y, dir));
        }
        
        for (int r = 0; r < size; r++) {
            int sz = process_particle_map[r].size();
            MPI_Send(&sz, 1, MPI_INT, r, 0, MPI_COMM_WORLD);
            for (int j = 0; j < sz; j++) {
                vector<int> serialized = process_particle_map[r][j].serialize();
                MPI_Send(serialized.data(), 4, MPI_INT, r, 0, MPI_COMM_WORLD);
            }
        }
    }
    
    int received_size;
    MPI_Recv(&received_size, 1, MPI_INT, 0, 0, MPI_COMM_WORLD, MPI_STATUS_IGNORE);
    
    for (int i = 0; i < received_size; i++) {
        vector<int> temp(4);
        MPI_Recv(temp.data(), 4, MPI_INT, 0, 0, MPI_COMM_WORLD, MPI_STATUS_IGNORE);
        my_particles[temp[0]] = Particle(temp[0], temp[1], temp[2], (char)temp[3]);
    }
    
    lowerlimit = rank * portion_length;
    upperlimit = min(lowerlimit + portion_length, m); 
    
    for (int step = 0; step < t; step++) {
        list_crossed_lowerlimit.clear();
        list_crossed_upperlimit.clear();
        move_particles_ahead(my_particles, m, n);
        
        // Send particles that crossed boundaries
        int next_rank = (rank + 1) % actual_process_size;
        int prev_rank = (rank - 1 + actual_process_size) % actual_process_size;
        
        // Send to next process
        if(lowerlimit<m){
        int sz_up = list_crossed_upperlimit.size();
        MPI_Send(&sz_up, 1, MPI_INT, next_rank, 0, MPI_COMM_WORLD);
        for (auto& p : list_crossed_upperlimit) {
            vector<int> serialized = p.serialize();
            MPI_Send(serialized.data(), 4, MPI_INT, next_rank, 0, MPI_COMM_WORLD);
        }
        
        // Send to previous process
        int sz_low = list_crossed_lowerlimit.size();
        MPI_Send(&sz_low, 1, MPI_INT, prev_rank, 0, MPI_COMM_WORLD);
        for (auto& p : list_crossed_lowerlimit) {
            vector<int> serialized = p.serialize();
            MPI_Send(serialized.data(), 4, MPI_INT, prev_rank, 0, MPI_COMM_WORLD);
        }
        
        // Receive from next process
        int recv_size;
        MPI_Recv(&recv_size, 1, MPI_INT, next_rank, 0, MPI_COMM_WORLD, MPI_STATUS_IGNORE);
        for (int i = 0; i < recv_size; i++) {
            vector<int> temp(4);
            MPI_Recv(temp.data(), 4, MPI_INT, next_rank, 0, MPI_COMM_WORLD, MPI_STATUS_IGNORE);
            my_particles[temp[0]] = Particle(temp[0], temp[1], temp[2], (char)temp[3]);
        }
        
        // Receive from previous process
        MPI_Recv(&recv_size, 1, MPI_INT, prev_rank, 0, MPI_COMM_WORLD, MPI_STATUS_IGNORE);
        for (int i = 0; i < recv_size; i++) {
            vector<int> temp(4);
            MPI_Recv(temp.data(), 4, MPI_INT, prev_rank, 0, MPI_COMM_WORLD, MPI_STATUS_IGNORE);
            my_particles[temp[0]] = Particle(temp[0], temp[1], temp[2], (char)temp[3]);
        }
        }
        // Synchronize all processes before handling collisions
        MPI_Barrier(MPI_COMM_WORLD);
        
        // Handle collisions
        map<pair<int, int>, vector<int>> positions;
        for (auto& [id, particle] : my_particles) {
            positions[{particle.x, particle.y}].push_back(id);
        }
        
        handle_collisions(positions, my_particles);

    }
    
    // Gather final results
    int local_size = my_particles.size();
    MPI_Send(&local_size, 1, MPI_INT, 0, 0, MPI_COMM_WORLD);
    for (const auto& [id, particle] : my_particles) {
        vector<int> serialized = particle.serialize();
        MPI_Send(serialized.data(), 4, MPI_INT, 0, 0, MPI_COMM_WORLD);
    }
    
    if (rank == 0) {
        vector<Particle> all_particles;
        for (int r = 0; r < size; r++) {
            int sz;
            MPI_Recv(&sz, 1, MPI_INT, r, 0, MPI_COMM_WORLD, MPI_STATUS_IGNORE);
            for (int i = 0; i < sz; i++) {
                vector<int> temp(4);
                MPI_Recv(temp.data(), 4, MPI_INT, r, 0, MPI_COMM_WORLD, MPI_STATUS_IGNORE);
                all_particles.push_back(Particle(temp[0], temp[1], temp[2], (char)temp[3]));
            }
        }
        
        sort(all_particles.begin(), all_particles.end());
        
        for (const auto& particle : all_particles) {
            cout << particle.x << " " << particle.y << " " << particle.direction << "\n";
        }
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