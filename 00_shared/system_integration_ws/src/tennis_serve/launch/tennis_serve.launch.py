from launch import LaunchDescription
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def _config(package, filename):
    return PathJoinSubstitution([FindPackageShare(package), "config", filename])


def generate_launch_description():
    return LaunchDescription([
        Node(
            package="tennis_serve_aim", executable="serve_aim_node",
            name="serve_aim_node", output="screen"),
        Node(
            package="tennis_serve_launcher_planning", executable="serve_planner_node",
            name="serve_planner_node", output="screen",
            parameters=[_config("tennis_serve_launcher_planning", "planner.yaml")]),
        Node(
            package="tennis_serve_supervisor", executable="serve_controller_node",
            name="serve_controller_node", output="screen",
            parameters=[_config("tennis_serve_supervisor", "supervisor.yaml")]),
        Node(
            package="tennis_serve_mission", executable="serve_job_manager_node",
            name="serve_job_manager_node", output="screen",
            parameters=[_config("tennis_serve_mission", "mission.yaml")]),
        Node(
            package="tennis_serve_operator", executable="serve_bridge_node",
            name="serve_bridge_node", output="screen",
            parameters=[_config("tennis_serve_operator", "operator.yaml")]),
    ])
