from setuptools import Extension, setup

setup(name="legacy-numpy-extension", ext_modules=[Extension("legacy_array", ["legacy_array.c"])])
