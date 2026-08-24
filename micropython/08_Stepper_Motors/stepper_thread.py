# =============================================================================
# Stepper class
# ESP32-C3 using _thread
# =============================================================================
#
# This is stepper_async.py rewritten with _thread instead of asyncio. Same
# public API, same half-step sequence, same integer position tracking -- only
# the concurrency mechanism changes. Read it side by side with the asyncio
# version; the differences are the point of the exercise.
#
# WHAT REPLACES WHAT
# ------------------
#   asyncio.create_task(...)  ->  append a job to a per-motor queue, which a
#                                 per-motor WORKER THREAD works through
#   asyncio.Lock              ->  _thread.allocate_lock()
#   await asyncio.sleep_ms()  ->  time.sleep_us()
#   async def / await         ->  ordinary blocking functions
#
# Note what did NOT happen: we did not spawn a thread per move. asyncio Tasks
# are a few hundred bytes, so the asyncio version can afford to create one per
# move command and let them queue on the lock. A MicroPython thread carries a
# fixed, pre-allocated stack (~5 kB by default, see _STACK_SIZE below), so a
# thread per move would exhaust the C3's heap after a few dozen commands. The
# fix is one long-lived worker thread per motor plus an explicit job queue --
# which is, in effect, hand-rolling the scheduler that asyncio handed us.
#
# THE ONE REAL WIN: time.sleep_us()
# ---------------------------------
# MicroPython's asyncio scheduler is millisecond-granular -- there is no
# asyncio.sleep_us(), so stepper_async.py cannot ask for a step period of, say,
# 1200 us. A thread can: time.sleep_us() takes microseconds and honors them.
# That alone is why this version exists.
#
# THE COSTS, HONESTLY
# -------------------
# 1. NO PARALLELISM. The ESP32-C3 is single-core. Two threads share one core
#    under the GIL, taking turns. Threads buy concurrency, not speed.
#
# 2. sleep_us() BUSY-WAITS. Below the 1 ms FreeRTOS tick there is nothing to
#    block on, so mp_hal_delay_us spins on the hardware timer until the
#    deadline. It returns on time, but it does not give the core away while
#    waiting. N motors stepping at 1200 us means N threads spinning, and the
#    core is saturated well before the arithmetic says it should be. (sleep_ms()
#    is different -- it defers to FreeRTOS and genuinely yields. Set delay_us to
#    a multiple of 1000 and the code below takes that path.)
#
# 3. PREEMPTION LANDS WHERE IT LIKES. asyncio switches tasks only at an
#    explicit `await`, so we know every switch point. FreeRTOS time-slices
#    equal-priority threads on the tick, and MicroPython drops the GIL on a
#    bytecode count, so a switch can land BETWEEN THE FOUR PIN WRITES in
#    _step(). The coils then sit in a half-written pattern until this thread is
#    scheduled again. It is usually microseconds and the motor tolerates it;
#    it is also exactly the unbounded jitter the asyncio version was written to
#    avoid. If you ever need those four writes to be indivisible, bracket them
#    with machine.disable_irq()/enable_irq() -- no tick, no preemption.
#
# 4. THE LOCK IS NOT FIFO. asyncio.Lock hands off to waiters in the order they
#    arrived. _thread's lock makes no such promise -- whichever thread the RTOS
#    happens to run next wins. Here it does not matter, because the job queue
#    (a plain list, popped from the front) is what preserves command order, and
#    the lock only guards the queue itself. Worth knowing before you reach for
#    a _thread lock to sequence anything.
#
# 5. RAM. Budget ~6 kB per motor for the stack, before anything else.
#
# For a hard, constant step rate that degrades with neither motor count nor
# scheduler mood, see stepper_timer.py: a hardware timer generates the tick and
# asyncio only sequences the moves.
# =============================================================================

import _thread
import time
from machine import Pin


class Stepper:

    SEQ = [0b0001, 0b0011, 0b0010, 0b0110,
           0b0100, 0b1100, 0b1000, 0b1001]

    # 28BYJ-48: 8 half-steps per internal motor cycle * 64:1 gearbox
    # = 512 cycles * 8 = 4096 half-steps per revolution of the OUTPUT shaft.
    STEPS_PER_REV = 4096
    STEPS_PER_DEGREE = STEPS_PER_REV / 360

    # Stack allocated for each worker thread, in bytes. MicroPython's minimum on
    # the ESP32 port is 4 kB and the default about 5 kB; 6 kB leaves room for
    # the exception traceback if a worker ever raises. Raise it if you see
    # "stack overflow"; lower it only if you are short on heap and have tested.
    _STACK_SIZE = 6 * 1024

    def __init__(self, pins, delay_us=2000):
        """
        pins     -- 4 GPIO pins wired to IN1..IN4 on the ULN2003 board.
        delay_us -- delay between half-steps, in MICROSECONDS (the asyncio
                    version could only take milliseconds):
                    2000 us/half-step * 4096 half-steps/rev = 8.192 s/rev
                    1200 us/half-step * 4096 half-steps/rev = 4.915 s/rev
                                       (matches stepper_timer.py's 833 Hz)
                    1000 us/half-step * 4096 half-steps/rev = 4.096 s/rev
                    Below ~1000 us a 28BYJ-48 tends to run out of torque and
                    buzz instead of turn. At or above 1000 us, prefer a whole
                    number of milliseconds -- see _wait().
        """
        self.pins = [Pin(p, Pin.OUT) for p in pins]

        self.delay_us = delay_us
        self.position = 0       # absolute position in half-steps, [0, 4096)
        self.seq_state = 0      # where we are in SEQ, 0..7

        # --- job queue, shared between the caller's thread and this motor's
        # --- worker thread. Touch _queue and _busy ONLY while holding _qlock.
        self._queue = []        # pending moves, oldest first
        self._busy = False      # True while the worker is executing a move
        self._alive = True      # cleared by stop() to end the worker
        self._qlock = _thread.allocate_lock()

        # Start this motor's worker. stack_size() is global state that applies
        # to the NEXT thread created, so it is set immediately before the call.
        _thread.stack_size(Stepper._STACK_SIZE)
        _thread.start_new_thread(self._worker, ())

    # --- Internal methods ----------------------------------------------------

    @staticmethod
    # The @staticmethod decorator defines a class method that does not receive
    # an implicit first argument (self). It acts a regular function but lives
    # inside the class's namespace for logical organization.
    def _sgn(x):
        """Signum: -1, 0, or +1."""
        if x == 0:
            return 0
        return int(abs(x) / x)

    def _wait(self):
        """
        Wait one step period.

        sleep_ms() hands the core back to FreeRTOS and costs nothing while it
        waits; sleep_us() spins. So take the cheap path whenever the period is a
        whole number of milliseconds, and pay for the spin only when the caller
        actually asked for sub-millisecond timing.
        """
        if self.delay_us >= 1000 and self.delay_us % 1000 == 0:
            time.sleep_ms(self.delay_us // 1000)
        else:
            time.sleep_us(self.delay_us)

    def _step(self, direction):
        """
        Advance ONE half-step.

        Unlike the asyncio version, this is NOT atomic with respect to the other
        motors: a preemptive switch can land between any two of the pin writes
        below. See note 3 in the header.
        """
        pattern = Stepper.SEQ[self.seq_state]

        for i in range(4):
            self.pins[i].value(pattern & (1 << i))

        # Advance our position in the sequence, wrapping in [0, 7].
        # Python's % returns a non-negative result even for negative operands,
        # so (0 - 1) % 8 == 7 and reverse motion wraps correctly.
        self.seq_state = (self.seq_state + direction) % 8

        # Update the tracked position.
        #
        # Track POSITION (an exact integer count of half-steps), not the angle.
        # Adding a fractional degree per step would accumulate floating-point
        # error over thousands of steps; counting steps cannot drift. The angle
        # in degrees is derived from this count on demand -- see the `angle`
        # property below.
        #
        # No lock is needed: only this motor's worker thread ever writes
        # position, and it is a single attribute store.
        self.position = (self.position + direction) % Stepper.STEPS_PER_REV

    def _steps(self, num_steps, direction):
        """
        Take num_steps half-steps, sleeping one step period between each.

        Checked against _alive every step so that stop() can interrupt a move
        that is already under way. Without this the worker only notices _alive
        between jobs, and a stop() issued during a full revolution would not
        take effect for the ~8 s it takes to finish -- long after stop() has
        released the coils, which the next step would silently re-energize.
        """
        for _ in range(num_steps):
            if not self._alive:     # stop() was called mid-move
                return
            self._step(direction)
            # THE yield point -- in spirit. In the asyncio version this line was
            # the ONLY place another motor could run. Here it is merely the
            # place another motor is MOST LIKELY to run; the RTOS may switch
            # anywhere.
            self._wait()

    # --- Worker thread -------------------------------------------------------

    def _worker(self):
        """
        One per motor, started in __init__ and running until stop().

        Pull one job off the queue and execute it, in order, forever. This loop
        is what replaces asyncio's scheduler and asyncio.Lock together: jobs run
        one at a time (there is only one worker) and in the order they were
        issued (the queue is FIFO).
        """
        while self._alive:
            job = None
            with self._qlock:
                if self._queue:
                    job = self._queue.pop(0)
                    self._busy = True
                else:
                    self._busy = False

            if job is None:
                # Nothing to do. sleep_ms() here, never sleep_us(): an idle
                # motor must not spin. 1 ms of latency before a queued move
                # starts is invisible next to an 8 s revolution.
                time.sleep_ms(1)
                continue

            kind, value = job
            if kind == 'r':
                self._do_rotate(value)
            else:
                self._do_go_angle(value)

    def _enqueue(self, kind, value):
        """Append a job. Called from whatever thread invoked the public API."""
        with self._qlock:
            self._queue.append((kind, value))

    def _do_rotate(self, delta):
        """Relative move, degrees. Positive and negative both allowed."""
        num_steps = int(round(Stepper.STEPS_PER_DEGREE * abs(delta)))
        self._steps(num_steps, self._sgn(delta))

    def _do_go_angle(self, new_angle):
        """
        Absolute move, degrees, taking the shorter way around.

        Run by the worker at the moment the job comes off the queue -- NOT when
        go_angle() was called. That matters: the shortest path depends on where
        the shaft is now, so planning it at call time would make every queued
        absolute move plan from the same stale starting position.

        The whole calculation is done in integer half-steps, so the number of
        steps we take is exactly the number that lands on the target position:
        no float drift, and repeated absolute moves always return to the same
        physical spot.
        """
        target = int(round((new_angle % 360) * Stepper.STEPS_PER_DEGREE))
        target %= Stepper.STEPS_PER_REV

        delta = (target - self.position) % Stepper.STEPS_PER_REV
        # delta is now in [0, 4096). If going forward would take more than
        # half a turn, going backward is shorter.
        if delta > Stepper.STEPS_PER_REV // 2:
            delta -= Stepper.STEPS_PER_REV
        self._steps(abs(delta), self._sgn(delta))

    # --- Public API ----------------------------------------------------------
    #
    # Ordinary methods that return IMMEDIATELY: they only append to the queue.
    # Issue several in a row and the worker executes them in order, while the
    # other motors' workers do the same.
    #
    # Unlike the asyncio version these return nothing -- there is no Task to
    # hand back, so there is no way to wait on one specific move. Use idle() to
    # wait for all of them.

    def rotate(self, delta):
        """Turn `delta` degrees from wherever the shaft is now."""
        self._enqueue('r', delta)

    def go_angle(self, new_angle):
        """Turn to absolute angle `new_angle`, by the shortest path."""
        self._enqueue('a', new_angle)

    def idle(self):
        """
        Block until every move queued on this motor has finished.

        Simpler than its asyncio counterpart, which needed a sleep_ms(0) first
        because create_task() only QUEUES a task and the lock would still look
        free. Here the job is in the list the instant rotate()/go_angle()
        returns, so there is no window in which a pending move is invisible:
        checking the queue and the busy flag together is enough.
        """
        while True:
            with self._qlock:
                if not self._queue and not self._busy:
                    return
            time.sleep_ms(1)

    # --- Position ------------------------------------------------------------

    @property
    def angle(self):
        """
        Current output shaft angle in degrees, [0, 360).

        Derived from `position` rather than tracked incrementally: `position`
        is an exact integer half-step count, so no floating-point error can
        accumulate over thousands of steps.
        """
        return self.position * 360 / Stepper.STEPS_PER_REV

    def zero(self):
        """
        Declare the current physical position to be 0 degrees.

        Call only when the motor is idle. The worker thread also writes
        position, and a zero() landing mid-move would be overwritten by the very
        next step.
        """
        self.position = 0

    def release(self):
        """
        De-energize all coils. The motor loses holding torque (the shaft turns
        freely) but stops drawing ~200 mA and stops getting hot. Call this when
        a motor will sit idle for a while -- and only when it is idle, since a
        running worker will re-energize the coils on its next step. Position
        tracking is unaffected -- but if something back-drives the shaft while
        released, our idea of the angle becomes a lie.
        """
        for p in self.pins:
            p.value(0)

    def stop(self):
        """
        End this motor's worker thread and de-energize it.

        There is no join() in MicroPython's _thread, so we set the flag, wait
        long enough for the worker to notice it, and release the coils. Any
        moves still queued are abandoned, and a move already under way stops
        where it is -- _steps() re-checks the flag before every half-step.

        The wait must cover the worker's two blocking points: the 1 ms idle
        poll, and one step period if it is mid-move. Sleeping delay_us plus a
        small margin covers both, so the coils are released only after the
        worker has stopped writing to them.
        """
        self._alive = False
        time.sleep_us(self.delay_us + 5000)
        self.release()


# =============================================================================
# Example
# =============================================================================

def main():

    # ESP32-C3 GPIO notes -- not every pin is free:
    #   GPIO 11-17 : internal SPI flash. Never use.
    #   GPIO 18,19 : USB D-/D+ (the USB-serial-JTAG console on most C3 boards).
    #   GPIO 20,21 : UART0 TX/RX (the serial console on boards without USB).
    #   GPIO 2,8,9 : strapping pins, sampled at boot. Usable, but a load on
    #                them can stop the board from booting.
    # The sets below stay clear of all of that.
    m1 = Stepper([3, 4, 5, 6])
    m2 = Stepper([7, 10, 0, 1])

    try:
        # Define "here" as zero for both motors. Safe: neither worker has any
        # work yet.
        m1.zero()
        m2.zero()

        # Queue up a routine. These calls all return instantly; each motor's
        # worker thread works through its own list in order, and the two motors
        # run side by side.
        #
        # Note what is missing compared to the asyncio version: nothing has to
        # yield for these to start. The workers are already running, so the
        # first moves are under way before this function reaches the next line.
        m1.go_angle(225)
        m1.go_angle(0)
        m1.go_angle(-90)
        m1.go_angle(0)
        m1.go_angle(-45)
        m1.go_angle(45)
        m1.go_angle(0)

        m2.go_angle(-225)
        m2.go_angle(0)
        m2.go_angle(90)
        m2.go_angle(0)
        m2.go_angle(45)
        m2.go_angle(-45)
        m2.go_angle(0)

        m1.idle()
        m2.idle()

        print("done: m1 at %.1f deg, m2 at %.1f deg" % (m1.angle, m2.angle))

    finally:
        # Always stop the workers. They are real RTOS tasks: they keep running
        # after main() returns, and a soft reboot with threads still stepping
        # is a good way to confuse the board.
        m1.stop()
        m2.stop()


if __name__ == "__main__":
    main()
