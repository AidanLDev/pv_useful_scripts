#pragma once
#include <string>
#include <set>
#include <sqlite3.h>

struct SegmentRecord {
    std::string filename;
    std::string path;
    int         sequenceNumber;
    double      startTime;   // Unix timestamp (seconds)
    double      endTime;
    double      duration;
};

class SegmentDatabase {
public:
    explicit SegmentDatabase(const std::string& dbPath);
    ~SegmentDatabase();

    void             insert(const SegmentRecord& r);
    std::set<std::string> allFilenames();

private:
    sqlite3* db_ = nullptr;
};
