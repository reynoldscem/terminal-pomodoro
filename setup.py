from setuptools import setup

setup(
    name='terminal-pomodoro',
    version='0.1',
    description='Terminal pomodoro timer',
    entry_points={
        'console_scripts': ['terminal-pomodoro=py_alarm:main']
    }
)
