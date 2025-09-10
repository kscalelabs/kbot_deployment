import atexit
import json
import select
import socket
import sys
import termios
import threading
import time
import tty
from dataclasses import dataclass
from typing import Callable

from rich.live import Live
from rich.table import Table

from motions import Motion, MOTIONS


class KeyboardState:
    """Tracks keyboard presses to update the command vector."""

    def __init__(self, dt) -> None:
        self._reset_cmd()
        
        # Set up stdin for raw input
        self._fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        atexit.register(lambda: termios.tcsetattr(self._fd, termios.TCSADRAIN, old_settings))

        # Start keyboard reading thread
        self._running = True
        self._thread = threading.Thread(target=self._read_keyboard, daemon=True)
        self._thread.start()

        # Motion state
        self._current_motion: Motion | None = None
        self._motion_dt = dt
    
    def _reset_cmd(self) -> None:
        self.cmd = [0.0] * 16

    def set_motion(self, motion_fn: Callable[[float], Motion]):
        self._current_motion = motion_fn(dt=self._motion_dt)

    def _read_keyboard(self) -> None:
        while self._running:
            # Use select to check for input with a timeout
            rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
            if not rlist:
                continue

            try:
                ch = sys.stdin.read(1).lower()

                # Motion controls
                if ch == 'z':
                    self.set_motion(MOTIONS['salute'])
                if ch == 'x':
                    self.set_motion(MOTIONS['wave'])
                # if ch == 'c':
                    self.set_motion(MOTIONS['pickup'])
                #     self.set_motion(MOTIONS['pickup'])
                # if ch == 'v':
                #     self.set_motion(MOTIONS['wild_walk'])
                # if ch == 'b':
                #     self.set_motion(MOTIONS['zombie_walk'])
                # if ch == 'n':
                #     self.set_motion(MOTIONS['pirouette'])
                # if ch == 'm':
                #     self.set_motion(MOTIONS['backflip'])
                # if ch == ',':
                #     self.set_motion(MOTIONS['boxing'])
                # if ch == '.':
                #     self.set_motion(MOTIONS['cone'])
                # if ch == '/':
                #     self.set_motion(MOTIONS['squats'])

                # Test motion controls
                if ch == '1':
                    self.set_motion(MOTIONS['test_rsp'])
                if ch == '2':
                    self.set_motion(MOTIONS['test_rsr'])
                if ch == '3':
                    self.set_motion(MOTIONS['test_rsy'])
                if ch == '4':
                    self.set_motion(MOTIONS['test_re'])
                if ch == '5':
                    self.set_motion(MOTIONS['test_rw'])
                if ch == '6':
                    self.set_motion(MOTIONS['test_lsp'])
                if ch == '7':
                    self.set_motion(MOTIONS['test_lsr'])
                if ch == '8':
                    self.set_motion(MOTIONS['test_lsy'])
                if ch == '9':
                    self.set_motion(MOTIONS['test_le'])
                # if ch == '0': # need zero for reset
                #     self.set_motion(MOTIONS['test_lw'])


                # base controls
                if ch == '0':
                    self._reset_cmd()
                    self._current_motion = None  # Stop any playing motion
                if ch == 'w':
                    self.cmd[0] += 0.1
                if ch == 's':
                    self.cmd[0] -= 0.1
                if ch == 'a':
                    self.cmd[1] += 0.1
                if ch == 'd':
                    self.cmd[1] -= 0.1
                if ch == 'q':
                    self.cmd[2] += 0.1
                if ch == 'e':
                    self.cmd[2] -= 0.1
                
                # base pose
                if ch == '=':
                    self.cmd[3] += 0.05
                if ch == '-':
                    self.cmd[3] -= 0.05
                if ch == 'r':
                    self.cmd[4] += 0.1
                if ch == 'f':
                    self.cmd[4] -= 0.1
                if ch == 't':
                    self.cmd[5] += 0.1
                if ch == 'g':
                    self.cmd[5] -= 0.1

                # diy clamp
                self.cmd = [max(-0.3, min(0.3, cmd)) for cmd in self.cmd]

            except (IOError, EOFError):
                continue

    def get_cmd(self) -> list[float]:
        if self._current_motion is not None:
            result = self._current_motion.get_next_motion_frame()
            if result is None:
                # Motion complete, reset
                self._current_motion = None
                return self.cmd
            
            commands, positions = result
            self.cmd = [*commands, *positions]
    
        return self.cmd


@dataclass
class ControlVectorMessage:
    XVel: float = 0.0
    YVel: float = 0.0
    YawRate: float = 0.0
    BaseHeight: float = 0.0
    BaseRoll: float = 0.0
    BasePitch: float = 0.0
    RShoulderPitch: float = 0.0
    RShoulderRoll: float = 0.0
    RElbowPitch: float = 0.0
    RElbowRoll: float = 0.0
    RWristPitch: float = 0.0
    LShoulderPitch: float = 0.0
    LShoulderRoll: float = 0.0
    LElbowPitch: float = 0.0
    LElbowRoll: float = 0.0
    LWristPitch: float = 0.0

    def to_msg(self) -> bytes:
        json_str = (
            json.dumps({k: getattr(self, k) for k in self.__dataclass_fields__})
            + "\n"
        )
        return json_str.encode("utf-8")


class Commander:
    def __init__(self, dt: float):
        self.dt = dt

        self.UDP_IP = "localhost"
        self.UDP_PORT = 10000
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Start command thread
        self._running = True
        self._keyboard = None
        self._thread = threading.Thread(target=self._command_loop, daemon=True)
        self._thread.start()

    def set_keyboard(self, kb: KeyboardState) -> None:
        self._keyboard = kb

    def _command_loop(self) -> None:
        while self._running:
            if self._keyboard is not None:
                cmd = ControlVectorMessage(*self._keyboard.get_cmd())
                self.sock.sendto(cmd.to_msg(), (self.UDP_IP, self.UDP_PORT))
            time.sleep(self.dt)


class CommandDisplay:
    def __init__(self, keyboard: KeyboardState, commander: Commander):
        self.keyboard = keyboard
        self.commander = commander

    def make_bar(self, value: float, width: int = 100, color: str = "white", inverted: bool = False) -> str:
        min_val, max_val = -0.3, 0.3
        normalized = (value - min_val) / (max_val - min_val)
        if inverted:
            normalized = 1.0 - normalized
        normalized = max(0.0, min(1.0, normalized))
        filled = int(normalized * width)
        bar = "█" * filled + " " * (width - filled)
        return f"[{color}][{bar}][/{color}] {value:+.2f}"

    def render_table(self) -> Table:
        table = Table(title="Control Vector", box=None)
        table.add_column("Axis", justify="right", no_wrap=True)
        table.add_column("Value", justify="center")
        
        # Main controls with distinct colors
        table.add_row("XVel", self.make_bar(self.keyboard.cmd[0], color="red"))
        table.add_row("YVel", self.make_bar(self.keyboard.cmd[1], color="green"))
        table.add_row("Yaw", self.make_bar(self.keyboard.cmd[2], color="blue"))
        table.add_row("")

        table.add_row("BaseHeight", self.make_bar(self.keyboard.cmd[3], color="yellow"))
        table.add_row("BaseRoll", self.make_bar(self.keyboard.cmd[4], color="cyan"))
        table.add_row("BasePitch", self.make_bar(self.keyboard.cmd[5], color="magenta"))
        table.add_row("")

        # All other commands in gradient
        names = list(ControlVectorMessage.__dataclass_fields__.keys())[6:]
        for i, name in enumerate(names):
            r = int(255 * (1 - i/len(names)))
            g = int(100 + (155 * i/len(names)))  
            b = int(255 * i/len(names))
            table.add_row(name, self.make_bar(self.keyboard.cmd[i+6], color=f"rgb({r},{g},{b})"))
        
        return table

    def run(self) -> None:
        with Live(self.render_table(), refresh_per_second=50, screen=False) as live:
            try:
                while True:
                    live.update(self.render_table())
                    time.sleep(0.05)
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    dt = 0.02
    kb = KeyboardState(dt)
    cmd = Commander(dt)
    cmd.set_keyboard(kb)
    CommandDisplay(kb, cmd).run()