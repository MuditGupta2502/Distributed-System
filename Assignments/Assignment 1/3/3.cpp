#include <mpi.h>
#include <iostream>
#include <vector>
#include <string>
#include <map>
#include <set>
#include <fstream>
#include <sstream>
#include <thread>
#include <chrono>
#include <mutex>
#include <atomic>
#include <algorithm>
#include <cstdlib>
#include <ctime>
#include <cstring>
#include <cctype>
#include <sstream>

const int CHUNK_SIZE = 32;
const int REPLICATION_FACTOR = 3;
const int HEARTBEAT_INTERVAL = 1;
const int FAILOVER_THRESHOLD = 5;

struct ChunkInfo {
    std::vector<int> locations;
    std::string data;
};

struct FileMetadata {
    std::string filename;
    std::vector<ChunkInfo> chunks;
};

struct SearchResult {
    std::vector<size_t> offsets;
};

// METADATA SERVER GLOBALS
std::map<std::string, FileMetadata> files;
std::map<int, std::chrono::system_clock::time_point> lastHeartbeats;
std::set<int> activeNodes;
std::mutex metadataMutex;
std::atomic<bool> running{true};

// STORAGE NODE GLOBALS
std::map<std::pair<std::string, int>, std::string> localChunks;
std::mutex localChunksMutex;
std::atomic<bool> nodeActive{true};

// Storage node thread: sends heartbeat to rank 0 every HEARTBEAT_INTERVAL (=1) seconds.
void heartbeatThread(int rank) {
    while (running) {
        if (nodeActive) {
            MPI_Send(&rank, 1, MPI_INT, 0, 0, MPI_COMM_WORLD);
        }
        std::this_thread::sleep_for(std::chrono::seconds(HEARTBEAT_INTERVAL));
    }
}

// Rank 0 thread: checks for lost heartbeats every second.
void checkHeartbeatsThread() {
    while (running) {
        std::this_thread::sleep_for(std::chrono::seconds(1));
        auto now = std::chrono::system_clock::now();

        std::lock_guard<std::mutex> lock(metadataMutex);
        for (auto it = lastHeartbeats.begin(); it != lastHeartbeats.end();) {
            auto diff = std::chrono::duration_cast<std::chrono::seconds>(now - it->second).count();
            if (diff >= FAILOVER_THRESHOLD) {
                activeNodes.erase(it->first);
                it = lastHeartbeats.erase(it);
            } else {
                ++it;
            }
        }
    }
}

std::vector<int> selectNodesRoundRobin(size_t chunkIndex, int replicationFactor, const std::set<int>& activeSet) {
    std::vector<int> sortedNodes(activeSet.begin(), activeSet.end());
    std::vector<int> chosen;
    chosen.reserve(replicationFactor);

    int size = (int)sortedNodes.size();
    int start = (int)(chunkIndex) % size;

    for (int i = 0; i < replicationFactor; i++) {
        int idx = (start + i) % size;
        chosen.push_back(sortedNodes[idx]);
    }
    return chosen;
}

/**
 * Return offsets of exact word matches for `word` in `chunk`,
 * offset by `chunkOffset`. A "word match" here means:
 *   - The substring is exactly `word`.
 *   - The char before and after is either start/end of chunk
 *     or a non-alphanumeric boundary.
 */
std::vector<size_t> findWordAsToken(
    const std::string &chunk,
    const std::string &word,
    size_t chunkOffset)
{
    std::vector<size_t> offsets;
    size_t pos = 0; // current scanning position

    while (pos < chunk.size()) {
        // skip leading spaces
        while (pos < chunk.size() && chunk[pos] == ' ') {
            pos++;
        }
        if (pos >= chunk.size()) break; // no more tokens

        // start of token
        size_t start = pos;
        // read until next space or chunk end
        while (pos < chunk.size() && chunk[pos] != ' ') {
            pos++;
        }
        // end of token is 'pos'
        size_t end = pos; 
        // token is chunk[start..end-1]
        std::string token = chunk.substr(start, end - start);

        // compare token with the search word
        if (token == word) {
            // record the offset (start + chunkOffset)
            offsets.push_back(chunkOffset + start);
        }
        // loop continues, pos is at a space or chunk end
    }

    return offsets;
}


bool uploadFile(const std::string& filename, const std::string& filepath, int rank)
{
    if (rank == 0)
    {
        // ===== METADATA SERVER (rank 0) =====

        std::lock_guard<std::mutex> lock(metadataMutex);

        // 1) Check if file already in DFS
        if (files.find(filename) != files.end()) {
            std::cout << "-1" << std::endl;
            int sentinel = -1;
            for (int node : activeNodes) {
            MPI_Send(&sentinel, 1, MPI_INT, node, 1, MPI_COMM_WORLD);
            }
            return false;
        }

        // 2) At least 1 active node?
        if (activeNodes.empty()) {
            std::cout << "-1" << std::endl;
            int sentinel = -1;
            for (int node : activeNodes) {
            MPI_Send(&sentinel, 1, MPI_INT, node, 1, MPI_COMM_WORLD);
            }
            return false;
        }

        // 3) Open local file
        std::ifstream fin(filepath, std::ios::binary);
        if (!fin) {
            std::cout << "-1" << std::endl;
            int sentinel = -1;
            for (int node : activeNodes) {
            MPI_Send(&sentinel, 1, MPI_INT, node, 1, MPI_COMM_WORLD);
            }
            return false;
        }

        // 4) Read entire file
        std::string content((std::istreambuf_iterator<char>(fin)),
                             std::istreambuf_iterator<char>());
        fin.close();

        FileMetadata metadata;
        metadata.filename = filename;

        // 5) Partition the file -> 32‐byte chunks
        std::vector<std::string> chunksData;
        for (size_t i = 0; i < content.size(); i += CHUNK_SIZE) {
            chunksData.push_back(content.substr(i, CHUNK_SIZE));
        }

        // 6) Decide how many replicas we can actually make
        int possibleFactor = (int)activeNodes.size();
        int actualFactor = (possibleFactor >= 3) ? 3 :
                           (possibleFactor == 2) ? 2 : 1;

        // Convert activeNodes to a sorted vector
        std::vector<int> activeVec(activeNodes.begin(), activeNodes.end());

        // node -> (chunkId, data)
        std::map<int, std::vector<std::pair<int,std::string>>> nodeToChunks;

        // 7) Round‐robin assignment, up to 'actualFactor' for each chunk
        for (size_t chunkId=0; chunkId < chunksData.size(); ++chunkId) {
            int offset = (int)(chunkId % activeVec.size());
            std::vector<int> chosen;
            chosen.reserve(actualFactor);

            for (int r = 0; r < actualFactor; r++) {
                int idx = (offset + r) % (int)activeVec.size();
                chosen.push_back(activeVec[idx]);
            }

            // Save chunk info in metadata
            ChunkInfo ci;
            ci.data = chunksData[chunkId];
            ci.locations = chosen;
            metadata.chunks.push_back(ci);

            // Also queue them for sending
            for (int nd : chosen) {
                nodeToChunks[nd].push_back({(int)chunkId, chunksData[chunkId]});
            }
        }

        // 8) Store final metadata
        files[filename] = metadata;

        // --- KEY FIX: Send 0 for nodes that have no chunks ---
        // Build a set of nodes that got some chunks
        std::set<int> usedNodes;
        for (auto &kv : nodeToChunks) {
            usedNodes.insert(kv.first);
        }

        // For each active node, if not in usedNodes, send 0
        for (int nd : activeVec) {
            if (usedNodes.find(nd) == usedNodes.end()) {
                int zero = 0;
                MPI_Send(&zero, 1, MPI_INT, nd, 1, MPI_COMM_WORLD);
            }
        }

        // Now actually send chunk data for usedNodes
        for (auto &kv : nodeToChunks) {
            int nodeRank = kv.first;
            auto &assignments = kv.second;
            int count = (int)assignments.size();
            MPI_Send(&count, 1, MPI_INT, nodeRank, 1, MPI_COMM_WORLD);

            for (auto &p : assignments) {
                int cid = p.first;
                std::string &data = p.second;
                MPI_Send(&cid, 1, MPI_INT, nodeRank, 1, MPI_COMM_WORLD);
                MPI_Send(data.c_str(), data.size(), MPI_CHAR, nodeRank, 1, MPI_COMM_WORLD);
            }
        }

        // 9) Print success + chunk distribution
        std::cout << "1" << std::endl;
        for (size_t i = 0; i < metadata.chunks.size(); i++) {
            auto &ch = metadata.chunks[i];
            std::cout << i << " " << ch.locations.size();
            for (int loc : ch.locations) {
                std::cout << " " << loc;
            }
            std::cout << std::endl;
        }

        // 10) Final barrier
        //MPI_Barrier(MPI_COMM_WORLD);
        return true;
    }
    else
    {
        // =========== STORAGE NODE (rank != 0) ==========
        MPI_Status status;

        // 1) receive how many chunks
        int totalChunks = 0;
        MPI_Recv(&totalChunks, 1, MPI_INT, 0, 1, MPI_COMM_WORLD, &status);

        // if totalChunks == 0 => no chunks for this node => just do barrier & done
        if (totalChunks < 0) {
            return false; // or return true, either is fine
        }

        // otherwise, read 'totalChunks' chunks
        for (int i=0; i<totalChunks; i++) {
            int cid;
            MPI_Recv(&cid, 1, MPI_INT, 0, 1, MPI_COMM_WORLD, &status);

            MPI_Probe(0,1,MPI_COMM_WORLD,&status);
            int csz=0;
            MPI_Get_count(&status, MPI_CHAR, &csz);
            std::vector<char> buf(csz);
            MPI_Recv(buf.data(), csz, MPI_CHAR, 0, 1, MPI_COMM_WORLD, &status);

            std::string chunkData(buf.begin(), buf.end());
            {
                std::lock_guard<std::mutex> lk(localChunksMutex);
                localChunks[{filename, cid}] = chunkData;
            }
        }

        // final barrier
        //MPI_Barrier(MPI_COMM_WORLD);
        return true;
    }
}



bool retrieveFile(const std::string& filename, int rank) {
    if (rank == 0) {
        // METADATA SERVER (rank 0)
        std::lock_guard<std::mutex> lock(metadataMutex);

        // 1) Check if file is known
        if (files.find(filename) == files.end()) {
            std::cout << "-1" << std::endl;

            int sentinel = -1;
            for (int node : activeNodes) {
            MPI_Send(&sentinel, 1, MPI_INT, node, 2, MPI_COMM_WORLD);
            }

            return false;
        }

        auto& metadata = files[filename];
        std::string content;

        // 2) For each chunk, pick one active node & request the chunk
        for (size_t i = 0; i < metadata.chunks.size(); i++) {
            bool gotChunk = false;

            for (int node : metadata.chunks[i].locations) {
                if (activeNodes.count(node) > 0) {
                    // Request chunk i from this active node
                    MPI_Send(&i, 1, MPI_INT, node, 2, MPI_COMM_WORLD);

                    // Receive chunk size
                    int chunkSize;
                    MPI_Recv(&chunkSize, 1, MPI_INT, node, 2, MPI_COMM_WORLD, MPI_STATUS_IGNORE);

                    // Receive chunk data
                    std::vector<char> buffer(chunkSize);
                    MPI_Recv(buffer.data(), chunkSize, MPI_CHAR, node, 2, MPI_COMM_WORLD, MPI_STATUS_IGNORE);

                    // Append data to 'content'
                    content += std::string(buffer.begin(), buffer.end());
                    gotChunk = true;
                    break; // done with this chunk
                }
            }

            if (!gotChunk) {
                // No active node had chunk => fail
                std::cout << "-1" << std::endl;

                // Send a sentinel to *all* active nodes so they break out of their loops
                // because we’re aborting early
                int sentinel = -1;
                for (int node : activeNodes) {
                    MPI_Send(&sentinel, 1, MPI_INT, node, 2, MPI_COMM_WORLD);
                }
                return false;
            }
        }

        // 3) We have all chunks => print the file’s content
        std::cout << content << std::endl;

        // 4) Now send sentinel to *all* active nodes to let them break out
        int sentinel = -1;
        for (int node : activeNodes) {
            MPI_Send(&sentinel, 1, MPI_INT, node, 2, MPI_COMM_WORLD);
        }

        return true;
    } 
    else {
        // =========== STORAGE NODE (rank != 0) ===========

        // Keep receiving chunk requests or a sentinel
        while (running && nodeActive) {
            MPI_Status status;
            int chunkId;

            // Wait for rank 0 to send either a chunk request or sentinel
            MPI_Recv(&chunkId, 1, MPI_INT, 0, 2, MPI_COMM_WORLD, &status);

            // If we got a sentinel => break out
            if (chunkId < 0) {
                break;
            }

            // Otherwise, respond with the requested chunk
            {
                std::lock_guard<std::mutex> lock(localChunksMutex);
                std::string chunk = localChunks[{filename, chunkId}];
                int chunkSize = (int)chunk.size();

                MPI_Send(&chunkSize, 1, MPI_INT, 0, 2, MPI_COMM_WORLD);
                MPI_Send(chunk.c_str(), chunkSize, MPI_CHAR, 0, 2, MPI_COMM_WORLD);
            }
        }
    }
    return true;
}

bool searchFile(const std::string& filename, const std::string& word, int rank, int size)
{
    if (rank == 0) {
        // ==== METADATA SERVER ====
        std::lock_guard<std::mutex> lock(metadataMutex);

        // 1) Check if file exists
        if (files.find(filename) == files.end()) {
            std::cout << "-1" << std::endl;

            int sentinel = -1;
            for (int node : activeNodes) {
            MPI_Send(&sentinel, 2, MPI_INT, node, 3, MPI_COMM_WORLD);
            }

            return false;
        }

        auto &metadata = files[filename];
        std::vector<size_t> allOffsets;

        // 2) For each chunk, find an active node to search
        for (size_t i = 0; i < metadata.chunks.size(); i++) {
            bool foundActiveReplica = false;

            // chunk i might have multiple replicas
            for (int node : metadata.chunks[i].locations) {
                if (activeNodes.count(node) > 0) {
                    // a) Send (chunkId, wordLength)
                    int searchData[2] = {(int)i, (int)word.size()};
                    MPI_Send(searchData, 2, MPI_INT, node, 3, MPI_COMM_WORLD);

                    // b) Send the actual word
                    MPI_Send(word.c_str(), word.size(), MPI_CHAR, node, 3, MPI_COMM_WORLD);

                    // c) Receive how many offsets
                    int numOffsets = 0;
                    MPI_Recv(&numOffsets, 1, MPI_INT, node, 3, MPI_COMM_WORLD, MPI_STATUS_IGNORE);

                    if (numOffsets > 0) {
                        std::vector<size_t> chunkOffsets(numOffsets);
                        MPI_Recv(chunkOffsets.data(), numOffsets, MPI_UNSIGNED_LONG, node, 3,
                                 MPI_COMM_WORLD, MPI_STATUS_IGNORE);
                        allOffsets.insert(allOffsets.end(), chunkOffsets.begin(), chunkOffsets.end());
                    }
                    foundActiveReplica = true;
                    break; // done for chunk i
                }
            }

            // If we never found an active node => fail
            if (!foundActiveReplica) {
                std::cout << "-1" << std::endl;

                // send sentinel to *all* active nodes
                int sentinel[2] = {-1, 0};
                for (int activeNode : activeNodes) {
                    MPI_Send(sentinel, 2, MPI_INT, activeNode, 3, MPI_COMM_WORLD);
                }
                return false;
            }
        }

        // 3) Sort & print offsets
        std::sort(allOffsets.begin(), allOffsets.end());
        std::cout << allOffsets.size() << std::endl;
        if (!allOffsets.empty()) {
            for (size_t i = 0; i < allOffsets.size(); i++) {
                std::cout << allOffsets[i];
                if (i + 1 < allOffsets.size()) std::cout << " ";
            }
                std::cout << "\n";
        } 
        // 4) Done => send sentinel to all active nodes
        int sentinel[2] = {-1, 0};
        for (int activeNode : activeNodes) {
            MPI_Send(sentinel, 2, MPI_INT, activeNode, 3, MPI_COMM_WORLD);
        }

        return true;
    }
    else {
        // ==== STORAGE NODE ====
        while (running && nodeActive) {
            MPI_Status status;
            int searchData[2];

            // wait for (chunkId, wordLen) or sentinel
            MPI_Recv(searchData, 2, MPI_INT, 0, 3, MPI_COMM_WORLD, &status);

            int chunkId = searchData[0];
            int wordLen = searchData[1];

            // if sentinel => break
            if (chunkId < 0) {
                break;
            }

            // next recv the actual word
            std::vector<char> buf(wordLen);
            MPI_Recv(buf.data(), wordLen, MPI_CHAR, 0, 3, MPI_COMM_WORLD, &status);
            std::string searchWord(buf.begin(), buf.end());

            // look up chunk data
            std::string chunkData;
            {
                std::lock_guard<std::mutex> lock(localChunksMutex);
                chunkData = localChunks[{filename, chunkId}];
            }

            // *** Token-based matching ***
            auto offsets = findWordAsToken(
                chunkData, 
                searchWord, 
                chunkId * CHUNK_SIZE
            );

            // send results
            int numOffsets = (int)offsets.size();
            MPI_Send(&numOffsets, 1, MPI_INT, 0, 3, MPI_COMM_WORLD);
            if (numOffsets > 0) {
                MPI_Send(offsets.data(), numOffsets, MPI_UNSIGNED_LONG, 0, 3, MPI_COMM_WORLD);
            }
        }
    }
    return true;
}


void listFile(const std::string& filename, int rank) {
    if (rank == 0) {
        std::lock_guard<std::mutex> lock(metadataMutex);
        if (files.find(filename) == files.end()) {
            std::cout << "-1" << std::endl;
            return;
        }

        auto& metadata = files[filename];
        for (size_t i = 0; i < metadata.chunks.size(); i++) {
            auto& c = metadata.chunks[i];
            std::vector<int> activeLocs;
            for (int loc : c.locations) {
                if (activeNodes.count(loc) > 0) {
                    activeLocs.push_back(loc);
                }
            }
            std::cout << i << " " << activeLocs.size();
            for (auto loc : activeLocs) {
                std::cout << " " << loc;
            }
            std::cout << std::endl;
        }
    }
}

void failover(int targetRank, int rank) {
    if (rank == targetRank) {
        nodeActive = false;
    }
    if (rank == 0) {
        std::lock_guard<std::mutex> lock(metadataMutex);
        activeNodes.erase(targetRank);
        std::cout << "1" << std::endl;
    }
}

void recover(int targetRank, int rank) {
    if (rank == targetRank) {
        nodeActive = true;
    }
    if (rank == 0) {
        std::lock_guard<std::mutex> lock(metadataMutex);
        activeNodes.insert(targetRank);
        std::cout << "1" << std::endl;
    }
}

int main(int argc, char **argv)
{
    MPI_Init(&argc, &argv);
    int rank, size;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &size);

    if (size<4) {
        if (rank==0) std::cout<<"-1"<<std::endl;
        MPI_Finalize();
        return 0;
    }

    // rank 0: mark all storage as active
    if (rank==0) {
        for (int i=1; i<size; i++) {
            activeNodes.insert(i);
        }
    }

    std::thread heartbeat, checkHeartbeats;
    if (rank!=0) {
        heartbeat = std::thread(heartbeatThread, rank);
    } else {
        checkHeartbeats = std::thread(checkHeartbeatsThread);
    }

    // *** Add a short startup sleep on rank0 so we definitely see heartbeats from nodes
    if (rank == 0) {
        std::this_thread::sleep_for(std::chrono::seconds(2));
    }
    // barrier ensures all ranks in sync after startup
    MPI_Barrier(MPI_COMM_WORLD);

    std::string command;
    while(true) {
        if (rank==0) {
            if (!std::getline(std::cin, command)) {
                command.clear(); // no input => we’ll exit
            }
        }
        // parse opType
        std::string operation;
        int target = -1;
        int opType=0;

        if (rank==0 && !command.empty()) {
            std::istringstream iss(command);
            iss >> operation;
            if (operation=="upload" || operation=="retrieve"||
                operation=="search"|| operation=="list_file") {
                opType=1;
            }
            else if (operation=="failover") {
                opType=2;
                iss >> target;
            }
            else if (operation=="recover") {
                opType=3;
                iss >> target;
            }
            else if (operation=="exit") {
                opType=0;
            }
        }

        MPI_Bcast(&opType, 1, MPI_INT, 0, MPI_COMM_WORLD);
        if (opType==0) {
            break;
        }
        if (opType==2 || opType==3) {
            MPI_Bcast(&target,1,MPI_INT,0,MPI_COMM_WORLD);
            if (opType==2) { failover(target, rank); }
            else { recover(target, rank); }
            MPI_Barrier(MPI_COMM_WORLD);
            continue;
        }
        // otherwise opType=1 => full broadcast
        int cmdLen=0;
        if (rank==0) cmdLen=(int)command.size();
        MPI_Bcast(&cmdLen,1,MPI_INT,0,MPI_COMM_WORLD);
        if (cmdLen==0) {
            break;
        }
        std::vector<char> buf(cmdLen+1,'\0');
        if (rank==0) {
            std::memcpy(buf.data(),command.c_str(),cmdLen);
        }
        MPI_Bcast(buf.data(), cmdLen, MPI_CHAR, 0, MPI_COMM_WORLD);

        std::string full(buf.data(), cmdLen);
        std::istringstream iss2(full);
        iss2 >> operation;
        if (operation=="upload") {
            std::string fname,fpath;
            iss2>>fname>>fpath;
            uploadFile(fname,fpath,rank);
        }
        else if(operation=="retrieve") {
            std::string fname;
            iss2>>fname;
            retrieveFile(fname,rank);
        }
        else if(operation=="search") {
            std::string fname, wd;
            iss2>>fname>>wd;
            searchFile(fname,wd,rank,size);
        }
        else if(operation=="list_file") {
            std::string fname;
            iss2>>fname;
            listFile(fname,rank);
        }
        MPI_Barrier(MPI_COMM_WORLD);

        // handle heartbeats
        if (rank==0) {
            int flag;
            MPI_Status st;
            MPI_Iprobe(MPI_ANY_SOURCE,0,MPI_COMM_WORLD,&flag,&st);
            while (flag) {
                int sr;
                MPI_Recv(&sr,1,MPI_INT,MPI_ANY_SOURCE,0,MPI_COMM_WORLD,&st);
                {
                    std::lock_guard<std::mutex> lk(metadataMutex);
                    lastHeartbeats[sr] = std::chrono::system_clock::now();
                    activeNodes.insert(sr);
                }
                MPI_Iprobe(MPI_ANY_SOURCE,0,MPI_COMM_WORLD,&flag,&st);
            }
        }
        MPI_Barrier(MPI_COMM_WORLD);
    }

    running=false;
    if (rank==0 && checkHeartbeats.joinable()) checkHeartbeats.join();
    if (rank!=0 && heartbeat.joinable()) heartbeat.join();

    MPI_Finalize();
    return 0;
}