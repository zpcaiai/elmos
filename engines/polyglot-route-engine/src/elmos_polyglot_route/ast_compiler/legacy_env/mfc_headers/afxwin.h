#pragma once
#include "afx.h"

#define afx_msg
#define DECLARE_MESSAGE_MAP()
#define BEGIN_MESSAGE_MAP(theClass, baseClass)
#define END_MESSAGE_MAP()
#define ON_COMMAND(id, memberFxn)
#define ON_BN_CLICKED(id, memberFxn)

class CCmdTarget : public CObject {};

class CWnd : public CCmdTarget {
public:
    virtual BOOL Create(LPCSTR lpszClassName, LPCSTR lpszWindowName, DWORD dwStyle = 0) { return TRUE; }
    virtual BOOL ShowWindow(int nCmdShow) { return TRUE; }
    virtual void UpdateWindow() {}
};

class CDialog : public CWnd {
protected:
    int m_nIDTemplate;
public:
    CDialog() : m_nIDTemplate(0) {}
    CDialog(int nIDTemplate, CWnd* pParentWnd = nullptr) : m_nIDTemplate(nIDTemplate) {}
    virtual BOOL OnInitDialog() { return TRUE; }
    virtual void OnOK() {}
    virtual void OnCancel() {}
    virtual int DoModal() { return 1; }
};

class CWinApp : public CCmdTarget {
public:
    virtual BOOL InitInstance() { return TRUE; }
    virtual int ExitInstance() { return 0; }
    virtual int Run() { return 0; }
};
