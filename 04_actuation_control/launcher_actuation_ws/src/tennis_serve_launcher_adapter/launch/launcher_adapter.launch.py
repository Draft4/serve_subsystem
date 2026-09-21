from launch import LaunchDescription
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    config = PathJoinSubstitution([
        FindPackageShare("tennis_serve_launcher_adapter"),
        "config",
        "adapter.yaml",
    ])
    return LaunchDescription([
        Node(
            package="tennis_serve_launcher_adapter",
            executable="serve_launcher_adapter_node",
            name="serve_launcher_adapter_node",
            output="screen",
            parameters=[config],
        ),
    ])
