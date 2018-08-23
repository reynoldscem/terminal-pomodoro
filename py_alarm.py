'''Simple terminal pomodoro timer.'''
from itertools import cycle
import argparse
import pyglet
import time
import os

REFRESH_RATE = 0.05
DEFAULT_SOUNDPATH_RELATIVE_TO_FILE_DIR = (
    'data/siren_noise_soundbible_shorter.wav'
)


class CycleAction(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        setattr(args, self.dest, cycle(values))


def build_parser():

    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        'countdowns', type=int, nargs='*',
        action=CycleAction,
        default=cycle((25, 5)),
        help='Cycle through countdown of this many minutes.'
    )

    file_dir = os.path.dirname(__file__)
    parser.add_argument(
        '--sound-path', type=str,
        default=os.path.join(file_dir, DEFAULT_SOUNDPATH_RELATIVE_TO_FILE_DIR),
        help='Path to alarm sound.'
    )

    return parser


def run_sound(sound_path):
    sound = pyglet.resource.media(sound_path)
    sound.play()

    # This is kind of an abuse of pyglet
    pyglet.clock.schedule_once(lambda x: pyglet.app.exit(), sound.duration)
    pyglet.app.run()


def countdown(minutes_total):
    upper_limit = minutes_total * 60
    start_time = time.time()
    print()
    while True:
        elapsed = time.time() - start_time
        minutes, seconds = divmod(elapsed, 60)
        _, minutes = divmod(minutes, 60)
        print(
            '\r{:02d}:{:02d} / {:02d}:00'
            ''.format(int(minutes), int(seconds), minutes_total), end='')
        time.sleep(REFRESH_RATE)
        if elapsed >= upper_limit:
            break


def main():
    args = build_parser().parse_args()

    try:
        while True:
            countdown(next(args.countdowns))
            run_sound(args.sound_path)
            print()
            input('Press return to reset')
    except KeyboardInterrupt:
        print('', end='\r')
        print()
        print('Goodbye!')

        # Hack to stop strange callback happening on exit
        pyglet.media.drivers.get_audio_driver().delete()
    except StopIteration:
        # Shouldn't actually get here, because of defaults in argparse.
        print('Need to have some countdowns!')


if __name__ == '__main__':
    main()
