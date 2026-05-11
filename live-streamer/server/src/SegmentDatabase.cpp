#include "SegmentDatabase.hpp"
#include <ctime>
#include <cstdio>
#include <stdexcept>

// Format a Unix timestamp as "2026-05-11T11:16:52.360Z" (UTC, millisecond precision).
static std::string toIso8601(double unixTime)
{
    time_t  t  = static_cast<time_t>(unixTime);
    int     ms = static_cast<int>((unixTime - t) * 1000);
    struct tm tm;
    gmtime_r(&t, &tm);
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02d.%03dZ",
                  tm.tm_year + 1900, tm.tm_mon + 1, tm.tm_mday,
                  tm.tm_hour, tm.tm_min, tm.tm_sec, ms);
    return buf;
}

SegmentDatabase::SegmentDatabase(const std::string& dbPath)
{
    if (sqlite3_open(dbPath.c_str(), &db_) != SQLITE_OK)
        throw std::runtime_error("Cannot open DB: " + std::string(sqlite3_errmsg(db_)));

    const char* ddl = R"sql(
        CREATE TABLE IF NOT EXISTS segments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            filename        TEXT    NOT NULL UNIQUE,
            path            TEXT    NOT NULL,
            sequence_number INTEGER NOT NULL,
            start_time      TEXT    NOT NULL,
            end_time        TEXT    NOT NULL,
            duration        REAL    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_time ON segments (start_time, end_time);
    )sql";

    char* errmsg = nullptr;
    if (sqlite3_exec(db_, ddl, nullptr, nullptr, &errmsg) != SQLITE_OK) {
        std::string msg = errmsg;
        sqlite3_free(errmsg);
        throw std::runtime_error("DB init failed: " + msg);
    }
}

SegmentDatabase::~SegmentDatabase()
{
    if (db_) sqlite3_close(db_);
}

void SegmentDatabase::insert(const SegmentRecord& r)
{
    const char* sql =
        "INSERT OR IGNORE INTO segments "
        "(filename, path, sequence_number, start_time, end_time, duration) "
        "VALUES (?, ?, ?, ?, ?, ?)";

    std::string start = toIso8601(r.startTime);
    std::string end   = toIso8601(r.endTime);

    sqlite3_stmt* stmt;
    sqlite3_prepare_v2(db_, sql, -1, &stmt, nullptr);
    sqlite3_bind_text  (stmt, 1, r.filename.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text  (stmt, 2, r.path.c_str(),     -1, SQLITE_TRANSIENT);
    sqlite3_bind_int   (stmt, 3, r.sequenceNumber);
    sqlite3_bind_text  (stmt, 4, start.c_str(),      -1, SQLITE_TRANSIENT);
    sqlite3_bind_text  (stmt, 5, end.c_str(),        -1, SQLITE_TRANSIENT);
    sqlite3_bind_double(stmt, 6, r.duration);
    sqlite3_step(stmt);
    sqlite3_finalize(stmt);
}

std::set<std::string> SegmentDatabase::allFilenames()
{
    std::set<std::string> out;
    sqlite3_stmt* stmt;
    sqlite3_prepare_v2(db_, "SELECT filename FROM segments", -1, &stmt, nullptr);
    while (sqlite3_step(stmt) == SQLITE_ROW)
        out.insert(reinterpret_cast<const char*>(sqlite3_column_text(stmt, 0)));
    sqlite3_finalize(stmt);
    return out;
}
