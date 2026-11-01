'use strict';

// App-specific result override for dev.jim.envinspector 1.0.1.
// This changes reported findings, not the device's actual security state.
if (typeof Java === 'undefined') {
  throw new Error('Run this script with the jprobe CLI (Java bridge required).');
}

Java.perform(function () {
  const target = 'dev.jim.envinspector';
  const packageName = Java.use('android.app.ActivityThread').currentPackageName();
  if (packageName === null || packageName.toString() !== target) {
    throw new Error('This script only supports ' + target);
  }

  const Finding = Java.use(target + '.Finding');
  const State = Java.use(target + '.Finding$State');
  const ctor = Finding.$init.overload(
    'java.lang.String', 'java.lang.String', target + '.Finding$State',
    'java.lang.String', 'java.lang.String', 'long'
  );
  const counts = Object.create(null);
  let replaced = 0;

  ctor.implementation = function (category, title, state, evidence, limitation, timestamp) {
    if (state !== null && state.name().toString() === 'SIGNAL') {
      const name = title === null ? '(untitled)' : title.toString();
      counts[name] = (counts[name] || 0) + 1;
      replaced++;
      console.log('[envinspector] SIGNAL -> CLEAR: ' + name);
      return ctor.call(this, category, title, State.CLEAR.value,
        '未观察到匹配的特征。', limitation, timestamp);
    }
    return ctor.call(this, category, title, state, evidence, limitation, timestamp);
  };

  rpc.exports.envInspectorStatus = function () {
    return { target: target, installed: true, replaced: replaced, checks: counts };
  };
  console.log('[envinspector] Installed; SIGNAL only. LIMITED/ERROR/INFO preserved.');
});
