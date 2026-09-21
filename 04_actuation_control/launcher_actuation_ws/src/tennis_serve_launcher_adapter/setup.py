from glob import glob

from setuptools import find_packages, setup


package_name = "tennis_serve_launcher_adapter"

setup(
    name=package_name,
    version="1.3.0",
    packages=find_packages(exclude=("test",)),
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            ["resource/" + package_name],
        ),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    tests_require=["pytest"],
    zip_safe=True,
    maintainer="Tennis Robot Team",
    maintainer_email="robot@example.invalid",
    description=(
        "Adapter between tennis_serve strategy topics and launcher hardware"
    ),
    license="Proprietary",
    entry_points={
        "console_scripts": [
            (
                "serve_launcher_adapter_node = "
                "tennis_serve_launcher_adapter.adapter_node:main"
            ),
        ],
    },
)
