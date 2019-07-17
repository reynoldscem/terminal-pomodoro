'''Simple terminal pomodoro timer.
By default a 25 minute, then 5 minute timer on loop.
'''
from functools import partial
from platform import system
from itertools import cycle
from copy import deepcopy
import argparse
import _thread
import termios
import select
import signal
import shutil
import time
import sys
import tty
import os

from pydub import AudioSegment
from pydub.utils import get_player_name

import subprocess
from tempfile import NamedTemporaryFile
PLAYER = get_player_name()


def play(seg):
    with NamedTemporaryFile('wb', suffix='.wav') as fd:
        devnull = open(os.devnull, 'w')
        seg.export(fd.name, 'wav')
        subprocess.call(
            [PLAYER, '-nodisp', '-autoexit', fd.name],
            stdout=devnull,
            stderr=devnull,
        )


REFRESH_RATE = 0.05
GOODBYE_DELAY = 0.2
FLASH_TIME = 0.75

VOLUME_ENV_VAR = 'PYALARM_VOLUME'
DEFAULT_VOLUME = 0.05

REAL_DIRNAME = os.path.dirname(os.path.realpath(__file__))
DEFAULT_SOUNDPATH = os.path.join(
    REAL_DIRNAME, 'data',
    'siren_noise_soundbible_shorter_fadeout.wav'
)
REAL_DIRNAME = os.path.dirname(os.path.realpath(__file__))

TIME_FORMAT = '{:02d}:{:02d} {} {:02d}:00'

ITERM_PROGRAM_NAME = 'iTerm.app'
PROFILE_NAME = 'pyalarm'

TERMINAL_HEIGHT = None
TERMINAL_WIDTH = None
CHANGED = False

ALTERNATE_SCREEN_ENTER, ALTERNATE_SCREEN_EXIT = '\033[?1049h', '\033[?1049l'
TERM_HIDE_CHAR, TERM_SHOW_CHAR = '\033[?25l', '\033[?25h'
SAVE_TERM, RESTORE_TERM = '\033[?47h', '\033[?47l'
INVERT_ON, INVERT_OFF = '\033[7m', '\033[27m'
BOLD_ON, BOLD_OFF = '\033[1m', '\033[22m'
BLUE, DEFAULT = '\033[34m', '\033[39m'

WARN_DARWIN = False


def get_terminal_size():
    return shutil.get_terminal_size((80, 20))


def setup_terminal():
    sys.stdout.write(ALTERNATE_SCREEN_ENTER)
    sys.stderr.write(ALTERNATE_SCREEN_EXIT)

    # The following stops the interrupt character (or other special chars)
    #  being echoed into the terminal, along with the cursor.
    sys.stdout.write(TERM_HIDE_CHAR)

    # This prevents user input being echoed out into the terminal, so it can
    #  be exclusively used as input to the program.
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    new = deepcopy(old)
    new[3] = new[3] & ~termios.ECHO
    termios.tcsetattr(fd, termios.TCSADRAIN, new)

    # This saves the contents of the current terminal.
    sys.stdout.write(SAVE_TERM)

    def reset_terminal():
        # Reset all at the end, echoing, showing special chars, and previous
        #  terminal contents.
        try:
            sys.stdout.write(
                TERM_SHOW_CHAR + RESTORE_TERM + ALTERNATE_SCREEN_EXIT
            )
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    return reset_terminal


class CycleAction(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        setattr(args, self.dest, cycle(values))


def volume_out_of_bounds(volume):
    return not 0 <= volume <= 1.0


class VolumeAction(argparse.Action):
    def __call__(self, parser, args, volume, option_string=None):
        volume = float(volume)
        if volume_out_of_bounds(volume):
            raise parser.error('Volume {} is outside of (0, 1)'.format(volume))

        setattr(args, self.dest, volume)


def get_environment_volume():
    volume_from_environment = os.getenv(VOLUME_ENV_VAR)
    error_string = 'Tried to set volume by environment variable: "{}".'
    error_string = error_string.format(VOLUME_ENV_VAR)

    def do_error():
        nonlocal error_string
        error_string = error_string.format(volume_from_environment)
        raise EnvironmentError(error_string) from None

    if volume_from_environment is None:
        return

    try:
        volume_from_environment = float(volume_from_environment)
    except ValueError:
        error_string += ' Appears not to be a valid float: "{}"'
        do_error()

    if volume_out_of_bounds(volume_from_environment):
        error_string += ' Got value outside of [0, 1]: "{}"'
        do_error()

    return volume_from_environment


def build_parser():

    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        'countdowns', type=int, nargs='*',
        action=CycleAction,
        default=cycle((25, 5)),
        help='Cycle through countdown of this many minutes.'
    )

    parser.add_argument(
        '--sound-path', type=str,
        default=DEFAULT_SOUNDPATH,
        action=SoundPathAction,
        help='Path to alarm sound.'
    )

    volume_from_env = get_environment_volume()
    parser.add_argument(
        '--volume', type=float,
        default=volume_from_env if volume_from_env else DEFAULT_VOLUME,
        action=VolumeAction,
        help='Volume from 0 to 1.'
    )

    return parser


def linear_scale_to_DB_offset(volume, eps=1e-12):
    from math import log10
    return 20 * log10(volume + eps)


def run_sound(sound_path, volume=None):
    if volume is not None and volume < 1:
        volume_offset = linear_scale_to_DB_offset(volume)
    else:
        volume_offset = 0

    sound = AudioSegment.from_wav(sound_path)
    play(sound + volume_offset)


def minutes_seconds_elapsed(elapsed):
    minutes, seconds = divmod(elapsed, 60)

    return int(minutes), int(seconds)


def print_time(minutes, seconds, total_minutes, paused=False):
    print('\r', end='')

    separator = '||' if paused else '::'

    time_str = TIME_FORMAT.format(minutes, seconds, separator, total_minutes)
    time_str = time_str.center(TERMINAL_WIDTH)
    if paused:
        time_str = ''.join((BOLD_ON, BLUE, time_str, BOLD_OFF, DEFAULT))
    print(time_str, end='')


def vertical_pad():
    vertical_padding = max(((TERMINAL_HEIGHT - 1) // 2), 0)
    print('\n' * vertical_padding, end='')


def clear_if_changed():
    global CHANGED
    if CHANGED:
        # Perhaps not the best place for this, but it's not doing much harm...
        sys.stdout.flush()

        # This might give you some garbage characters depending
        #  on the value of $TERM. They should be hidden anyway.
        # Also won't work on Windows. But nor will most of this...
        os.system('clear')
        vertical_pad()
        CHANGED = False


def pause_thread(pause_obj):
    while pause_obj.alive:
        while sys.stdin in select.select([sys.stdin], [], [], REFRESH_RATE)[0]:
            sys.stdin.readline()
            pause_obj.toggle_pause()


class PauseObject():
    def __init__(self):
        self.paused = 0
        self.state_changed = False

        self.current_pause_time = 0
        self.total_pause_time = 0

        self.pause_start = None

        self.alive = True

    def toggle_pause(self):
        self.paused = not self.paused
        self.state_changed = True

    def event(self):
        if self.state_changed:
            self.state_changed = False
            return True
        else:
            return False

    def poll(self):
        if self.paused:
            if self.event():
                self.pause_start = time.time()
            self.current_pause_time = time.time() - self.pause_start
        else:
            if self.event():
                self.total_pause_time += self.current_pause_time
            self.current_pause_time = 0

    def pause_time(self):
        if self.paused:
            return self.current_pause_time + self.total_pause_time
        else:
            return self.total_pause_time

    def kill(self):
        self.alive = False


def countdown(minutes_total):
    global TERMINAL_WIDTH

    clear_if_changed()

    upper_limit = minutes_total * 60
    start_time = time.time()

    pause_obj = PauseObject()
    _thread.start_new_thread(pause_thread, (pause_obj,))

    while True:
        pause_obj.poll()

        elapsed = time.time() - start_time - pause_obj.pause_time()
        timer_numbers = (*minutes_seconds_elapsed(elapsed), minutes_total)

        print_time(*timer_numbers, paused=pause_obj.paused)
        time.sleep(REFRESH_RATE)

        clear_if_changed()

        if elapsed >= upper_limit:
            pause_obj.kill()
            sys.stdout.flush()
            break


class SoundPathAction(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        setattr(args, self.dest, self.check_soundpath(values))

    @staticmethod
    def check_soundpath(sound_path):
        if os.path.isfile(sound_path):
            return os.path.realpath(sound_path)
        else:
            raise FileNotFoundError('Could not locate {}'.format(sound_path))


def resize_handler(*args):
    global TERMINAL_WIDTH, TERMINAL_HEIGHT, CHANGED

    TERMINAL_WIDTH, TERMINAL_HEIGHT = get_terminal_size()
    CHANGED = True


def exit(reset_terminal, *args, code=0, extra_funcs=[]):
    try:
        print('', end='\r')

        if code == 0:
            print('Goodbye!'.center(TERMINAL_WIDTH))
            time.sleep(GOODBYE_DELAY)
    finally:
        for extra_func in filter(callable, extra_funcs):
            extra_func()
        reset_terminal()
        sys.exit(code)


def input_thread(input_recorder):
    sys.stdout.write(ALTERNATE_SCREEN_ENTER)
    input_recorder.append(input())


def format_reset_string(string):
    return ''.join(
        (BLUE, INVERT_ON, BOLD_ON, string, BOLD_OFF, INVERT_OFF, DEFAULT)
    )


def reset_loop():
    input_list = []
    _thread.start_new_thread(input_thread, (input_list,))
    os.system('clear')
    vertical_pad()

    even = True
    time_since_flash = 0
    while True:
        clear_if_changed()
        print('', end='\r')
        string = 'Return to reset'.center(TERMINAL_WIDTH)
        reset_string = format_reset_string(string) if even else string

        print(reset_string, end='')

        time.sleep(REFRESH_RATE)
        time_since_flash += REFRESH_RATE
        if time_since_flash >= FLASH_TIME:
            even = not even
            time_since_flash = 0

        if len(input_list) > 0:
            break


def main_loop(countdowns, sound_path, volume=None):
    for countdown_amount in countdowns:
        countdown(countdown_amount)
        run_sound(sound_path, volume=volume)

        # Clear standard input incase user was pressing things before
        #  return message is displayed.
        termios.tcflush(sys.stdin, termios.TCIOFLUSH)
        reset_loop()
    else:
        # Shouldn't actually get here.
        print('Out of countdowns!'.center(TERMINAL_WIDTH))


def check_tty():
    is_tty = os.isatty(sys.stdout.fileno())
    if is_tty:
        return

    print(
        'Can only operate on a tty, are you piping or redirecting output?',
        file=sys.stderr
    )
    sys.exit(1)


def str2hex(string):
    return string.encode('utf-8').hex()


def hex2str(hex_string):
    return bytearray.fromhex(hex_string).decode()


def send_terminfo_request(string):
    hex_string = str2hex(string)
    sys.stdout.write('\033P+q{}\033\\'.format(hex_string))
    sys.stdout.flush()


def read_terminfo_result():
    while True:
        char = sys.stdin.read(1)
        if char == '=':
            break
    result = []
    while True:
        char = sys.stdin.read(1)
        if char == '\x1b':
            break
        result.append(char)
    sys.stdin.read(1)

    return ''.join(result)


def set_profile(profile_name):
    sys.stdout.write('\033]50;SetProfile={}\a'.format(profile_name))
    sys.stdout.flush()


def get_profile():
    file_desc = sys.stdin.fileno()
    old_setting = termios.tcgetattr(file_desc)
    tty.setraw(sys.stdin)

    send_terminfo_request('iTerm2Profile')

    result = read_terminfo_result()

    termios.tcsetattr(file_desc, termios.TCSADRAIN, old_setting)

    return hex2str(result)


def darwin_handler():
    term_program = os.environ['TERM_PROGRAM']

    if term_program != ITERM_PROGRAM_NAME:
        return

    old_profile = get_profile()
    set_profile(PROFILE_NAME)

    def exit_handler():
        set_profile(old_profile)

    return exit_handler


def set_fontsize():
    print()
    subprocess.call(
        ['xdotool', 'key', '--delay', '0'] +
        ['ctrl+plus'] * 32
    )


def reset_fontsize():
    subprocess.call(
        ['xdotool', 'key', '--delay', '0'] +
        ['ctrl+0']
    )


def linux_handler():
    set_fontsize()

    def exit_handler():
        reset_fontsize()

    return exit_handler


def warn_darwin(platform_string):
    import warnings
    version_warning_string = (
        'System is {}. Mac may not work as expected. Support is planned.'
        ' If this doesn\'t work for you please report your issue.'
        ''.format(platform_string)
    )
    warnings.warn(version_warning_string, UserWarning)


def warn_general(platform_string):
    import warnings
    version_warning_string = (
        'System is {}. This may not work as expected.'
        ' Support is not planned.'
        ' If you would like support, and this tool doesn\'t work for you'
        ' please report your issue, with details of your system.'
        ''.format(platform_string)
    )
    warnings.warn(version_warning_string, UserWarning)


def check_os():
    platform_string = system().lower()
    if 'linux' in platform_string:
        return linux_handler()
    elif 'win32' in platform_string:
        # Just give up... There is a plenty of posix / linux stuff here.
        #  Feel free to remove this and try it out if you'd like to push
        #  towards Windows support, but it's not on my radar.
        raise OSError(
            'System is {}. Windows is not supported.'
            ''.format(platform_string)
        )
    elif 'darwin' in platform_string:
        if WARN_DARWIN:
            warn_darwin(platform_string)
        return darwin_handler()
    else:
        warn_general()


def main():
    args = build_parser().parse_args()

    check_tty()
    os_handler = check_os()
    try:
        reset_terminal = setup_terminal()
        exit_ = partial(exit, reset_terminal, extra_funcs=(os_handler,))

        resize_handler()

        signal.signal(signal.SIGWINCH, resize_handler)
        signal.signal(signal.SIGINT, exit_)

        main_loop(args.countdowns, args.sound_path, args.volume)
    except Exception as e:
        sys.stderr.write(
            'Exception was raised: {}'.format(e).center(TERMINAL_WIDTH)
        )

        exit_(code=1)


if __name__ == '__main__':
    main()
