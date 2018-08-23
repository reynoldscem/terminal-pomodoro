import pyglet
import time

MINUTES = 25


def run_sound():
    sound = pyglet.resource.media('data/siren_noise_soundbible.wav')
    sound.play()
    pyglet.clock.schedule_once(lambda x: pyglet.app.exit(), sound.duration)
    pyglet.app.run()


def countdown():
    upper_limit = MINUTES * 60
    upper_limit = 5
    start_time = time.time()
    print()
    while True:
        elapsed = time.time() - start_time
        minutes, seconds = divmod(elapsed, 60)
        _, minutes = divmod(minutes, 60)
        print(
            '\r{:02d}:{:02d} / {:02d}:00'
            ''.format(int(minutes), int(seconds), MINUTES), end='')
        time.sleep(0.05)
        if elapsed >= upper_limit:
            break


def main():
    try:
        while True:
            countdown()
            run_sound()
            print()
            input('Press any key to reset')
    except KeyboardInterrupt:
        print('', end='\r')
        print()
        print('Goodbye!')


if __name__ == '__main__':
    main()
