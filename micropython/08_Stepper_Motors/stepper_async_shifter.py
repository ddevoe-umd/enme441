# =============================================================================
# Stepper class
# ESP32-C3 using asyncio, driving the coils through a 74HC595 shift register
# =============================================================================
#
# The shift register keeps the pin count CONSTANT: data, latch, clock.
#
#     motors      direct drive      shift register
#     -------     ------------      -----------------
#        1          4 GPIO            3 GPIO   (1 x 74HC595)
#        2          8 GPIO            3 GPIO   (1 x 74HC595)
#        4         16 GPIO            3 GPIO   (2 x 74HC595 chained)
#        8         32 GPIO            3 GPIO   (4 x 74HC595 chained)
#       16         64 GPIO            3 GPIO   (8 x 74HC595 chained)
#
# Each 74HC595 supplies 8 outputs = 2 motors
#
# A shift register chain is written as ONE word of length N * 8, where
# N is the number of shift register.  Every motor step is a 
# read-modify-write of that shared word followed by a shift of
# the whole chain:
#
#     1 SR, 2 motors, 8-bit word:
#       bits:   7  6  5  4 | 3  2  1  0
#               \-motor 2-/  \-motor 1-/
#
#     2 SRs, 4 motors, 16-bit word:
#       bits:  15 14 13 12 | 11 10  9  8 | 7  6  5  4 | 3  2  1  0
#               \-motor 4-/   \-motor 3-/  \-motor 2-/  \-motor 1-/
#
# NO LOCK GUARDS THE SHARED WORD
# -----------------------------------
# This is the payoff for cooperative scheduling, and it is worth reflecting on.
# _step() reads the shared word, modifies its own field, writes it back, and
# calls Shifter.shift() -- and contains no `await` anywhere in that sequence.
# Under asyncio, a function with no await runs to completion before any other
# task gets the CPU. So the read-modify-write is atomic and the shift cannot
# interleave with another motor's shift, for free.
#
# Write the same class with _thread and this stops being true:
# A preemptive switch can land between the read and the write, or midway
# through clocking out a word, and you would need a lock around the whole
# sequence. Same code, different concurrency model, different correctness.
#
# TRADE-OFF FOR UNLIMITED MOTOR COUNT
# ------------------------------------------------------
# Direct drive costs 4 Pin.value() calls per half-step, regardless of
# motor count. A shift costs, per bit, a data write plus a clock ping,
# and Shifter._ping() sits in a 10 us busy wait. Rough arithmetic on a C3,
# ~35 us per bit:
#
#     motors    chain     time to clock out one word
#     ------    -----     --------------------------
#       1-2      8 bit       ~300 us
#       3-4     16 bit       ~600 us
#       5-8     32 bit      ~1200 us
#      9-16     64 bit      ~2400 us
#
# And every motor pays that on EVERY step, for the whole word, not just its own
# field, so the cost per step grows with the square of the motor count once
# they are all moving at once. Against a 2 ms step period, two motors is ~15%
# overhead; at eight motors a single word takes longer to clock out than the
# step period itself, and the motors simply run slower than you asked.
#
# To push that ceiling out, the escape hatches are shifter_spi.py (clocks the
# word out in hardware, roughly an order of magnitude faster than bit-banging,
# which buys back most of the table above) and stepper_timer.py (hardware-timed
# steps).
#
# NOTE: shifter.py must be on the board alongside this file.
# =============================================================================

import asyncio
from shifter import Shifter


class Stepper:

    SEQ = [0b0001, 0b0011, 0b0010, 0b0110,
           0b0100, 0b1100, 0b1000, 0b1001]

    # 28BYJ-48: 8 half-steps per internal motor cycle * 64:1 gearbox
    # = 512 cycles * 8 = 4096 half-steps per revolution of the OUTPUT shaft.
    STEPS_PER_REV = 4096
    STEPS_PER_DEGREE = STEPS_PER_REV / 360

    # Set True if a HIGH on a shift register output turns its coil OFF -- some
    # wirings sink current through the coil rather than sourcing it, and the
    # lecture example in stepper_with_shifter.py is one. A property of how the
    # board is built, so it applies to every motor on the chain.
    INVERT = False

    # --- The shared chain ----------------------------------------------------
    # One 74HC595 chain, shared by every Stepper. _word is what is currently
    # clocked out to it, _num_bits is how long it has grown, and _count is how
    # many motors have been created (which is what decides the next motor's
    # field).
    _word = 0
    _num_bits = 0
    _count = 0

    def __init__(self, shifter, delay_ms=2):
        """
        shifter  -- the Shifter instance (from shifter.py) driving the chain.
        delay_ms -- delay between half-steps. As in stepper_async.py, asyncio's
                    millisecond scheduler is the floor; but note that the shift
                    itself now eats a few hundred microseconds of every step, so
                    the effective period is longer than this number.

        This motor's 4-bit field is assigned automatically: the first Stepper
        created drives bits 0-3 of the chain, the second bits 4-7, and so on.
        Create them in the order they are wired.

        WIRING CHECK: which physical Q output a given word bit reaches depends
        on how many registers are chained and which way round they are. Bring up
        ONE motor first and confirm it turns the expected direction before
        adding a second. If it steps backwards, swap a coil pair.
        """
        # Claim the next free 4-bit field and grow the chain to reach it. The
        # chain is always a whole number of 8-bit registers.
        self.offset = 4 * Stepper._count
        self.mask = 0b1111 << self.offset
        Stepper._count += 1
        Stepper._num_bits = ((Stepper._count * 4 + 7) // 8) * 8

        self.shifter = shifter
        self.delay_ms = delay_ms
        self.position = 0       # absolute position in half-steps, [0, 4096)
        self.seq_state = 0      # where we are in SEQ, 0..7

        self.lock = asyncio.Lock()   # One lock per motor

        # Push the initial (all coils off) state so the hardware matches what
        # we think it is.
        self._write(0)

    @classmethod
    def reset(cls):
        """
        Forget every motor, so the next one created starts at bits 0-3 again.

        Call this at the top of a run. _count lives on the CLASS, so it keeps
        counting for as long as the module stays imported: re-run your program
        from the REPL without this and the new motors are handed bits 8-15
        instead of 0-7, the chain silently doubles in length, and nothing turns.
        (A soft reboot -- ctrl-D -- does the same job by reimporting everything.)
        """
        cls._word = 0
        cls._num_bits = 0
        cls._count = 0

    # --- Internal methods -----------------------------------------------------

    @staticmethod
    # The @staticmethod decorator defines a class method that does not receive
    # an implicit first argument (self). It acts a regular function but lives
    # inside the class's namespace for logical organization.
    def _sgn(x):
        """Signum: -1, 0, or +1."""
        if x == 0:
            return 0
        return int(abs(x) / x)

    def _write(self, pattern):
        """
        Put a 4-bit coil pattern into this motor's field and clock the whole
        chain out.

        No `await` anywhere in here -- that is what makes the read-modify-write
        of the shared word safe without a lock. See the header.
        """
        if Stepper.INVERT:
            pattern = ~pattern & 0b1111

        Stepper._word = (Stepper._word & ~self.mask) | (pattern << self.offset)
        self.shifter.shift(Stepper._word, Stepper._num_bits)

    def _step(self, direction):
        """
        Advance ONE half-step. Pure computation and one shift -- no awaits,
        so this is atomic with respect to other asyncio tasks
        """
        self._write(Stepper.SEQ[self.seq_state])

        # Advance our position in the sequence, wrapping in [0, 7].
        # Python's % returns a non-negative result even for negative operands,
        # so (0 - 1) % 8 == 7 and reverse motion wraps correctly.
        self.seq_state = (self.seq_state + direction) % 8

        # Update the tracked position. All asyncio tasks share this object.
        #
        # Track POSITION (an exact integer count of half-steps), not the angle.
        # Adding a fractional degree per step would accumulate floating-point
        # error over thousands of steps; counting steps cannot drift. The angle
        # in degrees is derived from this count on demand -- see the `angle`
        # property below.
        self.position = (self.position + direction) % Stepper.STEPS_PER_REV

    async def _steps(self, num_steps, direction):
        """Take num_steps half-steps, yielding to other tasks between each."""
        for _ in range(num_steps):
            self._step(direction)
            # THE yield point. While this task is parked here, every other
            # motor's task gets to run -- including its turn at the shifter.
            await asyncio.sleep_ms(self.delay_ms)

    async def _rotate(self, delta):
        """Relative move, degrees. Positive and negative both allowed."""
        async with self.lock:            # wait for any move already in flight
            num_steps = int(round(Stepper.STEPS_PER_DEGREE * abs(delta)))
            await self._steps(num_steps, self._sgn(delta))

    async def _go_angle(self, new_angle):
        """
        Absolute move, degrees, taking the shorter way around.

        The whole calculation is done in integer half-steps, so the number of
        steps we take is exactly the number that lands on the target position:
        no float drift, and repeated absolute moves always return to the same
        physical spot.
        """
        async with self.lock:
            target = int(round((new_angle % 360) * Stepper.STEPS_PER_DEGREE))
            target %= Stepper.STEPS_PER_REV

            delta = (target - self.position) % Stepper.STEPS_PER_REV
            # delta is now in [0, 4096). If going forward would take more than
            # half a turn, going backward is shorter.
            if delta > Stepper.STEPS_PER_REV // 2:
                delta -= Stepper.STEPS_PER_REV
            await self._steps(abs(delta), self._sgn(delta))

    # --- Public API ----------------------------------------------------------
    #
    # These are ordinary (non-async) methods that return IMMEDIATELY, exactly
    # like the Pi version's Process-spawning methods. The move itself runs as a
    # background Task. Issue several in a row and they queue up on the lock and
    # execute in order.
    #
    # Each returns its Task, so you can `await` a specific move if you want to
    # know when that one finished.

    def rotate(self, delta):
        """Turn `delta` degrees from wherever the shaft is now."""
        return asyncio.create_task(self._rotate(delta))

    def go_angle(self, new_angle):
        """Turn to absolute angle `new_angle`, by the shortest path."""
        return asyncio.create_task(self._go_angle(new_angle))

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
        """Declare the current physical position to be 0 degrees."""
        self.position = 0

    def release(self):
        """
        De-energize this motor's coils. The motor loses holding torque (the
        shaft turns freely) but stops drawing ~200 mA and stops getting hot.
        Call this when a motor will sit idle for a while. Position tracking is
        unaffected -- but if something back-drives the shaft while released, our
        idea of the angle becomes a lie.

        Only this motor's four bits are cleared; the other motors on the chain
        keep holding whatever pattern they were on.
        """
        self._write(0)

    async def idle(self):
        """
        Wait until every move queued on this motor has finished.

        The sleep_ms(0) is not decoration. create_task() only QUEUES a task --
        it does not start it. If we grabbed the lock immediately we would find
        it unlocked (none of the queued moves has run far enough to take it)
        and return instantly, having waited for nothing. Yielding once lets
        every already-queued task run up to its first await, which puts them
        all on the lock's waiting list ahead of us. Because asyncio.Lock is
        FIFO, acquiring it then means everything ahead of us is done.
        """
        await asyncio.sleep_ms(0)
        async with self.lock:
            pass


# =============================================================================
# Example
# =============================================================================

async def main():

    # Declare the Shifter for use by all motors.
    s = Shifter(data=5, latch=6, clock=7)

    # Start the field numbering from scratch, so re-running this from the REPL
    # keeps giving m1 and m2 the same bits.
    Stepper.reset()

    # Declare a pair of Steppers.
    m1 = Stepper(s)
    m2 = Stepper(s)

    # Define current position as zero for both motors.
    m1.zero()
    m2.zero()

    # Queue up a sequence of movements
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

    # Nothing above has actually moved yet -- the tasks are queued, and they
    # only get to run once main() yields. Waiting on both motors does that.
    await m1.idle()
    await m2.idle()

    print("done: m1 at %.1f deg, m2 at %.1f deg" % (m1.angle, m2.angle))

    # Stop cooking the coils.
    m1.release()
    m2.release()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        # Reset the event loop, otherwise a soft reboot / re-run inherits the
        # old scheduler state and behaves strangely.
        asyncio.new_event_loop()
