# terminal-pomodoro

Just a simple pomodoro timer for the terminal. Sound plays and terminal flashes
when timer is finished. Hit return during the timer to pause it, and return
again to unpause. Will redraw if terminal changes size (so feel free to make the
font larger / smaller on the fly).

Makes pretty strong assumptions about Linux as the OS. Might work on other POSIX / UNIX OS's.
Windows is a hard no.

If you are on OSX and using iterm2, then if you have a profile called `pyalarm`
it will be enabled while the program is running. I personally just use it to
make the font size larger.

Example:

```$ python py_alarm.py 1 2 3```

For a 1 minute timer, then 2 minute, then 3 on a loop. Without arguments will do 25, 5 on loop.

```
usage: py_alarm.py [-h] [--sound-path SOUND_PATH] [--volume VOLUME]
                   [countdowns [countdowns ...]]

Simple terminal pomodoro timer. By default a 25 minute, then 5 minute timer on
loop.

positional arguments:
  countdowns            Cycle through countdown of this many minutes.

optional arguments:
  -h, --help            show this help message and exit
  --sound-path SOUND_PATH
                        Path to alarm sound.
  --volume VOLUME       Volume from 0 to 1.
```

To use the volume flag you will need `pyglet >= 1.4.0b1`. The `requirements.txt`
will try to install this. Older versions of pyglet will work, but without
volume.
