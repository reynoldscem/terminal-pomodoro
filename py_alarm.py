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
import pyglet
import time
import sys
import os

REFRESH_RATE = 0.05
GOODBYE_DELAY = 0.2
FLASH_TIME = 0.75

REAL_DIRNAME = os.path.dirname(os.path.realpath(__file__))
DEFAULT_SOUNDPATH = os.path.join(
    'siren_noise_soundbible_shorter_fadeout.wav'
)
REAL_DIRNAME = os.path.dirname(os.path.realpath(__file__))
pyglet.resource.path = [os.path.join(REAL_DIRNAME, 'data')]
TIME_FORMAT = '{:02d}:{:02d} {} {:02d}:00'


TERMINAL_WIDTH = None
CHANGED = False

ALTERNATE_SCREEN_ENTER, ALTERNATE_SCREEN_EXIT = '\033[?1049h', '\033[?1049l'
TERM_HIDE_CHAR, TERM_SHOW_CHAR = '\033[?25l', '\033[?25h'
SAVE_TERM, RESTORE_TERM = '\033[?47h', '\033[?47l'
INVERT_ON, INVERT_OFF = '\033[7m', '\033[27m'
BOLD_ON, BOLD_OFF = '\033[1m', '\033[21m'
BLUE, DEFAULT = '\033[34m', '\033[39m'

PYGLET_VOLUME_LIB_REQ = '1.4.0b1'
if pyglet.version < PYGLET_VOLUME_LIB_REQ:
    import warnings
    version_warning_string = (
        'Volume not supported on pyglet < {}, you have {}'
        ''.format(PYGLET_VOLUME_LIB_REQ, pyglet.version)
    )
    warnings.warn(version_warning_string, UserWarning)


def get_terminal_width():
    return shutil.get_terminal_size((80, 20)).columns


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


class VolumeAction(argparse.Action):
    def __call__(self, parser, args, value, option_string=None):
        if pyglet.version < PYGLET_VOLUME_LIB_REQ and value is not None:
            print(
                'Setting volume requires pyglet {}, you have pyglet {}.'
                ''.format(PYGLET_VOLUME_LIB_REQ, pyglet.version).center(
                    TERMINAL_WIDTH
                ),
            )
            print('Will ignore value of --volume'.center(TERMINAL_WIDTH))
            print('Enter to continue Ctrl + C to exit.'.center(TERMINAL_WIDTH))
            input()
            value = None
        elif value is not None:
            value = float(value)

        setattr(args, self.dest, value)


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

    parser.add_argument(
        '--volume', type=float,
        default=(0.05 if pyglet.version >= PYGLET_VOLUME_LIB_REQ else None),
        action=VolumeAction,
        help='Volume from 0 to 1.'
    )

    return parser


def run_sound(sound_path, volume=None):
    sound = pyglet.resource.media(sound_path)
    player = sound.play()

    if volume is not None and volume < 1:
        player.volume = volume

    # This is kind of an abuse of pyglet
    pyglet.clock.schedule_once(lambda x: pyglet.app.exit(), sound.duration)
    pyglet.app.run()


def minutes_seconds_elapsed(elapsed):
    minutes, seconds = divmod(elapsed, 60)

    return int(minutes), int(seconds)


def print_time(minutes, seconds, total_minutes, paused=False):
    print('\r', end='')

    separator = u'\u23F8' if paused else '/'

    time_str = TIME_FORMAT.format(minutes, seconds, separator, total_minutes)
    time_str = time_str.center(TERMINAL_WIDTH)
    if paused:
        time_str = ''.join((BOLD_ON, BLUE, time_str, DEFAULT, BOLD_OFF))
    print(time_str, end='')


def clear_if_changed():
    global CHANGED
    if CHANGED:
        print()
        # This might give you some garbage characters depending
        #  on the value of $TERM. They should be hidden anyway.
        # Also won't work on Windows. But nor will most of this...
        os.system('clear')
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
            sound_dir = os.path.dirname(os.path.realpath(sound_path))
            pyglet.resource.path.append(sound_dir)

            return os.path.basename(sound_path)

        for path in pyglet.resource.path:
            if os.path.isfile(os.path.join(path, sound_path)):
                return sound_path
        else:
            raise FileNotFoundError('Could not locate {}'.format(sound_path))


def resize_handler(*args):
    global TERMINAL_WIDTH, CHANGED

    TERMINAL_WIDTH = get_terminal_width()
    CHANGED = True


def exit(reset_terminal, *args, code=0):
    try:
        print('', end='\r')
        print('Goodbye!'.center(TERMINAL_WIDTH))

        # Hack to stop strange callback happening on exit
        pyglet.media.drivers.get_audio_driver().delete()

        time.sleep(GOODBYE_DELAY)
    finally:
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


def check_os():
    platform_string = system().lower()
    if 'linux' in platform_string:
        return
    elif 'win32' in platform_string:
        # Just give up... There is a plenty of posix / linux stuff here.
        #  Feel free to remove this and try it out if you'd like to push
        #  towards Windows support, but it's not on my radar.
        raise OSError(
            'System is {}. Windows is not supported.'
            ''.format(platform_string)
        )
    elif 'darwin' in platform_string:
        import warnings
        version_warning_string = (
            'System is {}. Mac may not work as expected. Support is planned.'
            ' If this doesn\'t work for you please report your issue.'
            ''.format(platform_string)
        )
        warnings.warn(version_warning_string, UserWarning)
    else:
        import warnings
        version_warning_string = (
            'System is {}. This may not work as expected.'
            ' Support is not planned.'
            ' If you would like support, and this tool doesn\'t work for you'
            ' please report your issue, with details of your system.'
            ''.format(platform_string)
        )
        warnings.warn(version_warning_string, UserWarning)


def main():
    args = build_parser().parse_args()

    check_os()
    check_tty()
    try:
        reset_terminal = setup_terminal()
        exit_partial_app = partial(exit, reset_terminal)

        resize_handler()

        signal.signal(signal.SIGWINCH, resize_handler)
        signal.signal(signal.SIGINT, exit_partial_app)

        main_loop(args.countdowns, args.sound_path, args.volume)
    except Exception as e:
        sys.stderr.write(
            'Exception was raised: {}'.format(e).center(TERMINAL_WIDTH)
        )

        exit_partial_app(code=1)


if __name__ == '__main__':
    main()
