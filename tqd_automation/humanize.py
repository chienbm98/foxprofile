import random
import time


def pause(low: float = 0.8, high: float = 2.5) -> None:
    """Wait a human-looking moment between page actions."""
    time.sleep(random.uniform(low, high))
