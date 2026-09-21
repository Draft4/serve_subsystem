#!/usr/bin/env bash
set -e

TENNIS_PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source /opt/ros/jazzy/setup.bash
source /home/pi/localization_ws/install/local_setup.bash
source /home/pi/Sensor_Publication/ros2_ws/install/local_setup.bash

for workspace in \
  00_shared/interfaces_ws \
  03_planning_control/serve_planning_ws \
  03_planning_control/launcher_planning_ws \
  04_actuation_control/actuation_supervisor_ws \
  04_actuation_control/launcher_actuation_ws \
  01_mission_decision/mission_ws \
  01_mission_decision/operator_ws \
  00_shared/system_integration_ws
do
  cd "$TENNIS_PROJECT_ROOT/$workspace"
  colcon build --symlink-install
  source install/local_setup.bash
done
