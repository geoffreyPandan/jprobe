"""Negative tests: the harness must not turn missing evidence into success."""
import contextlib,io,json,subprocess,sys,tempfile,unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from run import Runner,command
from integrations import detector_result
from resources import listening_inodes,owns_listener,stop_owned,verify_heartbeat_time
class HarnessTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.r=Runner.__new__(Runner)
  self.r.out=Path(self.tmp.name);self.r.results=[]
  self.r.a=SimpleNamespace(variant='r8',runtime='qjs',suite='selftest',serial='fixture')
 def tearDown(self):self.tmp.cleanup()
 def test_mismatch_is_failure(self):
  with contextlib.redirect_stdout(io.StringIO()):ok=self.r.case('wrong',lambda:self.r.expect(41,42))
  self.assertFalse(ok);data=json.loads((self.r.out/'results.json').read_text());self.assertEqual(data['counts']['FAIL'],1)
  self.assertIn('<failure ',(self.r.out/'junit.xml').read_text())
 def test_exception_is_not_success(self):
  with contextlib.redirect_stdout(io.StringIO()):ok=self.r.case('absent',lambda: (_ for _ in ()).throw(RuntimeError('missing result')))
  self.assertFalse(ok)
 def test_blocked_is_separate(self):
  self.r.blocked('arm32','ABI unavailable');data=json.loads((self.r.out/'results.json').read_text());self.assertEqual(data['counts']['PASS'],0);self.assertEqual(data['counts']['BLOCKED'],1)
 def test_process_failure(self):
  with self.assertRaises(RuntimeError):command([sys.executable,'-c','raise SystemExit(7)'])
 def test_process_timeout(self):
  with self.assertRaises(subprocess.TimeoutExpired):command([sys.executable,'-c','import time;time.sleep(30)'],timeout=.1)
 def test_restarted_target_cannot_pass(self):
  self.r.pid=123;answers=iter(['123','Broadcast completed: JAVA=42;NATIVE=42;TOTAL=42;UID=10049','456'])
  self.r.shell=lambda *args,**kwargs:next(answers)
  with self.assertRaises(AssertionError):self.r.independent()
 def test_detection_dialog_overrides_stale_negative(self):
  tree=ET.fromstring('<hierarchy><node text="检测结果：未检出"/><node text="已被 Frida 检测"/></hierarchy>')
  self.assertTrue(detector_result(tree)['detected'])
 def test_detection_instructions_are_not_a_verdict(self):
  tree=ET.fromstring('<hierarchy><node text="运行检测，以检查是否检测到 Frida"/></hierarchy>')
  with self.assertRaises(AssertionError):detector_result(tree)
 def test_detection_negative_and_unknown(self):
  self.assertFalse(detector_result(ET.fromstring('<hierarchy><node text="检测结果：未检出"/></hierarchy>'))['detected'])
  with self.assertRaises(AssertionError):detector_result(ET.fromstring('<hierarchy><node text="检测结果：运行中"/></hierarchy>'))
 def test_socket_inode_ownership_without_ss_pid(self):
  table='0: 0100007F:8926 00000000:0000 0A 00000000:00000000 00:00000000 00000000 0 0 991 1\n'
  self.assertEqual(listening_inodes(table,35110),{'991'})
  self.assertTrue(owns_listener(table,'socket:[991]',35110))
  self.assertFalse(owns_listener(table,'socket:[992]',35110))
  self.assertFalse(owns_listener(table.replace(' 0A ',' 01 '),'socket:[991]',35110))
 def test_cleanup_never_signals_unrelated_pid(self):
  commands=[]
  def shell(s,**kw):commands.append(s);return '/system/bin/unrelated'
  stop_owned(shell,123,'/data/local/tmp/unique/server')
  self.assertFalse(any('kill ' in s for s in commands))
 def test_cleanup_accepts_deleted_owned_executable(self):
  commands=[]
  def shell(s,**kw):
   commands.append(s)
   return '/data/local/tmp/unique/server (deleted)' if len(commands)==1 else ''
  stop_owned(shell,123,'/data/local/tmp/unique/server')
  self.assertTrue(any('kill -TERM 123' in s for s in commands))
 def test_heartbeat_uses_device_clock(self):
  self.assertAlmostEqual(verify_heartbeat_time(1000500,1001),.5)
  self.assertAlmostEqual(verify_heartbeat_time(1000500,1000),-.5)
 def test_stale_or_future_heartbeat_fails(self):
  for timestamp in (980000,1002000):
   with self.assertRaises(AssertionError):verify_heartbeat_time(timestamp,1000)
if __name__=='__main__':unittest.main()
