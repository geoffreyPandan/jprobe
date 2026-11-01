'use strict';

// Compatibility experiment for MobiKwik 23.75.1 / 2290, arm64.
// Overrides only its BTL method-hook classification. It does not change
// certificates, keystore methods, system properties, or hardware attestation.
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
Script.bindWeak(customRomLife, customRomRestore);
rpc.exports.customRomStatus = function () { return customRomStats; };
rpc.exports.customRomRestore = function () { clearInterval(customRomTimer); customRomRestore(); };
console.log('[CUSTOM-ROM] Native BTL classification override installed; no Java method hooks');
