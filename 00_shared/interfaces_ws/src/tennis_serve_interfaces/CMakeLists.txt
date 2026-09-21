cmake_minimum_required(VERSION 3.8)
project(tennis_serve_interfaces)

find_package(ament_cmake REQUIRED)
find_package(action_msgs REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/CourtTarget.msg"
  "msg/TrainingStep.msg"
  "msg/PlannedShot.msg"
  "msg/ChassisAimCommand.msg"
  "msg/LauncherSetpoint.msg"
  "msg/FeedCommand.msg"
  "msg/LauncherState.msg"
  "msg/ServeSystemStatus.msg"
  "srv/PlanShot.srv"
  "srv/PlanAim.srv"
  "srv/CreateJob.srv"
  "srv/GetJob.srv"
  "srv/JobCommand.srv"
  "srv/JobHeartbeat.srv"
  "srv/GetModelInfo.srv"
  "srv/SetLauncherHold.srv"
  "srv/ResetEmergencyStop.srv"
  "action/ExecuteShot.action"
  DEPENDENCIES action_msgs builtin_interfaces std_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
