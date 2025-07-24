"""
Fallback setup.py for older pip versions that don't support pyproject.toml
"""
from setuptools import setup, find_packages

setup(
    name="dab",
    use_scm_version=True,
    packages=find_packages(),
    python_requires=">=3.9",
)
