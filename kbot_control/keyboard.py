import json
import socket
import time
import threading
from dataclasses import dataclass
from typing import Tuple
import os
import sys
import select
import termios
import tty
import atexit

from rich.live import Live
from rich.table import Table


class KeyboardState:
    """Tracks keybboard presses to update the command vector."""

    def __init__(self) -> None:
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
    
    def _reset_cmd(self) -> None:
        self.cmd = [0.0] * 16

    def _read_keyboard(self) -> None:
        while self._running:
            # Use select to check for input with a timeout
            rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
            if not rlist:
                continue

            try:
                ch = sys.stdin.read(1).lower()

                # base controls
                if ch == '0':
                    self._reset_cmd()
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
    def __init__(self):
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
                cmd = ControlVectorMessage(*self._keyboard.cmd)
                self.sock.sendto(cmd.to_msg(), (self.UDP_IP, self.UDP_PORT))
            time.sleep(1/20)



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
    kb = KeyboardState()
    cmd = Commander()
    CommandDisplay(kb, cmd).run()