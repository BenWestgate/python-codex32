"""Setup module for python-codex32."""

with open("README.md", encoding="utf-8") as f:
    long_description = f.read()

from setuptools import setup, find_packages # pylint: disable=import-error

setup(
    name="codex32",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[],
    extras_require={
        "dev": ["pytest", "flake8"]
    },
    author="Ben Westgate",
    description="A Python implementation of Codex32.",
    long_description_content_type="text/markdown",
    url="https://github.com/BenWestgate/python-codex32",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.10",
)
