"""Run external tools so a timeout kills the whole tool, not just its launcher.

Tools are started through `conda run ...` (or `bash -c "a | b"`), so the process that
subprocess.run() kills on timeout is only the launcher; the real tool (Flye, SPAdes, ...)
is left running without a parent and keeps using CPU. run() starts the command in its
own session (= its own process group) and on timeout kills the whole group first.
"""
import os
import signal
import subprocess
import time

TimeoutExpired = subprocess.TimeoutExpired
CalledProcessError = subprocess.CalledProcessError
CompletedProcess = subprocess.CompletedProcess
PIPE = subprocess.PIPE
DEVNULL = subprocess.DEVNULL
STDOUT = subprocess.STDOUT


def kill_group(proc: subprocess.Popen, grace: float = 10) -> None:
    """Kill `proc` and everything in its process group: SIGTERM, then SIGKILL for
    whatever is still alive after `grace` seconds.

    Only kills a group that `proc` leads (started with start_new_session=True), so it
    can never hit the caller's own group (e.g. the Celery worker); otherwise it kills
    just `proc`."""
    pgid = proc.pid
    try:
        if os.getpgid(proc.pid) != pgid:
            proc.kill()
            proc.wait()
            return
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        proc.wait()
        return
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        proc.poll()  # reap the leader so a zombie does not count as alive
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.2)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def run(*popenargs, input=None, capture_output=False, timeout=None, check=False, **kwargs):
    """Drop-in replacement for subprocess.run() that kills the whole process group
    on timeout (and on any other exception, e.g. KeyboardInterrupt) before re-raising."""
    if input is not None and kwargs.get("stdin") is not None:
        raise ValueError("stdin and input arguments may not both be used.")
    if capture_output:
        if kwargs.get("stdout") is not None or kwargs.get("stderr") is not None:
            raise ValueError("stdout and stderr arguments may not be used with capture_output.")
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    if input is not None:
        kwargs["stdin"] = subprocess.PIPE
    kwargs.setdefault("start_new_session", True)

    with subprocess.Popen(*popenargs, **kwargs) as process:
        try:
            stdout, stderr = process.communicate(input, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            kill_group(process)
            # collect what the tool wrote before it was killed
            exc.stdout, exc.stderr = process.communicate()
            raise
        except BaseException:
            kill_group(process)
            raise
        retcode = process.poll()
        if check and retcode:
            raise subprocess.CalledProcessError(retcode, process.args, output=stdout, stderr=stderr)
    return subprocess.CompletedProcess(process.args, retcode, stdout, stderr)
