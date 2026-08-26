# =============================================================================
# Stepper class -- MicroPython on ESP32-C3
# VERSION 2 of 2: hardware Timer generates the step tick; asyncio sequences
#                 the moves.
# =============================================================================
#
# WHY asyncio AND NOT _thread
# ---------------------------
# MicroPython gives you two concurrency options. asyncio is the right one here:
#
# 1. The ESP32-C3 is a SINGLE-CORE RISC-V chip. (The original ESP32 is
#    dual-core; the C3 is not.) _thread therefore buys you exactly zero
#    parallelism -- two threads still share one core, taking turns under the
#    GIL. You pay all the cost of threads and get none of the benefit.
#
# 2. Preemption is actively harmful for this workload. Step timing is
#    open-loop: write 4 pins, wait a fixed interval, write again. A preemptive
#    thread switch can land in the middle of that interval and stretch it
#    unpredictably -- audible roughness on a 28BYJ-48, missed steps if it gets
#    bad. asyncio is COOPERATIVE: a task yields only at an explicit `await`, so
#    the switch points are known and the jitter is bounded.
#
# 3. MicroPython's _thread is deliberately minimal: fixed pre-allocated stacks,
#    no join(), no thread pool. The Pi version spawns one process per move
#    command; the thread equivalent would spawn a thread per move and run the
#    C3 out of RAM quickly. asyncio Tasks are cheap, so the same
#    fire-and-forget API survives the port.
#
# 4. asyncio tasks share one address space, so all the multiprocessing
#    scaffolding disappears. multiprocessing.Value existed only because a child
#    process cannot write to the parent's attributes. multiprocessing.Lock
#    becomes asyncio.Lock -- same job (one move at a time per motor), and it
#    hands off FIFO, so queued moves run in the order you issued them.
#
# WHAT THIS VERSION CHANGES, AND WHY
# ----------------------------------
# Version 1 (stepper_async.py) times the steps with asyncio.sleep_ms(). That is
# simple and correct, but MicroPython's scheduler is millisecond-granular and
# sleep_ms(n) means "at least n ms" -- every other ready task runs before this
# one resumes. So the step period is poorly controlled.
#
# Here the timing comes from a hardware timer instead. ONE periodic Timer ticks
# at the step rate and, on each tick, gives every registered motor that has
# work pending exactly one half-step. Consequences:
#
#   * The step period is set by hardware, so it stays put whether you are
#     driving one motor or six. Adding motors makes each tick do slightly more
#     work; it does not make the ticks further apart.
#   * Sub-millisecond periods are available -- 1200 us matches the Pi version.
#   * asyncio's remaining job is coordination, not timing: a move task computes
#     the step count, arms the motor, and sleeps until the timer reports the
#     move complete. The lock still serializes moves per motor.
#
# A CAVEAT ABOUT "ISR" ON THE ESP32 PORT
# -----------------------------------------------
# On the ESP32 family, machine.Timer callbacks are SOFT-scheduled: the real
# interrupt hands the Python callback to the scheduler, which runs it at the
# next bytecode boundary. So it is not a true hard IRQ, and allocating memory
# in it will not blow up the way it would on, say, a Pin.irq(hard=True)
# handler.
#
# We write it allocation-free anyway. Two reasons: it keeps the callback short,
# which keeps the jitter small; and it is the habit that lets this code move to
# a hard-IRQ context unchanged. The rules being followed below are:
#   - integer arithmetic only (in MicroPython a float result is a heap object)
#   - no range(), no list/tuple building, no string formatting, no print()
#   - loops unrolled where a range() object would otherwise be allocated
# The angle in DEGREES is therefore computed outside the callback, from an
# integer step count -- see the `angle` property. That is the main structural
# difference from version 1.
# =============================================================================

import asyncio
import micropython
from machine import Pin, Timer

# If an exception ever escapes a scheduled/IRQ callback, MicroPython needs a
# pre-allocated buffer to build the traceback -- otherwise you get a bare
# "no memory" and no idea what went wrong. Cheap insurance, set once.
micropython.alloc_emergency_exception_buf(100)


class Stepper:

    # --- Class attributes ----------------------------------------------------

    # Half-step drive sequence: 4-bit patterns for IN1..IN4. Walking forward
    # through the list turns the shaft one way, backward the other. Swap a coil
    # pair in your wiring if the direction comes out inverted.
    SEQ = [0b0001, 0b0011, 0b0010, 0b0110,
           0b0100, 0b1100, 0b1000, 0b1001]

    # 28BYJ-48: 8 half-steps/cycle * 64:1 gearbox * 8 = 4096 half-steps per
    # revolution of the OUTPUT shaft.
    STEPS_PER_REV = 4096

    # Step rate in Hz. 833 Hz ~= 1200 us/step, matching the original Pi code
    # (4096 / 833 = 4.9 s per output revolution). Push much past ~1000 Hz and a
    # 28BYJ-48 runs out of torque and stalls -- it will buzz instead of turn.
    STEP_FREQ = 833

    # Every motor shares ONE timer. This matters on the C3, which only exposes
    # two hardware timers -- a timer per motor would cap you at two motors.
    _timer = None
    _motors = []

    def __init__(self, pins):
        """pins -- 4 GPIO numbers wired to IN1..IN4 on the ULN2003 board."""
        # Build Pin objects once. Constructing them later (in the callback, or
        # per step) would allocate and could stall a move on a GC pass.
        self._pins = [Pin(p, Pin.OUT) for p in pins]

        # --- state read/written by the timer callback ---
        # Everything here is an int on purpose (see the header note about
        # allocation). Degrees are derived from _position on demand.
        self._phase = 0        # index into SEQ, 0..7
        self._position = 0     # absolute position, in half-steps, [0, 4096)
        self._remaining = 0    # half-steps left in the current move; 0 = idle
        self._dir = 1          # +1 or -1

        # Set by the callback when a move finishes; awaited by the move task.
        # ThreadSafeFlag (not Event) is the correct type here: it is explicitly
        # designed to be set from an interrupt / scheduled callback and wake an
        # asyncio task safely. Only one task may wait on a given flag -- which
        # is guaranteed here, because the lock below means only one move task
        # per motor is ever in flight.
        self._done = asyncio.ThreadSafeFlag()

        # One move at a time per motor; other moves queue up FIFO.
        self._lock = asyncio.Lock()

        Stepper._motors.append(self)
        Stepper.start()        # idempotent -- starts the shared timer once

    # --- Shared timer --------------------------------------------------------

    @classmethod
    def start(cls, freq=None, timer_id=0):
        """Start the shared step timer. Safe to call repeatedly."""
        if cls._timer is not None:
            return
        cls._timer = Timer(timer_id)
        cls._timer.init(mode=Timer.PERIODIC,
                        freq=freq or cls.STEP_FREQ,
                        callback=cls._tick)
        # If your MicroPython build's esp32 Timer does not accept `freq`, the
        # equivalent using explicit tick units is:
        #   cls._timer.init(mode=Timer.PERIODIC, period=1200, tick_hz=1000000,
        #                   callback=cls._tick)
        # (`period` on its own is in milliseconds, which is too coarse here --
        # that is the whole problem this version exists to solve.)

    @classmethod
    def stop(cls):
        """Stop the shared timer and de-energize every motor."""
        if cls._timer is not None:
            cls._timer.deinit()
            cls._timer = None
        for m in cls._motors:
            m.release()

    @staticmethod
    def _tick(t):
        """
        Timer callback -- runs at STEP_FREQ Hz, forever.

        Give one half-step to each motor that has work pending, and nothing to
        the ones that don't. Keep it short: this runs ~833 times a second.
        """
        for m in Stepper._motors:
            if m._remaining:
                m._pulse()

    def _pulse(self):
        """
        Exactly one half-step. Called only from _tick.

        Allocation-free by construction: only small-int arithmetic and
        Pin.value() calls. Note the unrolled pin writes -- `for i in range(4)`
        would allocate a range object on every single step.
        """
        s = Stepper.SEQ[self._phase]
        p = self._pins
        p[0].value(s & 0b0001)
        p[1].value(s & 0b0010)
        p[2].value(s & 0b0100)
        p[3].value(s & 0b1000)

        # Advance. Python's % is non-negative even for negative operands, so
        # (0 - 1) % 8 == 7 and reverse motion wraps correctly.
        self._phase = (self._phase + self._dir) % 8
        self._position = (self._position + self._dir) % Stepper.STEPS_PER_REV

        self._remaining -= 1
        if not self._remaining:
            # Move complete -- wake whichever task is awaiting this motor.
            self._done.set()

    # --- Position ------------------------------------------------------------

    @property
    def angle(self):
        """
        Current output shaft angle in degrees, [0, 360).

        Derived here rather than tracked incrementally, which is strictly
        better than the Pi version: `_position` is an exact integer step count,
        so there is no floating-point error accumulating over thousands of
        steps, and the callback never has to touch a float.
        """
        return self._position * 360 / Stepper.STEPS_PER_REV

    def zero(self):
        """Declare the current physical position to be 0 degrees."""
        self._position = 0

    def release(self):
        """
        De-energize all coils: no holding torque, but no ~200 mA and no heat.
        Worth calling when a motor will sit idle. If the shaft gets back-driven
        while released, our tracked position is no longer true.
        """
        for p in self._pins:
            p.value(0)

    # --- Internals -----------------------------------------------------------

    async def _rotate(self, delta):
        """Relative move, degrees. Computes the step count, then runs it."""
        async with self._lock:              # wait for any move already running
            num_steps = int(round(abs(delta) * Stepper.STEPS_PER_REV / 360))
            await self._arm(num_steps, 1 if delta >= 0 else -1)

    async def _go_angle(self, new_angle):
        """
        Absolute move, degrees, taking the shorter way around.

        The shortest-path math happens AFTER the lock is acquired, i.e. once
        every move queued ahead of this one has finished. That is essential:
        the answer depends on where the shaft actually is, and if we computed
        it back when go_angle() was called, a queue of absolute moves would
        every one of them plan from the same stale starting position.
        """
        async with self._lock:
            # Integer steps end to end -- no float drift, and the number handed
            # to the callback is exactly the number we computed.
            target = int(round((new_angle % 360) * Stepper.STEPS_PER_REV / 360))
            target %= Stepper.STEPS_PER_REV

            delta = (target - self._position) % Stepper.STEPS_PER_REV
            # delta is in [0, 4096). If going forward is more than half a turn,
            # going backward is shorter.
            if delta > Stepper.STEPS_PER_REV // 2:
                delta -= Stepper.STEPS_PER_REV

            await self._arm(abs(delta), 1 if delta >= 0 else -1)

    async def _arm(self, num_steps, direction):
        """
        Hand `num_steps` to the timer and wait for it to work through them.
        Call with the lock held.

        This is the whole handoff between the two worlds: asyncio decides WHAT
        to do, the timer decides WHEN.
        """
        if num_steps == 0:
            return

        # The flag should already be clear (each move consumes exactly one
        # set), but clearing makes the invariant explicit and survives an
        # interrupted move. Remove this line if your build's ThreadSafeFlag
        # has no clear().
        self._done.clear()

        # ORDER MATTERS. `_remaining` is what arms the callback, so it must be
        # written LAST -- otherwise a tick landing between these two lines
        # would step the motor using the previous move's direction. (The
        # bulletproof alternative is to bracket both writes with
        # machine.disable_irq()/enable_irq(); ordering is enough here because a
        # single attribute store is atomic with respect to the callback.)
        self._dir = direction
        self._remaining = num_steps

        # Park until _pulse() reports the last step. This task consumes no CPU
        # while waiting, so the other motors' tasks -- and anything else in
        # your program -- run freely.
        await self._done.wait()

    # --- Public API ----------------------------------------------------------
    #
    # Non-async methods that return IMMEDIATELY, like the Pi version's
    # Process-spawning methods. The move runs as a background Task; several
    # issued in a row queue on the lock and execute in order. Each returns its
    # Task, so you can await one specific move if you want to.

    def rotate(self, delta):
        """Turn `delta` degrees from wherever the shaft is now."""
        return asyncio.create_task(self._rotate(delta))

    def go_angle(self, new_angle):
        """Turn to absolute angle `new_angle`, by the shortest path."""
        return asyncio.create_task(self._go_angle(new_angle))

    async def idle(self):
        """
        Wait until every move queued on this motor has finished.

        The sleep_ms(0) is load-bearing. create_task() only QUEUES a task -- it
        does not start it. Taking the lock immediately would find it unlocked
        (no queued move has run far enough to take it) and return having waited
        for nothing. Yielding once lets every queued task run to its first
        await, putting them all on the lock's waiting list ahead of us; since
        asyncio.Lock is FIFO, acquiring it then means they are all done.
        """
        await asyncio.sleep_ms(0)
        async with self._lock:
            pass


# =============================================================================
# Example
# =============================================================================

async def main():

    # ESP32-C3 GPIO notes -- not every pin is free:
    #   GPIO 11-17 : internal SPI flash. Never use.
    #   GPIO 18,19 : USB D-/D+ (the USB-serial-JTAG console on most C3 boards).
    #   GPIO 20,21 : UART0 TX/RX (the serial console on boards without USB).
    #   GPIO 2,8,9 : strapping pins, sampled at boot. Usable, but a load on
    #                them can stop the board from booting.
    m1 = Stepper([3, 4, 5, 6])
    m2 = Stepper([7, 10, 0, 1])

    m1.zero()
    m2.zero()

    # Queue a routine. Calls return instantly; each motor works its own list in
    # order, both motors advance on the same hardware tick.
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

    await m1.idle()
    await m2.idle()

    print("done: m1 at %.1f deg, m2 at %.1f deg" % (m1.angle, m2.angle))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        # Always kill the timer. It is hardware: it keeps firing after your
        # program ends, and a callback referencing torn-down state is a good
        # way to hardfault the board on the next soft reboot.
        Stepper.stop()
        asyncio.new_event_loop()
