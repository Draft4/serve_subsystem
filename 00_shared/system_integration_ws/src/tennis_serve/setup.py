from glob import glob
from setuptools import find_packages, setup

package_name = "tennis_serve"

setup(
    name=package_name,
    version="0.7.0",
    packages=find_packages(exclude=("test",)),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
        ("share/" + package_name + "/deploy", glob("deploy/*.service")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Tennis Robot Team",
    maintainer_email="robot@example.invalid",
    description="ROS 2 tennis serve integrated launch",
    license="Proprietary",
    entry_points={"console_scripts": []},
)
