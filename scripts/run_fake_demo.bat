@echo off
cd /d %~dp0\..\backend
echo Starting Moonfall fake demo clients.
echo Open another terminal and run backend\run_server.bat first if the server is not running.
start "Moonfall HR Fake Client" cmd /k python clients\hr_client_example.py
start "Moonfall Arm Fake Client" cmd /k python clients\arm_client_example.py
start "Moonfall Robot Fake Client" cmd /k python clients\robot_client_example.py
start "Moonfall Voice Fake Client" cmd /k python clients\voice_client_example.py
