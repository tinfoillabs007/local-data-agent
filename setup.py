from setuptools import setup, find_packages

setup(
    name="local_agent_helper",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "requests",
        "python-dotenv",
        "flask",
    ],
) 