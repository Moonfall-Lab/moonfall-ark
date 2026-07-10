from pathlib import Path

PROJECT_NAME = "moonfall-runtime"
RUNTIME_SOURCE = "runtime"

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent
CONFIG_PATH = BACKEND_DIR / "configs" / "moonfall.yaml"
DEFAULT_SQLITE_DB_PATH = BACKEND_DIR / "data" / "moonfall.db"

TOPIC_STATE_WORLD = "state.world"
TOPIC_STATE_EVENT = "state.event"
TOPIC_INPUT_VOICE = "input.voice"
TOPIC_INPUT_CARD = "input.card"
TOPIC_INPUT_DECLARE_LAUNCH = "input.declare_launch"
TOPIC_INPUT_DEBUG = "input.debug"
TOPIC_SENSOR_HR = "sensor.hr"
TOPIC_PERCEPTION_POSE = "perception.pose"
TOPIC_CMD_ROBOT = "cmd.robot"
TOPIC_CMD_ARM = "cmd.arm"
TOPIC_CMD_HUMANOID = "cmd.humanoid"
TOPIC_DEBUG_ECHO = "debug.echo"
TOPIC_DEBUG_LOG = "debug.log"
TOPIC_ERROR = "error"

KNOWN_TOPICS = {
    TOPIC_STATE_WORLD,
    TOPIC_STATE_EVENT,
    TOPIC_INPUT_VOICE,
    TOPIC_INPUT_CARD,
    TOPIC_INPUT_DECLARE_LAUNCH,
    TOPIC_INPUT_DEBUG,
    TOPIC_SENSOR_HR,
    TOPIC_PERCEPTION_POSE,
    TOPIC_CMD_ROBOT,
    TOPIC_CMD_ARM,
    TOPIC_CMD_HUMANOID,
    TOPIC_DEBUG_ECHO,
    TOPIC_DEBUG_LOG,
    TOPIC_ERROR,
}

ALLOWED_ROBOT_IDS = {"r1", "r2", "r3", "r4"}
ALLOWED_ZONES = {"base", "resource_ne", "resource_sw", "relic_nw", "relic_se", "dust_center"}
ALLOWED_ACTIONS = {"move_to", "collect", "escort", "avoid_and_move", "return_base", "stop"}
