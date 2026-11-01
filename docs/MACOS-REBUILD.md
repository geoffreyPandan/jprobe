# macOS ARM64 jprobe 重建

仓库放在 `workspace/jprobe/`，上游源码放在 `workspace/upstream/`；以下命令从
`workspace/` 执行。最新完成的构建与实测结果见 [R7-VALIDATION.md](R7-VALIDATION.md)。
已交付候选保留正常单词 `Friday`；下面的严格零匹配门禁仍会在该项停止。
该门禁没有为本次源码归档而放宽，不能将它描述为一键产出已交付候选。

本流程构建独立 Mac Python 客户端和 CLI，不自动重建 SDK，不操作手机。
输出必须通过原生扩展及 wheel 内 `.so`、`.js` 的大小写无关 ASCII / UTF-16LE
`frida` 零命中检查；关键词检查不替代功能或手机检测验证。

## 前置条件

- Apple Silicon 原生 macOS Terminal、Xcode Command Line Tools、Python 3.13、Node/npm、Ninja。
- `prepare_macos_source.py` 已准备固定上游及 `go-rename/tsc`。
- 固定 Go 缓存 `go-download-cache/golang.org/toolchain@v0.0.1-go1.26.0.darwin-arm64` 存在。
- 已审计的 GLib、tinycc、V8 安装在 `upstream/deps/sdk-macos-arm64`，其 `VERSION.txt` 与 releng 匹配。
- SDK 安装者已创建 `upstream/deps/sdk-macos-arm64/JPROBE-SDK-AUDIT.json`，仅在实际审计通过后设置 `auditPassed: true`。

Marker 格式：

```json
{
  "schemaVersion": 1,
  "host": "macos-arm64",
  "auditPassed": true,
  "libraries": {
    "lib/libglib-2.0.a": "实际文件的64位小写SHA256",
    "lib/libgobject-2.0.a": "实际文件的64位小写SHA256",
    "lib/libgio-2.0.a": "实际文件的64位小写SHA256",
    "lib/libtcc.a": "实际文件的64位小写SHA256",
    "lib/libv8-15.7.a": "实际文件的64位小写SHA256"
  }
}
```

Hash 占位必须替换为真实值；全部 `lib/libv8-*.a` 必须覆盖。可添加源码提交、审计报告等字段。
此 marker 范围仅为列出的修正依赖，不代表 SDK 所有文件或最终程序均零命中。
构建前、配置后验证 marker 与 archive hash，最终扩展及 wheel 另有强制门禁。

## 使用

从工作区根目录全新构建：

```sh
bash jprobe/scripts/build_macos.sh
```

对同一源码和已配置目录显式增量重建：

```sh
bash jprobe/scripts/build_macos.sh --reuse-build
```

增量模式通过 Python `releng.meson_configure.configure()` API 重新配置，追加
`--reconfigure --clearcache`，核对实际选项及生成的 Go 环境，适用于替换已审计 SDK 后重新链接。
默认模式拒绝已有构建配置；两种模式都拒绝覆盖非空 `dist/macos-clean`，须先显式归档旧发布。
不完整但非空的构建目录须先检查并保留或移走，脚本不自动删除。

可选接口：`build_macos.sh [--reuse-build] /absolute/path/upstream /absolute/path/workspace`。
`upstream` 必须直接位于 workspace 内。不要并发打包同一 checkout。

## 构建设置

| 用途 | 路径或设置 |
|---|---|
| 构建 | `build-macos-clean` |
| Python 3.13 | `venv-macos-clean` |
| Go 工具链副本 | `toolchains/go1.26-jprobe` |
| Go 编译/模块缓存 | `go-build-cache-clean` / `go-download-cache` |
| 发布 | `dist/macos-clean` |
| 暂存与失败证据 | `.macos-package-staging/package-*` |
| 日志 | `logs/macos-clean.*/build.log` |
| 版本 | jprobe 17.25.0 / tools 14.11.0+jprobe |
| 签名 | `MACOS_CERTID=-` 默认 ad-hoc，可显式提供 identity |
| Go | `GOROOT` 指向副本，`GOTOOLCHAIN=local` |
| npm | 官方 registry，并写 compiler 私有目录 `.npmrc` |

脚本调用幂等源码修正及固定 Go 副本准备，`-j4` 编译。
Python/tools 启用，server/gadget/inject 禁用，`frida-core:compat=disabled`。
因此不包含 arm64e 兼容 agent/helper。Python 构建工具固定为 pip 26.2.2、setuptools 84.2.1、
wheel 0.48.0、packaging 26.3。

## 打包及验收

原生扩展复制到新暂存目录，再执行 `sanitize_macos_extension.py --require-zero`；
仅剥离非全局符号、删除已证明无用途的旧 RPATH、重新签名，不进行运行时字符串的二进制替换。
wheel 中的扩展必须与已审计副本完全一致。

工具打包临时切换 `frida-tools/build` 链接，正常结束或可捕获异常后恢复。
只接受本 workspace 的 `build-macos-client` / `build-macos-clean` 下工具目录，拒绝真实目录或其他链接。
不可捕获的强制终止后，依据暂存的 `tools-link-state.json` 核对并恢复链接，
确认没有其他打包进程后处理 lock 文件。

两个 wheel 的 `.so`、`.js` 全部零命中后才发布，并附带 `native-audit.json`、
`wheel-audit.json`、`SDK-AUDIT.json`、`SHA256SUMS.txt`。失败暂存保留。
脚本不自动安装 wheel 或启动手机测试；发布后安装两个 wheel，执行 `pip check`、导入、
进程枚举、TypeScript/RPC/Java 桥接检查，再单独进行胖狗冷启动测试。
