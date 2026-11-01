'use strict';
// MobiKwik 23.75.1 / 2290 ARM64 lab startup override. Requires jprobe R8.
// Intentionally changes this app's environment detector responses. No APK,
// global device settings, certificates, account or payment data are changed.
if (Process.arch !== 'arm64') throw new Error('Unsupported architecture');
let startupVerified = null;
function verifyStartupModule(m) {
  if (startupVerified !== null && startupVerified.equals(m.base)) return;
  const startupCmdBytes = new Uint8Array(File.readAllBytes('/proc/self/cmdline'));
  let startupCmd = '';
  for (const b of startupCmdBytes) { if (b === 0) break; startupCmd += String.fromCharCode(b); }
  if (startupCmd !== 'com.mobikwik_new' || Process.arch !== 'arm64') throw new Error('Unsupported process or architecture');
  const bytes = Array.from(new Uint8Array(m.base.add(0x36c750).readByteArray(32))).map(b => b.toString(16).padStart(2, '0')).join('');
  if (bytes !== 'ffc304d1fd7b0da9fc6f0ea9fa670fa9f85f10a9f65711a9f44f12a9fd430391') throw new Error('Unsupported libloader.so policy resolver');
  startupVerified = m.base;
}
const startupPolicyOriginals = new Map();
function setStartupPolicy(slot, value) {
  const key = slot.toString();
  if (!startupPolicyOriginals.has(key)) startupPolicyOriginals.set(key, {original:slot.readU8(), value:value});
  slot.writeU8(value);
}
function restoreStartupPolicies() {
  for (const [address, saved] of startupPolicyOriginals) {
    try { const slot=ptr(address); if (slot.readU8() === saved.value) slot.writeU8(saved.original); } catch (_) {}
  }
}
const startupPolicyLife = {};
Script.bindWeak(startupPolicyLife, restoreStartupPolicies);
const bootProperty = Module.getGlobalExportByName('__system_property_get');
Interceptor.attach(bootProperty, {
  onEnter(args) {
    this.bootMatch = false;
    try {
      if (args[0].readCString() !== 'ro.boot.verifiedbootstate') return;
      this.bootMatch = true;
      this.bootBuffer = args[1];
      this.bootCaller = this.returnAddress;
    } catch (_) {}
  },
  onLeave(result) {
    if (!this.bootMatch) return;
    const m = Process.findModuleByName('libloader.so');
    const caller = Process.findModuleByAddress(this.bootCaller);
    if (m === null || caller === null || caller.name !== 'libloader.so' ||
        this.bootCaller.sub(m.base).toString() !== '0x26449c') return;
    const row = {property:this.bootBuffer.readCString(),caller:caller === null ? '<anonymous>' : caller.name+'+'+this.bootCaller.sub(caller.base)};
    if (m !== null) {
      verifyStartupModule(m);
      const resolve = new NativeFunction(m.base.add(0x36c750), 'void', ['pointer','pointer']);
      const event = Memory.alloc(0xc0);
      resolve(Memory.allocUtf8String('51dd4a4bd1ebc4ed'), event);
      const ctx = event.add(0x90).readPointer();
      const tpl = event.add(0x98).readPointer();
      if (!ctx.isNull() && !tpl.isNull() && ctx.add(0x778).readCString() === 'Zygisk Detected by App') {
        const flags = tpl.add(0xe10).readU8();
        if ((flags & 2) !== 0) {
          setStartupPolicy(tpl.add(0xe10), flags & ~2);
          console.log('[ROOT-NATIVE-POLICY] Cleared native termination flag for Zygisk response; before=' + flags);
        }
      }
      row.attestationVersion=m.base.add(0x73da38).readU32();
      row.deviceLocked=m.base.add(0x73da3c).readU32();
      row.verifiedBootState=m.base.add(0x73da40).readU32();
    }
    if (m !== null && caller !== null && caller.name === 'libloader.so' &&
        this.bootCaller.sub(m.base).toString() === '0x26449c' &&
        row.property === 'green' && row.attestationVersion === 300 &&
        row.deviceLocked === 0 && row.verifiedBootState === 2) {
      this.bootBuffer.writeUtf8String('orange');
      result.replace(6);
      row.correctedProperty = 'orange';
      const bootPolicy = m.base.add(0x7e9f90);
      row.previousUnverifiedBootPolicy = bootPolicy.readU8();
      setStartupPolicy(bootPolicy, 1);
      row.allowUnverifiedBootInDetector = true;
    }
    console.log('[BOOT-CONSISTENCY] ' + JSON.stringify(row));
  }
});
console.log('[BOOT-CONSISTENCY] Scoped property consistency correction enabled');


console.log('[EARLY] pid=' + Process.id);
let earlyInstalled = false;
const earlyLifetimes = [];
const earlyObserver = Process.attachModuleObserver({ onAdded(m) {
  if (m.name !== 'libloader.so' || earlyInstalled) return;
  verifyStartupModule(m);
  earlyInstalled = true;

// Compatibility experiment for MobiKwik 23.75.1 / 2290, arm64.
// This block overrides only the BTL method-hook classification.
// It leaves keystore methods and certificate bytes unchanged.
const customCmdBytes = new Uint8Array(File.readAllBytes('/proc/self/cmdline'));
let customCmd = '';
for (const b of customCmdBytes) { if (b === 0) break; customCmd += String.fromCharCode(b); }
if (customCmd !== 'com.mobikwik_new') throw new Error('Unsupported process');
const customRomModule = Process.getModuleByName('libloader.so');
const customRomPrefix = Array.from(new Uint8Array(customRomModule.base.add(0x295780).readByteArray(32)))
  .map(b => b.toString(16).padStart(2, '0')).join('');
if (customRomPrefix !== 'fd7bbda9f50b00f9f44f02a9fd030091ff4300d155d03bd5a81640f9e92400d0')
  throw new Error('Unsupported libloader.so; expected verified 23.75.1 callback');
const customRomCategory = Memory.allocUtf8String('jprobe-lab');
const customRomReplaced = new Map();
const customRomStats = { overriddenRecords: 0, tables: 0 };
let customRomTable = ptr(0);
function customRomApply() {
  const count = customRomModule.base.add(0x7eee38).readU32();
  const table = customRomModule.base.add(0x7eee40).readPointer();
  if (table.isNull() || count === 0) return;
  if (count > 300) throw new Error('Unexpected method record count');
  if (!table.equals(customRomTable)) { customRomTable = table; customRomStats.tables++; }
  for (let i = 0; i < count; i++) {
    const record = table.add(i * 0x50);
    const slot = record.add(0x28);
    const category = slot.readPointer();
    if (category.equals(customRomCategory)) continue;
    if (category.isNull() || category.readCString() !== 'BTL') continue;
    const klass = record.readPointer().readCString();
    if (!/^(java\/security\/|android\/security\/)/.test(klass))
      throw new Error('Unexpected BTL class: ' + klass);
    customRomReplaced.set(slot.toString(), category);
    slot.writePointer(customRomCategory);
    customRomStats.overriddenRecords++;
    console.log('[CUSTOM-ROM] Override BTL classification: ' + klass + '.' + record.add(0x10).readPointer().readCString());
  }
}
function customRomRestore() {
  for (const [address, original] of customRomReplaced) {
    try {
      const slot = ptr(address);
      if (slot.readPointer().equals(customRomCategory)) slot.writePointer(original);
    } catch (_) { /* The process may already be shutting down. */ }
  }
}
customRomApply();
const customRomTimer = setInterval(customRomApply, 100);
const customRomLife = {};
earlyLifetimes.push(customRomLife);
Script.bindWeak(customRomLife, customRomRestore);
rpc.exports.customRomStatus = function () { return customRomStats; };
rpc.exports.customRomRestore = function () { clearInterval(customRomTimer); customRomRestore(); };
console.log('[CUSTOM-ROM] Native BTL classification override installed; no Java method hooks');

  console.log('[EARLY] Custom ROM override installed');
}});
function installRootResponse() { Java.perform(function () {
  const target = 'com.mobikwik_new';
  const AT = Java.use('android.app.ActivityThread');
  const app = AT.currentApplication();
  if (app === null) { setTimeout(installRootResponse, 100); return; }
  if (app.getPackageName().toString() !== target) {
    throw new Error('This script only supports ' + target);
  }
  const info = app.getPackageManager().getPackageInfo(target, 0);
  if (info.versionCode.value !== 2290 || info.versionName.value.toString() !== '23.75.1') {
    throw new Error('Unsupported MobiKwik version; expected 23.75.1 / 2290');
  }

  const RootChecker = Java.use('com.mobikwik_new.utils.RootChecker');
  RootChecker.isRooted.overload('android.content.Context', 'com.mobikwik_new.utils.RootCheckListener').implementation = function (context, listener) {
    console.log('[APP-ROOT] Applied unrooted startup callback for this app only');
    if (listener !== null) listener.setDeviceUnrooted();
  };
  const Popup = Java.use('pxSVj3.jZ6bM1.yzOdS4');
  const Message = Java.use('pxSVj3.jZ6bM1.yzOdS4$pYxHn4');
  const Exit = Java.use('pxSVj3.i8rgh8.jx5ed4');
  const stats = { suppressedMessages: 0, suppressedQueuedExits: 0, reasons: {} };
  const allowedReasons = new Set([
    "Zygisk Detected by App"
  ]);

  function isEnvironmentFailure(shortMessage) {
    return shortMessage !== null && allowedReasons.has(String(shortMessage));
  }
  function pendingEnvironmentFailure() {
    const raw = Popup.UserIndicationPopup_private_static_persistentMessage.value;
    return raw !== null && isEnvironmentFailure(Java.cast(raw, Message).UserIndicationPopup_MessageOutput_shortMsg.value);
  }
  function clearEnvironmentToast() {
    if (!pendingEnvironmentFailure()) return;
    const stack = Popup.UserIndicationPopup_private_static_toastStack.value;
    while (!stack.isEmpty()) {
      const toast = stack.pop();
      if (toast !== null) Java.cast(toast, Java.use('android.widget.Toast')).cancel();
    }
    Popup.UserIndicationPopup_private_static_isExitingAfterToast.value = false;
    Popup.UserIndicationPopup_private_static_isWaitingForToastCallback.value = false;
  }

  const indication = Popup.nXj2T0.overload(
    'java.lang.String', 'java.lang.String', 'boolean', 'boolean',
    'java.lang.String', 'java.lang.String'
  );
  indication.implementation = function (message, shortMessage, shouldExit, restart, suffix, extra) {
    if (isEnvironmentFailure(shortMessage)) {
      stats.suppressedMessages++;
      const reason = String(shortMessage);
      stats.reasons[reason] = (stats.reasons[reason] || 0) + 1;
      console.log('[mobikwik] Suppressed environment indication: ' + reason + '; shouldExit=' + shouldExit);
      return;
    }
    console.log('[mobikwik] Other indication retained: ' + shortMessage);
    return indication.call(this, message, shortMessage, shouldExit, restart, suffix, extra);
  };
  const queuedExit = Exit.cmFpY4.overload('android.content.Context', 'java.lang.Boolean');
  queuedExit.implementation = function (context, restart) {
    if (pendingEnvironmentFailure()) {
      stats.suppressedQueuedExits++;
      clearEnvironmentToast();
      console.log('[mobikwik] Suppressed queued environment exit');
      return;
    }
    return queuedExit.call(this, context, restart);
  };

  Java.scheduleOnMainThread(clearEnvironmentToast);
  rpc.exports.mobikwikStatus = function () { return stats; };
  console.log('[mobikwik] Installed for 23.75.1 / 2290, pid=' + Process.id);
}); }
installRootResponse();
