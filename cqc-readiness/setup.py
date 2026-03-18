from setuptools import setup, find_packages

setup(
    name="cqc-readiness",
    version="1.0.0",
    packages=find_packages(exclude=["tests*", "migrations*"]),
)
