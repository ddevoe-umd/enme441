# =============================================================================
# Stepper class -- MicroPython on ESP32-C3
# Hardware Timer generates the step tick, with shift register drive
#
# Versions:
#   stepper_async.py                asyncio timing, direct drive
#   stepper_async_shifter.py        asyncio timing, shift register
#   stepper_async_timer.py          timer timing,   direct drive
#   stepper_async_timer_shifter.py  timer timing,   shift register   <-- this file
# =============================================================================
#
# Issue with stepper_async.py (no Timer)
# -------------------------------------
# asyncio.sleep_ms(2) does always yield "2 ms". The event loop works out
# how long until the next task is due and calls poll() with that timeout. 
# A poll timeout greater than zero blocks for at least one full system
# tick. So every step where the loop had nothing else to do pays a whole
# tick, and the step period becomes the tick period instead of delay_ms.
#
# The result is counter-intuitive: MORE motors run FASTER. With two
# motors stepping, the 2nd motor is always already overdue by the time the first
# finishes its step, the computed timeout is zero, the poll returns
# immediately, and the loop runs free. Command one motor on its own, and it slows.
#
# Driving the steps from a hardware timer removes the event loop from the
# timing path completely. The tick arrives when it arrives; asyncio's job
# decomes deciding _what_ to do, not when.
#
# One shift per Timer tick (vs. one shift per motor movement in previous versions)
# -------------------------------------
# In the non-Timer code versions, each motor clocked out the whole chain for
# itself, so N moving motors meant performing N shifts.
#
# Here _tick() updates the shared word for all motors on each tick,
# then clocks the entire chain out ONCE. Cost per tick is one shift, 
# whether one motor is moving or 16.  Lag due to the shifting process thus
# scales with motor chain length:
#
#     motors   chain    one shift    duty at 833 Hz (1200 us period)
#     ------   -----    ---------    -------------------------------
#      1-2      8 bit     ~300 us               25%
#      3-4     16 bit     ~600 us               50%
#      5-8     32 bit    ~1200 us              100%  <-- ticks start overrunning
#
# Past 4 motors, move to the approach in shifter_spi.py, which clocks the
# word out in hardware roughly an order of magnitude faster.
#
# =============================================================================

import asyncio
import micropython
from machine import Timer

# If an exception escapes a scheduled/IRQ callback, MicroPython needs a
# pre-allocated buffer to build the traceback, otherwise you get a bare
# "no memory" and no idea what went wrong. Cheap insurance, set once.
micropython.alloc_emergency_exception_buf(100)


class Stepper:

    # --- Class attributes ----------------------------------------------------

    # Half-step drive sequence
    SEQ = [0b0001, 0b0011, 0b0010, 0b0110,
           0b0100, 0b1100, 0b1000, 0b1001]

    # 8 half-steps/cycle * 64:1 gearbox * 8 = 4096 half-steps per revolution
    STEPS_PER_REV = 4096

    # Step rate in Hz.
    STEP_FREQ = 833

    # Set True if a HIGH on a shift register output turns its coil OFF -- some
    # wirings sink current through the coil rather than sourcing it. A property
    # of how the board is built, so it applies to every motor on the chain.
    INVERT = False

    _shifter = None     # shift register (chain or 1 or more)
    _word = 0           # data word being clocked out
    _num_bits = 0       # total number of bits (4 * motor count)
    _count = 0          # motor count
    _timer = None       # hardware timer for every motor
    _motors = []

    def __init__(self, shifter):
        """
        shifter -- the Shifter instance (from shifter.py) driving the chain.
                   Pass the same one to every motor.

        This motor's 4-bit field is assigned automatically: the first Stepper
        created drives bits 0-3 of the chain, the second bits 4-7, and so on.
        Create them in the order they are wired.
        """
        
        # Claim the next free 4-bit field and grow the chain to reach it. The
        # chain is always a whole number of 8-bit registers.
        self.offset = 4 * Stepper._count
        self.mask = 0b1111 << self.offset
        Stepper._count += 1
        Stepper._num_bits = ((Stepper._count * 4 + 7) // 8) * 8
        Stepper._shifter = shifter

        # --- state read/written by the timer callback ---
        # Every one of these is an int on purpose. Degrees are derived from
        # _position on demand, outside the callback, so the callback never
        # touches a float (a float result is a heap object in MicroPython).
        self._phase = 0        # index into SEQ, 0..7
        self._position = 0     # absolute position, in half-steps, [0, 4096)
        self._remaining = 0    # half-steps left in this move; 0 = idle
        self._dir = 1          # +1 or -1

        # Set by the callback when a move finishes; awaited by the move task.
        # ThreadSafeFlag (not Event) is the correct type: it is designed to be
        # set from an interrupt / scheduled callback and wake an asyncio task
        # safely. Only one task may wait on a given flag, which is guaranteed
        # here because the lock below allows one move task per motor at a time.
        self._done = asyncio.ThreadSafeFlag()

        # One move at a time per motor; other moves queue up FIFO.
        self._lock = asyncio.Lock()

        Stepper._motors.append(self)

        # Push the initial (all coils off) state so the hardware matches what
        # we think it is, then make sure the shared timer is running.
        self.release()
        Stepper.start()        # idempotent -- starts the timer once

    # --- Class-level setup and teardown --------------------------------------

    @classmethod
    def reset(cls):
        """
        Forget every motor, so the next one created starts at bits 0-3 again.
        This also stops the timer, which would otherwise keep firing.

        Call this at the top of a run. _count lives on the CLASS, so it keeps
        counting for as long as the module stays imported: re-run your program
        from the REPL without this and the new motors are handed bits 8-15
        instead of 0-7 (A soft reboot -- ctrl-D -- does the same job by 
        reimporting.)

        """
        cls.stop()
        cls._word = 0
        cls._num_bits = 0
        cls._count = 0
        cls._motors = []
        cls._shifter = None

    @classmethod
    def start(cls, freq=None, timer_id=0):
        """Start the shared step timer. Safe to call repeatedly."""
        if cls._timer is not None:  # timer already exists, so return
            return
        cls._timer = Timer(timer_id)
        cls._timer.init(mode=Timer.PERIODIC,
                        freq=freq or cls.STEP_FREQ,
                        callback=cls._tick)

    @classmethod
    def stop(cls):
        """Stop the shared timer and de-energize every motor."""
        if cls._timer is not None:
            cls._timer.deinit()
            cls._timer = None
        for m in cls._motors:
            m.release()

    # --- The timer callback --------------------------------------------------

    @staticmethod
    def _tick(t):
        """
        Timer callback -- runs at STEP_FREQ Hz, forever.

        Advance every motor that has work pending, accumulating all of their
        coil patterns into ONE word, then clock the chain out once.
        Doing the shift here rather than inside each motor makes the
        cost independent of how many motors are moving.

        """
        word = Stepper._word
        active = False     # flag for active motor command in progress

        for m in Stepper._motors:
            if m._remaining:
                word = m._advance(word)
                active = True

        # At least one motor movement has been requested, so perform the shift 
        # (otherwise skip since motors are idle) 
        if active:
            Stepper._word = word
            Stepper._shifter.shift(word, Stepper._num_bits)

    def _advance(self, word):
        """
        Advance this motor one half-step and return the updated chain word.
        Called only from _tick, and deliberately allocation-free: small-int
        arithmetic only, no range(), no float, no print().

        This function just edits its own 4 bits of the word and hands it back.
        """
        s = Stepper.SEQ[self._phase]
        if Stepper.INVERT:
            s = ~s & 0b1111
        word = (word & ~self.mask) | (s << self.offset)

        # Advance. Python's % is non-negative even for negative operands, so
        # (0 - 1) % 8 == 7 and reverse motion wraps correctly.
        self._phase = (self._phase + self._dir) % 8
        self._position = (self._position + self._dir) % Stepper.STEPS_PER_REV

        self._remaining -= 1
        if not self._remaining:
            # Move complete -- wake whichever task is awaiting this motor.
            self._done.set()

        return word

    # --- Position ------------------------------------------------------------

    @property
    def angle(self):
        """
        Current output shaft angle in degrees, [0, 360).

        Derived here rather than tracked incrementally: _position is an exact
        integer step count, so no floating-point error accumulates over
        thousands of steps, and the callback never has to touch a float.
        """
        return self._position * 360 / Stepper.STEPS_PER_REV

    def zero(self):
        """Declare the current physical position to be 0 degrees."""
        self._position = 0

    def release(self):
        """
        De-energize this motor's coils: no holding torque, but no ~200 mA and
        no heat. Worth calling when a motor will sit idle. If the shaft gets
        back-driven while released, our tracked position is no longer true.

        Only this motor's four bits are cleared; the other motors on the chain
        keep holding whatever pattern they were on. Any move still in progress
        is abandoned, so take the lock (or await idle()) first if you care.
        """
        self._remaining = 0

        off = 0b1111 if Stepper.INVERT else 0
        Stepper._word = (Stepper._word & ~self.mask) | (off << self.offset)
        if Stepper._shifter is not None:
            Stepper._shifter.shift(Stepper._word, Stepper._num_bits)

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
        the answer depends on where the shaft actually is, and computing it
        back when go_angle() was called would have a queue of absolute moves
        all planning from the same stale starting position.
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

        # ORDER MATTERS. _remaining is what arms the callback, so it must be
        # written LAST -- otherwise a tick landing between these two lines
        # would step the motor using the previous move's direction. (The
        # bulletproof alternative is to bracket both writes with
        # machine.disable_irq()/enable_irq(); ordering is enough here because a
        # single attribute store is atomic with respect to the callback.)
        self._dir = direction
        self._remaining = num_steps

        # Park until _advance() reports the last step. This task consumes no
        # CPU while waiting, so the other motors' tasks (and anything else in
        # your code, such as an MQTT loop) run freely.
        await self._done.wait()

    # --- Public API ----------------------------------------------------------
    #
    # Non-async methods that return IMMEDIATELY. The move runs as a background
    # Task; several issued in a row queue on the lock and execute in order.
    # Each returns its Task, so you can await one specific move if you want to.

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

    from shifter import Shifter

    # Start the field numbering (and the timer) from scratch, so re-running
    # this from the REPL keeps giving m1 and m2 the same bits.
    Stepper.reset()

    # One Shifter, shared by every motor. Three GPIO total, however many
    # motors you end up adding.
    s = Shifter(data=5, latch=6, clock=7)

    m1 = Stepper(s)
    m2 = Stepper(s)

    # Define the current position as zero for both motors.
    m1.zero()
    m2.zero()

    # Queue a routine. These calls return instantly; each motor works its own
    # list in order, and both motors advance on the same hardware tick.
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

    # Nothing above has moved yet -- the tasks are queued and only run after
    # main() yields. Waiting on both motors does that.
    await m1.idle()
    await m2.idle()

    print("done: m1 at %.1f deg, m2 at %.1f deg" % (m1.angle, m2.angle))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        # kill the class timer and deenergize all motors
        Stepper.stop()
        # remove tasks from the asyncio loop by starting a new loop
        asyncio.new_event_loop()
