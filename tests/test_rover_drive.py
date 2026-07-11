import socket
import time
import unittest

from tests.rover_helpers import CLIENTS  # noqa: F401

from rover_agent.drive import RoverDrive  # noqa: E402


class DriveTest(unittest.TestCase):
    def setUp(self):
        self.rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rx.bind(("127.0.0.1", 0))
        self.rx.settimeout(0.5)
        self.port = self.rx.getsockname()[1]

    def tearDown(self):
        self.rx.close()

    def _drain(self, seconds):
        msgs = []
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                msgs.append(self.rx.recv(64).decode())
            except socket.timeout:
                break
        return msgs

    def test_default_keepalive_period_is_250ms(self):
        drive = RoverDrive("127.0.0.1", self.port)
        try:
            self.assertEqual(drive._period, 0.25)
        finally:
            drive.close()

    def test_clamp_keepalive_and_close(self):
        drive = RoverDrive("127.0.0.1", self.port, period_ms=25)
        drive.set_wheels(150, -230)  # 超界 → clamp 到 ±100
        msgs = self._drain(0.2)
        self.assertIn("100,-100", msgs)
        # 保活线程 25ms 一发，0.2s 内应重发多次
        self.assertGreaterEqual(msgs.count("100,-100"), 3)

        drive.close()
        time.sleep(0.05)
        tail = self._drain(0.3)
        self.assertTrue(tail, "close() 应发出停车指令")
        self.assertEqual(tail[-1], "0,0")

    def test_stop(self):
        drive = RoverDrive("127.0.0.1", self.port, period_ms=25)
        drive.set_wheels(60, 60)
        drive.stop()
        time.sleep(0.06)
        msgs = self._drain(0.1)
        self.assertIn("0,0", msgs)
        drive.close()

    def test_stale_command_expires_to_stop(self):
        drive = RoverDrive("127.0.0.1", self.port, period_ms=20)
        drive._command_ttl = 0.06
        self._drain(0.05)  # 丢掉线程启动时发送的初始 0,0
        drive.set_wheels(60, 60)
        time.sleep(0.09)
        msgs = self._drain(0.2)
        self.assertIn("0,0", msgs)
        drive.close()

    def test_timed_pulse_stops_without_waiting_for_control_loop(self):
        drive = RoverDrive("127.0.0.1", self.port, period_ms=200)
        self._drain(0.05)
        drive.start_pulse(-40, 40, duration_sec=0.05)
        time.sleep(0.09)
        msgs = self._drain(0.3)
        self.assertIn("-40,40", msgs)
        self.assertIn("0,0", msgs)
        self.assertEqual(msgs[-1], "0,0")
        drive.close()


if __name__ == "__main__":
    unittest.main()
