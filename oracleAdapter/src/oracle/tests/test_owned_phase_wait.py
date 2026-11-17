import signal
import subprocess
import os
import sys
import time
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from oracle.research.full_run import IntegrityStop, wait_for_phase_exit


class OwnedPhaseWait(unittest.TestCase):
    @unittest.skipUnless(os.name=='posix' and Path('/proc').exists(),'Linux process identity integration')
    def test_real_child_handle_is_reaped_without_receipt_based_early_release(self):
        p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(.1)'])
        try:
            fields=Path(f'/proc/{p.pid}/stat').read_text().rsplit(')',1)[1].split()
            with patch.object(p,'wait',wraps=p.wait) as wait:
                wait_for_phase_exit({'pid':p.pid,'start_ticks':fields[19]},p,time.monotonic(),5)
            self.assertEqual(p.returncode,0)
            self.assertTrue(any(call.kwargs.get('timeout') is not None for call in wait.call_args_list))
        finally:
            if p.poll() is None:p.terminate()
            p.wait()

    def process(self):
        p=Mock();p.pid=42;p.poll.return_value=0;p.wait.return_value=0
        return p

    def test_fast_owned_exit_does_not_pay_fixed_poll_sleep(self):
        p=self.process()
        with patch('oracle.research.full_run.live',side_effect=[True,False]), \
             patch('oracle.research.full_run.time.monotonic',return_value=1.), \
             patch('oracle.research.full_run.time.sleep') as sleep:
            wait_for_phase_exit({'pid':42,'start_ticks':'7'},p,0.,900)
        self.assertEqual(p.wait.call_args_list[0].kwargs,{'timeout':2.})
        sleep.assert_not_called()

    def test_wait_timeout_is_not_worker_failure_or_restart(self):
        p=self.process();p.wait.side_effect=[subprocess.TimeoutExpired('worker',2),0,0]
        with patch('oracle.research.full_run.live',side_effect=[True,True,False]), \
             patch('oracle.research.full_run.time.monotonic',return_value=1.), \
             patch('oracle.research.full_run.signal_owned') as kill:
            wait_for_phase_exit({'pid':42,'start_ticks':'7'},p,0.,900)
        kill.assert_not_called()
        self.assertEqual(p.wait.call_count,3)

    def test_start_receipt_cannot_name_a_different_owned_pid(self):
        p=self.process()
        with self.assertRaises(IntegrityStop):
            wait_for_phase_exit({'pid':43,'start_ticks':'7'},p,0.,900)
        p.wait.assert_not_called()

    def test_live_process_with_mismatched_start_ticks_is_not_silently_reaped(self):
        p=self.process();p.poll.return_value=None
        with patch('oracle.research.full_run.live',return_value=False), \
             patch('oracle.research.full_run.signal_owned') as kill:
            with self.assertRaises(IntegrityStop):
                wait_for_phase_exit({'pid':42,'start_ticks':'old'},p,0.,900)
        kill.assert_not_called();p.wait.assert_not_called()

    def test_existing_phase_without_popen_keeps_identity_polling(self):
        with patch('oracle.research.full_run.live',side_effect=[True,False]), \
             patch('oracle.research.full_run.time.monotonic',return_value=1.), \
             patch('oracle.research.full_run.time.sleep') as sleep:
            wait_for_phase_exit({'pid':42,'start_ticks':'7'},None,0.,900)
        sleep.assert_called_once_with(2.)

    def test_existing_timeout_escalation_preserves_owned_signal_checks(self):
        p=self.process()
        with patch('oracle.research.full_run.live',side_effect=[True,True,False]), \
             patch('oracle.research.full_run.time.monotonic',return_value=1000.), \
             patch('oracle.research.full_run.time.sleep'), \
             patch('oracle.research.full_run.signal.SIGKILL',9,create=True), \
             patch('oracle.research.full_run.signal_owned') as kill:
            identity={'pid':42,'start_ticks':'7'}
            wait_for_phase_exit(identity,p,0.,900)
        self.assertEqual(kill.call_args_list[0].args,(identity,signal.SIGTERM))
        self.assertEqual(kill.call_args_list[1].args,(identity,9))
