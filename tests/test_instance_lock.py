"""Lock de instância única."""
# pylint: disable=missing-class-docstring,missing-function-docstring
import unittest

from instance_lock import AlreadyRunningError, InstanceLock
from tests.support import temporary_dir


class InstanceLockTest(unittest.TestCase):
    def setUp(self):
        self.path = temporary_dir(self) / "service.lock"

    def test_second_instance_is_refused_until_the_first_releases(self):
        first, second = InstanceLock(self.path), InstanceLock(self.path)
        first.acquire()
        self.addCleanup(first.release)
        with self.assertRaisesRegex(AlreadyRunningError, "Outra instância"):
            second.acquire()
        first.release()
        second.acquire()
        second.release()

    def test_release_without_acquire_and_twice_is_harmless(self):
        lock = InstanceLock(self.path)
        lock.release()
        lock.acquire()
        lock.release()
        lock.release()


if __name__ == "__main__":
    unittest.main()
