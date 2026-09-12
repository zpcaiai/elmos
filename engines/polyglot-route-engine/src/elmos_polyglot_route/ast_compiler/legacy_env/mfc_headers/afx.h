#pragma once
#include <cstdint>
#include <string>
#include <cstring>
#include <cstdio>

typedef uint32_t DWORD;
typedef int BOOL;
typedef unsigned char BYTE;
typedef unsigned short WORD;
typedef const char* LPCSTR;
typedef char* LPSTR;

#define TRUE 1
#define FALSE 0
#ifndef NULL
#define NULL nullptr
#endif

class CObject {
public:
    virtual ~CObject() = default;
};

class CString {
private:
    std::string m_data;
public:
    CString() = default;
    CString(const char* s) : m_data(s ? s : "") {}
    CString(const std::string& s) : m_data(s) {}
    int GetLength() const { return static_cast<int>(m_data.length()); }
    bool IsEmpty() const { return m_data.empty(); }
    void Empty() { m_data.clear(); }
    const char* GetBuffer() const { return m_data.c_str(); }
    operator const char*() const { return m_data.c_str(); }
    CString& operator=(const char* s) { m_data = (s ? s : ""); return *this; }
    CString& operator+=(const char* s) { if (s) m_data += s; return *this; }
};
