"""
Flight Control Test Harness

This script systematically tests the experimental flight control commands
to validate that they work correctly and to build calibration data.

The experimental flight command format is:
[CMD_ID, throttle, yaw, pitch, roll, checksum]

Where CMD_ID = 0x50 and values are 0-255 with 128 as neutral.

Usage:
    python -m autonomous.testing.flight_control_test --mode interactive
    python -m autonomous.testing.flight_control_test --mode calibrate
    python -m autonomous.testing.flight_control_test --mode test_throttle
"""

import sys
import os
import time
import json
import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Add parent directory to path to import teky
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from teky.drone_controller_advanced import TEKYDroneControllerAdvanced

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FlightControlTester:
    """Test harness for flight control calibration"""

    def __init__(self, drone_ip: str = "192.168.1.1", log_dir: str = "logs/flight_tests"):
        self.drone_ip = drone_ip
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.drone: Optional[TEKYDroneControllerAdvanced] = None
        self.test_log: List[Dict] = []
        self.is_connected = False

        # Test parameters
        self.neutral_value = 128
        self.min_value = 0
        self.max_value = 255

    def connect(self) -> bool:
        """Connect to drone"""
        logger.info(f"Connecting to drone at {self.drone_ip}...")

        try:
            self.drone = TEKYDroneControllerAdvanced(drone_ip=self.drone_ip)

            if self.drone.connect():
                logger.info("✅ Connected to drone successfully")
                self.is_connected = True

                # Start video stream (useful for monitoring)
                if self.drone.start_video_stream():
                    logger.info("✅ Video stream started")
                else:
                    logger.warning("⚠️ Video stream failed to start (non-critical)")

                return True
            else:
                logger.error("❌ Failed to connect to drone")
                return False

        except Exception as e:
            logger.error(f"❌ Exception during connection: {e}")
            return False

    def disconnect(self):
        """Disconnect from drone"""
        if self.drone and self.is_connected:
            logger.info("Disconnecting from drone...")
            self.drone.disconnect()
            self.is_connected = False
            logger.info("✅ Disconnected")

    def log_test(self, test_name: str, control_values: Dict, observations: str, success: bool):
        """Log a test result"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "test_name": test_name,
            "control_values": control_values,
            "observations": observations,
            "success": success
        }
        self.test_log.append(entry)
        logger.info(f"📝 Logged: {test_name} - {'SUCCESS' if success else 'FAILED'}")

    def save_log(self, filename: Optional[str] = None):
        """Save test log to file"""
        if not filename:
            filename = f"flight_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        filepath = self.log_dir / filename
        with open(filepath, 'w') as f:
            json.dump(self.test_log, f, indent=2)

        logger.info(f"💾 Test log saved to: {filepath}")
        return filepath

    def set_controls(self, throttle: int, yaw: int, pitch: int, roll: int, duration: float = 1.0):
        """
        Set flight control values for a duration

        Args:
            throttle: 0-255, 128=neutral
            yaw: 0-255, 128=neutral (rotation)
            pitch: 0-255, 128=neutral (forward/back)
            roll: 0-255, 128=neutral (left/right)
            duration: How long to hold these values (seconds)
        """
        if not self.drone or not self.is_connected:
            logger.error("❌ Not connected to drone")
            return False

        logger.info(f"Setting controls: T={throttle}, Y={yaw}, P={pitch}, R={roll} for {duration}s")

        # Set values
        self.drone.flight_controller.throttle = throttle
        self.drone.flight_controller.yaw = yaw
        self.drone.flight_controller.pitch = pitch
        self.drone.flight_controller.roll = roll

        # Hold for duration
        time.sleep(duration)

        return True

    def reset_controls(self):
        """Reset all controls to neutral"""
        if self.drone and self.is_connected:
            logger.info("🔄 Resetting controls to neutral")
            self.drone.flight_controller.reset()
            time.sleep(0.5)

    def test_throttle_range(self):
        """Test throttle response across range"""
        logger.info("\n" + "="*60)
        logger.info("🚁 THROTTLE RANGE TEST")
        logger.info("="*60)
        logger.info("This test will vary throttle from low to high")
        logger.info("Observe drone behavior and note:")
        logger.info("  - At what value does it lift off?")
        logger.info("  - What value maintains hover?")
        logger.info("  - What value causes rapid ascent?")
        logger.info("="*60 + "\n")

        input("Press ENTER when ready to start (make sure area is clear)...")

        # Test sequence: below neutral, neutral, above neutral
        test_values = [
            (100, "Below neutral - should descend/stay grounded"),
            (128, "Neutral - baseline"),
            (140, "Slightly above neutral - gentle lift"),
            (150, "Moderate throttle - hover?"),
            (160, "Higher throttle - ascent"),
            (128, "Back to neutral")
        ]

        for throttle, description in test_values:
            logger.info(f"\n📊 Testing throttle={throttle}: {description}")
            obs = input("Press ENTER to apply, then describe what happens: ")

            self.set_controls(throttle=throttle, yaw=128, pitch=128, roll=128, duration=2.0)

            observations = input("Observations (behavior, altitude change): ")
            self.log_test(
                f"throttle_test_{throttle}",
                {"throttle": throttle, "yaw": 128, "pitch": 128, "roll": 128},
                observations,
                success=True
            )

        self.reset_controls()
        logger.info("\n✅ Throttle range test complete\n")

    def test_pitch_range(self):
        """Test pitch (forward/backward) response"""
        logger.info("\n" + "="*60)
        logger.info("🚁 PITCH RANGE TEST")
        logger.info("="*60)
        logger.info("This test will vary pitch (forward/backward movement)")
        logger.info("Assumes drone is hovering at stable altitude")
        logger.info("="*60 + "\n")

        hover_throttle = input("Enter hover throttle value (from previous test, default 150): ")
        hover_throttle = int(hover_throttle) if hover_throttle else 150

        input("Press ENTER when drone is hovering stably...")

        test_values = [
            (100, "Backward pitch"),
            (128, "Neutral pitch"),
            (140, "Slight forward"),
            (150, "Moderate forward"),
            (128, "Back to neutral")
        ]

        for pitch, description in test_values:
            logger.info(f"\n📊 Testing pitch={pitch}: {description}")
            input("Press ENTER to apply: ")

            self.set_controls(throttle=hover_throttle, yaw=128, pitch=pitch, roll=128, duration=2.0)

            observations = input("Observations (movement direction, speed): ")
            self.log_test(
                f"pitch_test_{pitch}",
                {"throttle": hover_throttle, "yaw": 128, "pitch": pitch, "roll": 128},
                observations,
                success=True
            )

        self.reset_controls()
        logger.info("\n✅ Pitch range test complete\n")

    def test_roll_range(self):
        """Test roll (left/right) response"""
        logger.info("\n" + "="*60)
        logger.info("🚁 ROLL RANGE TEST")
        logger.info("="*60)
        logger.info("This test will vary roll (left/right movement)")
        logger.info("="*60 + "\n")

        hover_throttle = input("Enter hover throttle value (default 150): ")
        hover_throttle = int(hover_throttle) if hover_throttle else 150

        input("Press ENTER when drone is hovering stably...")

        test_values = [
            (100, "Roll left"),
            (128, "Neutral roll"),
            (140, "Slight right"),
            (150, "Moderate right"),
            (128, "Back to neutral")
        ]

        for roll, description in test_values:
            logger.info(f"\n📊 Testing roll={roll}: {description}")
            input("Press ENTER to apply: ")

            self.set_controls(throttle=hover_throttle, yaw=128, pitch=128, roll=roll, duration=2.0)

            observations = input("Observations (movement direction, speed): ")
            self.log_test(
                f"roll_test_{roll}",
                {"throttle": hover_throttle, "yaw": 128, "pitch": 128, "roll": roll},
                observations,
                success=True
            )

        self.reset_controls()
        logger.info("\n✅ Roll range test complete\n")

    def test_yaw_range(self):
        """Test yaw (rotation) response"""
        logger.info("\n" + "="*60)
        logger.info("🚁 YAW RANGE TEST")
        logger.info("="*60)
        logger.info("This test will vary yaw (rotation)")
        logger.info("="*60 + "\n")

        hover_throttle = input("Enter hover throttle value (default 150): ")
        hover_throttle = int(hover_throttle) if hover_throttle else 150

        input("Press ENTER when drone is hovering stably...")

        test_values = [
            (100, "Rotate counter-clockwise"),
            (128, "Neutral yaw"),
            (140, "Slight clockwise"),
            (150, "Moderate clockwise"),
            (128, "Back to neutral")
        ]

        for yaw, description in test_values:
            logger.info(f"\n📊 Testing yaw={yaw}: {description}")
            input("Press ENTER to apply: ")

            self.set_controls(throttle=hover_throttle, yaw=yaw, pitch=128, roll=128, duration=2.0)

            observations = input("Observations (rotation direction, speed): ")
            self.log_test(
                f"yaw_test_{yaw}",
                {"throttle": hover_throttle, "yaw": yaw, "pitch": 128, "roll": 128},
                observations,
                success=True
            )

        self.reset_controls()
        logger.info("\n✅ Yaw range test complete\n")

    def interactive_mode(self):
        """Interactive control for manual testing"""
        logger.info("\n" + "="*60)
        logger.info("🎮 INTERACTIVE CONTROL MODE")
        logger.info("="*60)
        logger.info("Manual control interface for testing")
        logger.info("Commands:")
        logger.info("  t <value>  - Set throttle (0-255)")
        logger.info("  y <value>  - Set yaw (0-255)")
        logger.info("  p <value>  - Set pitch (0-255)")
        logger.info("  r <value>  - Set roll (0-255)")
        logger.info("  reset      - Reset all to neutral (128)")
        logger.info("  status     - Show current values")
        logger.info("  log <msg>  - Log observation")
        logger.info("  quit       - Exit interactive mode")
        logger.info("="*60 + "\n")

        while True:
            try:
                cmd = input("Control> ").strip().lower()

                if not cmd:
                    continue

                if cmd == "quit":
                    break

                elif cmd == "reset":
                    self.reset_controls()

                elif cmd == "status":
                    if self.drone:
                        fc = self.drone.flight_controller
                        logger.info(f"Current values: T={fc.throttle}, Y={fc.yaw}, P={fc.pitch}, R={fc.roll}")

                elif cmd.startswith("log "):
                    obs = cmd[4:]
                    if self.drone:
                        fc = self.drone.flight_controller
                        self.log_test(
                            "interactive_observation",
                            {"throttle": fc.throttle, "yaw": fc.yaw, "pitch": fc.pitch, "roll": fc.roll},
                            obs,
                            success=True
                        )

                elif cmd.startswith("t "):
                    value = int(cmd[2:])
                    if 0 <= value <= 255:
                        if self.drone:
                            self.drone.flight_controller.throttle = value
                            logger.info(f"Throttle set to {value}")
                    else:
                        logger.error("Value must be 0-255")

                elif cmd.startswith("y "):
                    value = int(cmd[2:])
                    if 0 <= value <= 255:
                        if self.drone:
                            self.drone.flight_controller.yaw = value
                            logger.info(f"Yaw set to {value}")
                    else:
                        logger.error("Value must be 0-255")

                elif cmd.startswith("p "):
                    value = int(cmd[2:])
                    if 0 <= value <= 255:
                        if self.drone:
                            self.drone.flight_controller.pitch = value
                            logger.info(f"Pitch set to {value}")
                    else:
                        logger.error("Value must be 0-255")

                elif cmd.startswith("r "):
                    value = int(cmd[2:])
                    if 0 <= value <= 255:
                        if self.drone:
                            self.drone.flight_controller.roll = value
                            logger.info(f"Roll set to {value}")
                    else:
                        logger.error("Value must be 0-255")

                else:
                    logger.warning(f"Unknown command: {cmd}")

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error: {e}")

        self.reset_controls()
        logger.info("\n✅ Interactive mode exited\n")

    def run_full_calibration(self):
        """Run complete calibration sequence"""
        logger.info("\n" + "="*60)
        logger.info("🔧 FULL CALIBRATION SEQUENCE")
        logger.info("="*60)
        logger.info("This will run all calibration tests in sequence")
        logger.info("Make sure you have a clear, safe testing area")
        logger.info("Keep emergency stop ready!")
        logger.info("="*60 + "\n")

        input("Press ENTER to start full calibration...")

        try:
            self.test_throttle_range()
            time.sleep(2)

            self.test_pitch_range()
            time.sleep(2)

            self.test_roll_range()
            time.sleep(2)

            self.test_yaw_range()
            time.sleep(2)

            logger.info("\n✅ Full calibration complete!")

            # Save results
            logfile = self.save_log()
            logger.info(f"\n📊 Review results in: {logfile}")
            logger.info("Use this data to create calibration mapping in config/drone_config.yaml")

        except KeyboardInterrupt:
            logger.warning("\n⚠️ Calibration interrupted by user")
            self.reset_controls()
            self.save_log("calibration_interrupted.json")


def main():
    parser = argparse.ArgumentParser(description="Flight Control Test Harness")
    parser.add_argument(
        "--mode",
        choices=["interactive", "calibrate", "test_throttle", "test_pitch", "test_roll", "test_yaw"],
        default="interactive",
        help="Test mode to run"
    )
    parser.add_argument(
        "--drone-ip",
        default="192.168.1.1",
        help="Drone IP address"
    )

    args = parser.parse_args()

    tester = FlightControlTester(drone_ip=args.drone_ip)

    try:
        if not tester.connect():
            logger.error("❌ Failed to connect. Exiting.")
            return 1

        if args.mode == "interactive":
            tester.interactive_mode()

        elif args.mode == "calibrate":
            tester.run_full_calibration()

        elif args.mode == "test_throttle":
            tester.test_throttle_range()

        elif args.mode == "test_pitch":
            tester.test_pitch_range()

        elif args.mode == "test_roll":
            tester.test_roll_range()

        elif args.mode == "test_yaw":
            tester.test_yaw_range()

        # Save log before exiting
        if tester.test_log:
            tester.save_log()

    except KeyboardInterrupt:
        logger.info("\n\n⚠️ Test interrupted by user")

    except Exception as e:
        logger.error(f"\n\n❌ Unexpected error: {e}", exc_info=True)

    finally:
        tester.reset_controls()
        tester.disconnect()

    return 0


if __name__ == "__main__":
    sys.exit(main())
