'''Simple terminal pomodoro timer.
By default a 25 minute, then 5 minute timer on loop.
'''
from functools import partial
from itertools import cycle
from copy import deepcopy
import argparse
import termios
import signal
import shutil
import pyglet
import time
import sys
import os

REFRESH_RATE = 0.05
DEFAULT_SOUNDPATH = os.path.join(
    'siren_noise_soundbible_shorter_fadeout.wav'
)
REAL_DIRNAME = os.path.dirname(os.path.realpath(__file__))
pyglet.resource.path = [os.path.join(REAL_DIRNAME, 'data')]
TIME_FORMAT = '{:02d}:{:02d} / {:02d}:00'


TERMINAL_WIDTH = None
CHANGED = False

TERM_HIDE_CHAR, TERM_SHOW_CHAR = ('\033[?25l', '\033[?25h')

PYGLET_VOLUME_LIB_REQ = '1.4.0b1'


def get_terminal_width():
    return shutil.get_terminal_size((80, 20)).columns


def setup_terminal():
    # The following stops the interrupt character (or other special chars)
    #  being echoed into the terminal.
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    new = deepcopy(old)
    new[3] = new[3] & ~termios.ECHO
    termios.tcsetattr(fd, termios.TCSADRAIN, new)
    sys.stdout.write(TERM_HIDE_CHAR)

    def reset_terminal():
        # Reset at the end
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write(TERM_SHOW_CHAR)

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


def print_time(minutes, seconds, total_minutes):
    print('\r', end='')
    time_str = TIME_FORMAT.format(minutes, seconds, total_minutes)
    time_str = time_str.center(TERMINAL_WIDTH)
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


def countdown(minutes_total):
    global TERMINAL_WIDTH

    clear_if_changed()

    upper_limit = minutes_total * 60
    start_time = time.time()
    while True:
        elapsed = time.time() - start_time
        timer_numbers = (*minutes_seconds_elapsed(elapsed), minutes_total)

        print_time(*timer_numbers)
        time.sleep(REFRESH_RATE)

        clear_if_changed()

        if elapsed >= upper_limit:
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
    print('', end='\r')
    print('Goodbye!'.center(TERMINAL_WIDTH))

    # Hack to stop strange callback happening on exit
    pyglet.media.drivers.get_audio_driver().delete()

    reset_terminal()
    sys.exit(code)


def main_loop(countdowns, sound_path, volume=None):
    for countdown_amount in countdowns:
        countdown(countdown_amount)
        run_sound(sound_path, volume=volume)
        print('', end='\r')
        input('Return to reset'.center(TERMINAL_WIDTH))
    else:
        # Shouldn't actually get here.
        print('Out of countdowns!'.center(TERMINAL_WIDTH))


def main():
    try:
        reset_terminal = setup_terminal()
        exit_partial_app = partial(exit, reset_terminal)

        resize_handler()

        signal.signal(signal.SIGWINCH, resize_handler)
        signal.signal(signal.SIGINT, exit_partial_app)

        args = build_parser().parse_args()

        main_loop(args.countdowns, args.sound_path, args.volume)
    except Exception as e:
        print('Exception was raised: {}'.format(e).center(TERMINAL_WIDTH))
        print('Cleaning up'.center(TERMINAL_WIDTH))
        exit_partial_app(code=1)


if __name__ == '__main__':
    main()
