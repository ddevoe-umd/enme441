# =============================================================================
# Stepper class
# ESP32-C3 using asyncio
# =============================================================================
#
# WHY asyncio AND NOT _thread
# ---------------------------
#
# 1. The ESP32-C3 is a SINGLE-CORE RISC-V chip. (Some other ESP32s are
#    dual-core; the C3 is not.) _thread therefore buys exactly zero
#    parallelism since two threads share one core, taking turns under the
#    GIL. You pay all the cost of threads and get none of the benefit.
#
# 2. Step timing here is open-loop: we write 4 pins, wait a fixed interval,
#    write again. A preemptive thread switch can land anywhere, including 
#    in the middle of that interval. On a 28BYJ-48 that can result in
#    missed steps. asyncio is COOPERATIVE: a task only ever yields at 
#    an explicit `await`, so we control where the switches happen 
#    (at sleep points between steps).
#
# 3. MicroPython's _thread is deliberately minimal: fixed pre-allocated stacks,
#    no join(), no thread pool. The original Pi code spawns one process per
#    move command; the thread equivalent would spawn one thread per move and
#    run the C3 out of RAM in short order. asyncio Tasks are cheap by
#    comparison, so we can keep that same fire-and-forget API.
#
# ---------------------------------------
# MicroPython's asyncio scheduler is MILLISECOND-granular. There is
# asyncio.sleep_ms(), but no asyncio.sleep_us(). This limits timing 
# resolution and mininmum step period. Furthermore, the true step period
# creeps upward as motors are added.
#
# If you need a constant step rate that does not degrade as you add
# motors, see stepper_timer.py, which drives the steps from a
# hardware timer and uses asyncio only to sequence the moves.
# =============================================================================

import asyncio
from machine import Pin

class Stepper:

    SEQ = [0b0001, 0b0011, 0b0010, 0b0110,
           0b0100, 0b1100, 0b1000, 0b1001]

    # 28BYJ-48: 8 half-steps per internal motor cycle * 64:1 gearbox
    # = 512 cycles * 8 = 4096 half-steps per revolution of the OUTPUT shaft.
    STEPS_PER_REV = 4096
    STEPS_PER_DEGREE = STEPS_PER_REV / 360

    def __init__(self, pins, delay_ms=2):
        """
        pins     -- 4 GPIO pins wired to IN1..IN4 on the ULN2003 board.
        delay_ms -- delay between half-steps. 2 ms is about as fast as
                    asyncio's millisecond scheduler can usefully go; 1 ms
                    may outrun a 28BYJ-48's torque. Try both:
                    2 ms/half-step * 4096 half-steps/rev = 8.192 s/rev
                    1 ms/half-step * 4096 half-steps/rev = 4.096 s/rev
        """

        self.pins = [Pin(p, Pin.OUT) for p in pins]

        self.delay_ms = delay_ms
        self.position = 0       # absolute position in half-steps, [0, 4096)
        self.seq_state = 0      # where we are in SEQ, 0..7

        self.lock = asyncio.Lock()   # One lock per motor

    # --- Internal methods ------------------------------------------------

    @staticmethod
    # The @staticmethod decorator defines a class method that does not receive 
    # an implicit first argument (self). It acts a regular function but lives 
    # inside the class's namespace for logical organization.
    def _sgn(x):
        """Signum function: -1, 0, or +1."""
        if x == 0:
            return 0
        return int(abs(x) / x)

    def _step(self, direction):
        """
        Advance ONE half-step. Pure computation and pin writes -- no awaits,
        so this is atomic with respect to other asyncio tasks
        """
        pattern = Stepper.SEQ[self.seq_state]

        for i in range(4):
            self.pins[i].value(pattern & (1 << i))

        # Advance our position in the sequence, wrapping in [0, 7].
        # Python's % returns a non-negative result even for negative operands,
        # so (0 - 1) % 8 == 7 and reverse motion wraps correctly.
        self.seq_state = (self.seq_state + direction) % 8

        # Update the tracked position. All asyncio tasks share this object.
        #
        # Track POSITION (an exact integer count of half-steps), not the angle.
        # Adding a fractional degree per step would accumulate floating-point
        # error over thousands of steps; counting steps cannot drift. The angle
        # in degrees is derived from this count on demand.
        self.position = (self.position + direction) % Stepper.STEPS_PER_REV

    async def _steps(self, num_steps, direction):
        """Take num_steps half-steps, yielding to other tasks between each."""
        for _ in range(num_steps):
            self._step(direction)
            # THE yield point. While this task is parked here, every other
            # motor's task gets to run. This one line is what makes N motors
            # move at once on a single core.
            await asyncio.sleep_ms(self.delay_ms)

    async def _rotate(self, delta):
        """Relative move, degrees. Positive and negative both allowed."""
        async with self.lock:            # wait for any move already in flight
            num_steps = int(round(Stepper.STEPS_PER_DEGREE * abs(delta)))
            await self._steps(num_steps, self._sgn(delta))

    async def _go_angle(self, new_angle):
        """ Absolute move, degrees, taking the shortest path."""
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
    # These are ordinary (non-async) methods that return IMMEDIATELY. 
    # The move itself runs as a background Task. Issue several in a row 
    # and they queue up on the lock and execute in order.
    #
    # Each returns its Task, so you can `await` a specific move if you want to
    # know when that move has finished.

    def rotate(self, delta):
        """Turn `delta` degrees from wherever the shaft is now."""
        return asyncio.create_task(self._rotate(delta))

    def go_angle(self, new_angle):
        """Turn to absolute angle `new_angle`, by the shortest path."""
        return asyncio.create_task(self._go_angle(new_angle))

    @property
    # The @property decorator transforms a class method into a 
    # read-only "getter" attribute, allowing you to access it using 
    # standard dot notation (obj.attribute) without parentheses. 
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
        De-energize all coils. The motor loses holding torque (the shaft turns
        freely) but stops drawing ~200 mA and stops getting hot. Call this when
        a motor will sit idle for a while.
        """
        for p in self.pins:
            p.value(0)

    async def idle(self):
        """
        Wait until every move queued on this motor has finished.

        The sleep_ms(0) is not decoration. create_task() only QUEUES a task --
        it does not start it. If we grabbed the lock immediately we would find
        it unlocked (none of the queued moves have run far enough to take it)
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

    # ESP32-C3 GPIO notes -- not every pin is free:
    #   GPIO 11-17 : internal SPI flash. Never use.
    #   GPIO 18,19 : USB D-/D+ (the USB-serial-JTAG console on most C3 boards).
    #   GPIO 20,21 : UART0 TX/RX (the serial console on boards without USB).
    #   GPIO 2,8,9 : strapping pins, sampled at boot. Usable, but a load on
    #                them can stop the board from booting.
    # The sets below stay clear of all of that.
    m1 = Stepper([3, 4, 5, 6])
    m2 = Stepper([7, 10, 0, 1])

    # Define "here" as zero for both motors.
    m1.zero()
    m2.zero()

    # Queue up a routine. These calls all return instantly; each motor works
    # through its own list in order, and the two motors run side by side.
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

    # The above statements only queue the tasks. They only run
    # once main() yields. Waiting on both motors does that.
    await m1.idle()
    await m2.idle()

    # Note: idle() isn't needed to make the motors run; they will run 
    # as soon as main() reaches *any* await. It's needed to force 
    # main() to wait for the already-queued movements to complete.
    #
    # Each motor has its own asyncio.Lock, held for the duration of one 
    # move (async with self.lock in _rotate/_go_angle) and released when 
    # that move completes. Since the lock is FIFO, if idle() can acquire 
    # it, every move that was queued before idle() was called has already 
    # run to completion. So idle() acquires the lock, does nothing (pass), 
    # and immediately releases it.  The act of successfully acquiring is 
    # the signal, not the "doing" part.
    #
    # When the first await statment for m1 runs, main() pauses and ALL queued
    # tasks for both m1 and m2 are executed through the event loop 
    # scheduler. By the time the second await statement for m2 is run,
    # which only occurs once m1.idle() returns, most or all of the m2 
    # movement tasks are likely also already done.

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
