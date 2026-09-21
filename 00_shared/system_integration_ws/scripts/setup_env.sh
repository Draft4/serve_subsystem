#!/usr/bin/env bash
# Source this file after building all workspaces.
TENNIS_PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source /opt/ros/jazzy/setup.bash
source /home/pi/localization_ws/install/local_setup.bash
source /home/pi/Sensor_Publication/ros2_ws/install/local_setup.bash
source "$TENNIS_PROJECT_ROOT/00_shared/interfaces_ws/install/local_setup.bash"
source "$TENNIS_PROJECT_ROOT/03_planning_control/serve_planning_ws/install/local_setup.bash"
source "$TENNIS_PROJECT_ROOT/03_planning_control/launcher_planning_ws/install/local_setup.bash"
source "$TENNIS_PROJECT_ROOT/04_actuation_control/actuation_supervisor_ws/install/local_setup.bash"
source "$TENNIS_PROJECT_ROOT/04_actuation_control/launcher_actuation_ws/install/local_setup.bash"
source "$TENNIS_PROJECT_ROOT/01_mission_decision/mission_ws/install/local_setup.bash"
source "$TENNIS_PROJECT_ROOT/01_mission_decision/operator_ws/install/local_setup.bash"
source "$TENNIS_PROJECT_ROOT/00_shared/system_integration_ws/install/local_setup.bash"
