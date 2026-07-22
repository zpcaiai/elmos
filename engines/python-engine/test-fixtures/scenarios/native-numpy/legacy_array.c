#include <Python.h>
#include <numpy/arrayobject.h>

static void *elmos_numpy_api_marker(void) {
    return PyArray_API;
}
