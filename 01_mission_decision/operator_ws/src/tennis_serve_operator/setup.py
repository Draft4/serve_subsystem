from glob import glob
from setuptools import find_packages, setup

package_name = "tennis_serve_operator"

setup(
    name=package_name,
    version="0.7.0",
    packages=find_packages(exclude=("test",)),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Tennis Robot Team",
    maintainer_email="robot@example.invalid",
    description="tennis_serve_operator for the tennis serving subsystem",
    license="Proprietary",
    entry_points={"console_scripts": [
        "serve_bridge_node = tennis_serve_operator.bridge_node:main",
    ]},
)

