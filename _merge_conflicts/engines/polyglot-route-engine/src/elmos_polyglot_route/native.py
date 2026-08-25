from __future__ import annotations

import atexit
import base64
import binascii
import fcntl
import hashlib
import json
import os
import pwd
import re
import shutil
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

from .clang_analyzer import analyze_clang, inventory_clang_module
from .emitter import _CPP_HELPERS, _OBJC_HELPERS, _PHP_HELPERS, _SWIFT_HELPERS
from .models import ROUTED_LANGUAGES, Language, RouteError, SemanticIR
from .python_analyzer import analyze_python
from .repository import javascript_esm_descriptor
from .toolchains import (
    ExactToolchain,
    exact_toolchain,
    sanitized_subprocess_env,
    typescript_parser_receipt,
    verify_csharp_toolchain,
)

ENGINE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = ENGINE_ROOT.parents[1]

# These native frontends can re-lift emitted target source even though they
# are not part of the older ROUTED_LANGUAGES evidence inventory.  Relift
# capability is deliberately named separately from route certification.
NATIVE_RELIFTABLE_LANGUAGES = frozenset({"cpp", "objc", "swift", "php"})
MODULE_INVENTORY_KIND = "elmos.typed-pure-module-inventory"
MODULE_INVENTORY_PROFILE = "typed-pure-module-v1"
_JAVASCRIPT_ANALYZER = ENGINE_ROOT / "native" / "javascript" / "analyzer.mjs"
_JAVASCRIPT_ANALYZER_SHA256 = "22325ea068f0ae28d3602f452c3b6f27be0d1f332a1692655d8bcce986b9e5b0"
_JAVASCRIPT_ANALYZER_BYTES = 26_923
_JAVASCRIPT_TYPESCRIPT_ROOT = ENGINE_ROOT / "native" / "javascript" / "vendor" / "typescript-5.9.2"
_JAVASCRIPT_TYPESCRIPT_ROOT_MODE = 0o755
_JAVASCRIPT_TYPESCRIPT_ROOT_NLINK = 6
_JAVASCRIPT_TYPESCRIPT_ASSET_SPECS = (
    (
        "asset-manifest.json",
        931,
        "e42b0b7a74a8b6532fb3edc39135776b9ee81e93aea0157a5e0c1c80ac44b073",
    ),
    (
        "LICENSE.txt",
        9_197,
        "a7d00bfd54525bc694b6e32f64c7ebcf5e6b7ae3657be5cc12767bce74654a47",
    ),
    (
        "package.json",
        3_620,
        "5a0bb7f286c4b3f1413a42c05f902311b161f70e5f52d9da10490443bfd595a3",
    ),
    (
        "typescript.js",
        9_111_680,
        "e5f1f6b3e82228a89873cc7b941b2465185e839c0692860f83e3e63e53f94c2b",
    ),
)
_JAVASCRIPT_TYPESCRIPT_ASSET_MODE = 0o644
_JAVASCRIPT_TYPESCRIPT_MANIFEST_SHA256 = _JAVASCRIPT_TYPESCRIPT_ASSET_SPECS[0][2]
_JAVASCRIPT_TYPESCRIPT_SHA256 = _JAVASCRIPT_TYPESCRIPT_ASSET_SPECS[3][2]
_JAVASCRIPT_TYPESCRIPT_BYTES = _JAVASCRIPT_TYPESCRIPT_ASSET_SPECS[3][1]
_JAVASCRIPT_ANALYZER_MAX_SOURCE_BYTES = 2_000_000
_TYPESCRIPT_ANALYZER = ENGINE_ROOT / "native" / "typescript" / "analyzer.mjs"
_TYPESCRIPT_ANALYZER_SHA256 = "482d2875c625f21fa13e02741ea4350e5ad43f0a168257a7425a3df87dc7d1d2"
_TYPESCRIPT_ANALYZER_BYTES = 31_436
_TYPESCRIPT_ANALYZER_MAX_SOURCE_BYTES = 2_000_000
_PHP_ANALYZER = ENGINE_ROOT / "native" / "php" / "analyzer.php"
_PHP_ANALYZER_SHA256 = "8419309ee77f60b881bcad26da1f3ea139dac934cd76d4305d17b353bcf9a7ff"
_PHP_ANALYZER_BYTES = 44089
_PHP_ANALYZER_MAX_SOURCE_BYTES = 2_000_000
#: Every PHP invocation the engine makes. `-n` drops php.ini so the analyzer's
#: behaviour is the build's, not the machine's, and the four `-d` overrides pin
#: the settings that could otherwise change an *observed value* rather than a
#: diagnostic. Kept as one constant so the analyzer and the behaviour harness
#: cannot drift apart in how they configure the interpreter.
_PHP_INTERPRETER_FLAGS = (
    "-n",
    "-d",
    "error_reporting=E_ALL",
    "-d",
    "precision=17",
    "-d",
    "serialize_precision=-1",
    "-d",
    "opcache.enable_cli=0",
)
_SWIFT_ANALYZER_KIND = "elmos.swift-analyzer-build-receipt"
_SWIFT_SYNTAX_VERSION = "600.0.1"
_SWIFT_SYNTAX_REVISION = "0687f71944021d616d34d922343dcef086855920"
_SWIFT_SYNTAX_TREE_SHA256 = "b78ec1b227a6cbe43ca239585f66907e50485b9119f96b5461bfc888f0e5f45d"
_SWIFT_SYNTAX_TREE_FILE_COUNT = 753
_SWIFT_SYNTAX_TREE_BYTES = 8_866_479
_SWIFT_DEPENDENCY_IDENTITY = "swift-syntax"
_SWIFT_DEPENDENCY_CACHE_SCHEMA = "swift-dependencies-standalone-v2"
_SWIFT_DEPENDENCY_CACHE_KEY_SCHEMA = "standalone-v2"
_SWIFT_DEPENDENCY_CACHE_SEED = "verified-content-addressed-standalone-cache"
_SWIFT_DEPENDENCY_OBJECT_STORE_POLICY = "standalone-no-alternates-no-hardlinks-v2"
_SWIFT_DEPENDENCY_OBJECT_STORE_MANIFEST_SCHEMA = "swift-git-object-store-manifest-v1"
_SWIFT_DEPENDENCY_OBJECT_STORE_MAXIMUM_ENTRIES = 100_000
_SWIFT_DEPENDENCY_OBJECT_STORE_MAXIMUM_FILE_BYTES = 512 * 1024 * 1024
_SWIFT_DEPENDENCY_OBJECT_STORE_MAXIMUM_BYTES = 64 * 1024 * 1024
_SWIFT_ANALYZER_BINARY_MAX_BYTES = 100_000_000
_SWIFT_ANALYZER_COLD_BUILD_TIMEOUT_SECONDS = 3_600
_SWIFT_BUILD_TERMINATION_GRACE_SECONDS = 1.0
_SWIFT_BUILD_CLEANUP_TIMEOUT_SECONDS = 5.0
_SWIFT_BUILD_REAP_RESERVE_SECONDS = 0.5
_SWIFT_BUILD_FINAL_SIGNAL_RESERVE_SECONDS = 0.25
_SWIFT_BUILD_FINAL_VERIFICATION_RESERVE_SECONDS = 0.5
_SWIFT_BUILD_SESSION_POLL_SECONDS = 0.05
_SWIFT_BUILD_PROCESS_LIST_TIMEOUT_SECONDS = 1.0
_SWIFT_BUILD_POST_COMPLETION_TIMEOUT_SECONDS = 2.0
_SWIFT_BUILD_MAXIMUM_PROCESS_IDS = 32_768
_SWIFT_BUILD_MAXIMUM_PROCESS_LIST_BYTES = 512 * 1024
_SWIFT_BUILD_REQUIRED_EMPTY_SNAPSHOTS = 3
_PROCESS_LIST = Path("/bin/ps")
_LIBPROC = Path("/usr/lib/libproc.dylib")
_APPLE_GIT = Path("/Applications/Xcode.app/Contents/Developer/usr/bin/git")
_APPLE_GIT_VERSION = "git version 2.50.1 (Apple Git-155)"
_APPLE_GIT_SHA256 = "10f9c1df894525ae4c7454258febab6d3d25071062b42cb48dbb1842cdffd2a9"
_APPLE_GIT_BYTES = 3_704_880
_SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")
_SANDBOX_EXEC_SHA256 = "e3d7a792c58a5d3783d2f7274c82d70062393830d8cb1ded713ca554a470bd2f"
_SANDBOX_EXEC_CDHASH_FULL = "3fd94e400493dc8210fe815339088e83b0cdc18fc800c1352de86a7562e22ff5"
_SANDBOX_EXEC_BYTES = 102_368
_CODESIGN = Path("/usr/bin/codesign")
_CODESIGN_SHA256 = "6f92f630759f1a7f3faa0bebe1b27b3565a44d5d44c15cc4ddead6b3af373f40"
_CODESIGN_BYTES = 458_576
_SANDBOX_EXEC_POLICY = "(version 1)\n(allow default)\n(deny network*)\n"
_SANDBOX_NETWORK_PROBE_SOURCE = r"""#include <arpa/inet.h>
#include <errno.h>
#include <stdint.h>
#include <sys/socket.h>
#include <unistd.h>

int main(void) {
    const int descriptor = socket(AF_INET, SOCK_STREAM, 0);
    if (descriptor < 0) {
        return 2;
    }
    struct sockaddr_in address = {0};
    address.sin_family = AF_INET;
    address.sin_port = htons(9);
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    errno = 0;
    const int status = connect(
        descriptor,
        (const struct sockaddr *)&address,
        (socklen_t)sizeof(address)
    );
    const int error = errno;
    if (close(descriptor) != 0) {
        return 3;
    }
    if (status != -1 || error != EPERM) {
        return 4;
    }
    static const char result[] = "NETWORK_DENIED:1\n";
    const ssize_t written = write(STDOUT_FILENO, result, sizeof(result) - 1);
    if (written != (ssize_t)(sizeof(result) - 1)) {
        return 5;
    }
    return 0;
}
"""
_SANDBOX_NETWORK_PROBE_SOURCE_SHA256 = "8a82a5f438ec38c0e733881eb868d91a4fb82c3ce95c3d8f27507a720dee7c19"
_SANDBOX_NETWORK_PROBE_SOURCE_BYTES = 923
_SANDBOX_NETWORK_PROBE_BINARY_NAME = "ElmosNetworkDenyProbe"
_SANDBOX_NETWORK_PROBE_BINARY_SHA256 = "446fc22c935c695feeea983fe3dba5705b399d32c93c285d797b7d90d0bdcbb7"
_SANDBOX_NETWORK_PROBE_BINARY_BYTES = 33_784
_SANDBOX_NETWORK_PROBE_UUID = "3C8F074C-FA7E-3977-B467-A98D3FC2BE00"
_SANDBOX_NETWORK_PROBE_CDHASH_FULL = "5e87ec802f0589e8d88db8eed94de7f41f5c855110c202ec3959cb8cfb9d7dc4"
_SANDBOX_NETWORK_PROBE_LINKED_LIBRARIES = ("/usr/lib/libSystem.B.dylib",)
_SANDBOX_NETWORK_PROBE_BUILD_ARGV = (
    "<sandbox-exec>",
    "-p",
    "<deny-network-policy>",
    "<clang>",
    "-x",
    "c",
    "-std=c17",
    "-target",
    "arm64-apple-macosx26.0",
    "-Os",
    "-fno-ident",
    "-isysroot",
    "<swift-sdk>",
    "-Wl,-dead_strip",
    "-o",
    "<probe-output>",
    "-",
)
_SANDBOX_NETWORK_PROBE_BUILD_ENVIRONMENT = {
    "PATH": ("<swift-toolchain-bin>:<system-usr-bin>:<system-bin>:<system-usr-sbin>:<system-sbin>"),
    "HOME": "<isolated-home>",
    "TMPDIR": "<isolated-tmp>",
    "LANG": "C",
    "LC_ALL": "C",
    "TZ": "UTC",
    "NO_COLOR": "1",
    "CLICOLOR": "0",
    "SOURCE_DATE_EPOCH": "0",
    "ZERO_AR_DATE": "1",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "<null-device>",
    "GIT_TERMINAL_PROMPT": "0",
    "XDG_CACHE_HOME": "<isolated-home>/.cache",
    "PYTHONHASHSEED": "0",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONNOUSERSITE": "1",
    "SWIFT_DETERMINISTIC_HASHING": "1",
}
_XCODE_ROOT = Path("/Applications/Xcode.app/Contents")
_SWIFT_TOOLCHAIN_ROOT = _XCODE_ROOT / "Developer/Toolchains/XcodeDefault.xctoolchain"
_SWIFT_PLATFORM_ROOT = _XCODE_ROOT / "Developer/Platforms/MacOSX.platform/Developer"
_SWIFT_SDK_ROOT = _SWIFT_PLATFORM_ROOT / "SDKs/MacOSX26.5.sdk"
_SWIFT_SDK_RESOLVED_ROOT = _SWIFT_PLATFORM_ROOT / "SDKs/MacOSX.sdk"
_SWIFT_SHARED_FRAMEWORKS = _XCODE_ROOT / "SharedFrameworks"
_SWIFT_BUILD_CLOSURE_SCHEMA = "swiftpm-build-execution-closure-v1"
_SWIFT_BUILD_CLOSURE_SCOPE = "pinned-local-xcode-swiftpm-direct-components-and-critical-sdk-projection-v1"
_SWIFT_DETERMINISTIC_ENVIRONMENT = {
    "SOURCE_DATE_EPOCH": "0",
    "SWIFT_DETERMINISTIC_HASHING": "1",
    "ZERO_AR_DATE": "1",
}
_SWB_BUILD_SERVICE_RELATIVE = (
    "SwiftBuild.framework/Versions/A/PlugIns/SWBBuildService.bundle/Contents/Frameworks/"
    "SWBBuildService.framework/Versions/A/SWBBuildService"
)
_SWB_PROJECT_MODEL_RELATIVE = (
    "SwiftBuild.framework/Versions/A/PlugIns/SWBBuildService.bundle/Contents/Frameworks/"
    "SWBProjectModel.framework/Versions/A/SWBProjectModel"
)
_SWB_UTIL_RELATIVE = (
    "SwiftBuild.framework/Versions/A/PlugIns/SWBBuildService.bundle/Contents/Frameworks/"
    "SWBUtil.framework/Versions/A/SWBUtil"
)

# role, lexical path, resolved path, relative link target, sha256, bytes, mode, uid, gid, nlink
_SWIFT_BUILD_COMPONENT_SPECS: tuple[tuple[object, ...], ...] = (
    (
        "swift-dispatcher",
        _SWIFT_TOOLCHAIN_ROOT / "usr/bin/swift",
        _SWIFT_TOOLCHAIN_ROOT / "usr/bin/swift-frontend",
        "swift-frontend",
        "2ed38571e92c0283091838c1649e27650ad9c99950288e883c7b2dc6c4ce89fb",
        171_036_592,
        "0755",
        0,
        0,
        1,
    ),
    (
        "swiftc-dispatcher",
        _SWIFT_TOOLCHAIN_ROOT / "usr/bin/swiftc",
        _SWIFT_TOOLCHAIN_ROOT / "usr/bin/swift-frontend",
        "swift-frontend",
        "2ed38571e92c0283091838c1649e27650ad9c99950288e883c7b2dc6c4ce89fb",
        171_036_592,
        "0755",
        0,
        0,
        1,
    ),
    (
        "swift-build-dispatcher",
        _SWIFT_TOOLCHAIN_ROOT / "usr/bin/swift-build",
        _SWIFT_TOOLCHAIN_ROOT / "usr/bin/swift-package",
        "swift-package",
        "dc1a5f5bd4f05be81b8cc4a4bc6e0fd8846210e4cb829062d0fed3d03f79b753",
        23_293_616,
        "0755",
        0,
        0,
        1,
    ),
    (
        "swift-package",
        _SWIFT_TOOLCHAIN_ROOT / "usr/bin/swift-package",
        _SWIFT_TOOLCHAIN_ROOT / "usr/bin/swift-package",
        None,
        "dc1a5f5bd4f05be81b8cc4a4bc6e0fd8846210e4cb829062d0fed3d03f79b753",
        23_293_616,
        "0755",
        0,
        0,
        1,
    ),
    (
        "swift-driver",
        _SWIFT_TOOLCHAIN_ROOT / "usr/bin/swift-driver",
        _SWIFT_TOOLCHAIN_ROOT / "usr/bin/swift-driver",
        None,
        "fead52ebe00ec6ec700ecbb4be30f0b6204dd0506cb271dda72ac257261bd64b",
        3_011_968,
        "0755",
        0,
        0,
        1,
    ),
    (
        "swift-frontend",
        _SWIFT_TOOLCHAIN_ROOT / "usr/bin/swift-frontend",
        _SWIFT_TOOLCHAIN_ROOT / "usr/bin/swift-frontend",
        None,
        "2ed38571e92c0283091838c1649e27650ad9c99950288e883c7b2dc6c4ce89fb",
        171_036_592,
        "0755",
        0,
        0,
        1,
    ),
    (
        "clang",
        _SWIFT_TOOLCHAIN_ROOT / "usr/bin/clang",
        _SWIFT_TOOLCHAIN_ROOT / "usr/bin/clang",
        None,
        "7def90dd8829726686213a747fc5bff1583df933dae5edc55d755479e0bfe00a",
        141_373_024,
        "0755",
        0,
        0,
        1,
    ),
    (
        "clangxx-dispatcher",
        _SWIFT_TOOLCHAIN_ROOT / "usr/bin/clang++",
        _SWIFT_TOOLCHAIN_ROOT / "usr/bin/clang",
        "clang",
        "7def90dd8829726686213a747fc5bff1583df933dae5edc55d755479e0bfe00a",
        141_373_024,
        "0755",
        0,
        0,
        1,
    ),
    (
        "linker",
        _SWIFT_TOOLCHAIN_ROOT / "usr/bin/ld",
        _SWIFT_TOOLCHAIN_ROOT / "usr/bin/ld",
        None,
        "5897b275efd93b201b6df5832dd541262b3f20f290859ba78f2200a6a66ef38b",
        2_331_792,
        "0755",
        0,
        0,
        1,
    ),
    (
        "archiver",
        _SWIFT_TOOLCHAIN_ROOT / "usr/bin/ar",
        _SWIFT_TOOLCHAIN_ROOT / "usr/bin/ar",
        None,
        "e49ffad64ad1cee722540fc5ecb00a230fd8071680682c60d9c851029d20e814",
        73_520,
        "0755",
        0,
        0,
        1,
    ),
    (
        "libtool",
        _SWIFT_TOOLCHAIN_ROOT / "usr/bin/libtool",
        _SWIFT_TOOLCHAIN_ROOT / "usr/bin/libtool",
        None,
        "229eb9d8027953d2aee0590f983eed587d52bdd1ebc21114a62ce693f77b03f1",
        210_800,
        "0755",
        0,
        0,
        1,
    ),
    (
        "platform-swift-plugin-server",
        _SWIFT_PLATFORM_ROOT / "usr/bin/swift-plugin-server",
        _SWIFT_PLATFORM_ROOT / "usr/bin/swift-plugin-server",
        None,
        "438b8b9027176baed23c149a51250a94dc6a6360116aa818523168d1c4df68c8",
        71_520,
        "0755",
        0,
        0,
        1,
    ),
    (
        "in-process-plugin-server",
        _SWIFT_TOOLCHAIN_ROOT / "usr/lib/swift/host/libSwiftInProcPluginServer.dylib",
        _SWIFT_TOOLCHAIN_ROOT / "usr/lib/swift/host/libSwiftInProcPluginServer.dylib",
        None,
        "55385f1fbf98dd8e9a73cd0e87c0d93fbc778c6abe04c6fb744bff9278ef5811",
        91_424,
        "0755",
        0,
        0,
        1,
    ),
    (
        "swift-driver-library",
        _SWIFT_TOOLCHAIN_ROOT / "usr/lib/libSwiftDriver.dylib",
        _SWIFT_TOOLCHAIN_ROOT / "usr/lib/libSwiftDriver.dylib",
        None,
        "38ea28895a054a7d72da72042a786722884b62cdefdf0362d18f84a174ef87fb",
        3_031_376,
        "0755",
        0,
        0,
        1,
    ),
    (
        "swift-tools-support-library",
        _SWIFT_TOOLCHAIN_ROOT / "usr/lib/libSwiftToolsSupport.dylib",
        _SWIFT_TOOLCHAIN_ROOT / "usr/lib/libSwiftToolsSupport.dylib",
        None,
        "066f824adc6dffbfb4b88aeec2bce96bc2634b4cda4922ee2e999b4c9df431c1",
        1_190_496,
        "0755",
        0,
        0,
        1,
    ),
    (
        "build-server-protocol",
        _SWIFT_SHARED_FRAMEWORKS / "BuildServerProtocol.framework/Versions/A/BuildServerProtocol",
        _SWIFT_SHARED_FRAMEWORKS / "BuildServerProtocol.framework/Versions/A/BuildServerProtocol",
        None,
        "05be7dcb9f19802d036a5caa5cc5530c63ed0f2b3133185910200a5ee48dcec3",
        488_112,
        "0755",
        0,
        0,
        1,
    ),
    (
        "language-server-protocol",
        _SWIFT_SHARED_FRAMEWORKS / "LanguageServerProtocol.framework/Versions/A/LanguageServerProtocol",
        _SWIFT_SHARED_FRAMEWORKS / "LanguageServerProtocol.framework/Versions/A/LanguageServerProtocol",
        None,
        "7c4f0641f2d7533c2432bd0234e285bbd464274b8928b335bf2861cda19f5e00",
        2_689_424,
        "0755",
        0,
        0,
        1,
    ),
    (
        "language-server-protocol-transport",
        _SWIFT_SHARED_FRAMEWORKS
        / "LanguageServerProtocolTransport.framework/Versions/A/LanguageServerProtocolTransport",
        _SWIFT_SHARED_FRAMEWORKS
        / "LanguageServerProtocolTransport.framework/Versions/A/LanguageServerProtocolTransport",
        None,
        "3ef1a0607d060769cdae18edbae5f622d974d2f2b157385d6cb03c6d6e6f8069",
        254_480,
        "0755",
        0,
        0,
        1,
    ),
    (
        "swb-build-service",
        _SWIFT_SHARED_FRAMEWORKS / _SWB_BUILD_SERVICE_RELATIVE,
        _SWIFT_SHARED_FRAMEWORKS / _SWB_BUILD_SERVICE_RELATIVE,
        None,
        "9e8908fcb0d74d0348b31641c0d3ec0fc97bd6467f82a574b1756432a73433de",
        1_395_264,
        "0755",
        0,
        0,
        1,
    ),
    (
        "swb-project-model",
        _SWIFT_SHARED_FRAMEWORKS / _SWB_PROJECT_MODEL_RELATIVE,
        _SWIFT_SHARED_FRAMEWORKS / _SWB_PROJECT_MODEL_RELATIVE,
        None,
        "46c09eeff03bf97d179e6b6385fe6a58fea28245d6125ac61943a7615cc2acf9",
        540_144,
        "0755",
        0,
        0,
        1,
    ),
    (
        "swb-util",
        _SWIFT_SHARED_FRAMEWORKS / _SWB_UTIL_RELATIVE,
        _SWIFT_SHARED_FRAMEWORKS / _SWB_UTIL_RELATIVE,
        None,
        "165998df0e1326f5b254f40e0efe57e501f03c93bbe8ce306c82e8a77f14646c",
        3_196_784,
        "0755",
        0,
        0,
        1,
    ),
    (
        "swift-build-framework",
        _SWIFT_SHARED_FRAMEWORKS / "SwiftBuild.framework/Versions/A/SwiftBuild",
        _SWIFT_SHARED_FRAMEWORKS / "SwiftBuild.framework/Versions/A/SwiftBuild",
        None,
        "3ae14a15416d3641949cb4eedecd972eec863eb058e753f1f564e5f35fe01973",
        3_413_216,
        "0755",
        0,
        0,
        1,
    ),
    (
        "tools-protocols-swift-extensions",
        _SWIFT_SHARED_FRAMEWORKS / "ToolsProtocolsSwiftExtensions.framework/Versions/A/ToolsProtocolsSwiftExtensions",
        _SWIFT_SHARED_FRAMEWORKS / "ToolsProtocolsSwiftExtensions.framework/Versions/A/ToolsProtocolsSwiftExtensions",
        None,
        "cf57590d1be3819fbbb7ebc51435423804e9b34723b068a1b5f83e11abe603bd",
        199_824,
        "0755",
        0,
        0,
        1,
    ),
    (
        "llbuild-framework",
        _SWIFT_SHARED_FRAMEWORKS / "llbuild.framework/Versions/A/llbuild",
        _SWIFT_SHARED_FRAMEWORKS / "llbuild.framework/Versions/A/llbuild",
        None,
        "25bfb2c3d42c28cc5b01bd303268f63e26ee017c54c626d98bddbe135ed28f36",
        1_432_608,
        "0755",
        0,
        0,
        1,
    ),
    (
        "sdk-settings-json",
        _SWIFT_SDK_ROOT / "SDKSettings.json",
        _SWIFT_SDK_RESOLVED_ROOT / "SDKSettings.json",
        None,
        "f8d005f09381389167f9e0aeaa169bc9e7dff162ef22ca2fd8e98df7ff1acafe",
        7_774,
        "0644",
        0,
        0,
        1,
    ),
    (
        "sdk-settings-plist",
        _SWIFT_SDK_ROOT / "SDKSettings.plist",
        _SWIFT_SDK_RESOLVED_ROOT / "SDKSettings.plist",
        None,
        "e5c7c40b8c5dc1a9f99f8b9fa51870f8fe180421225b8201d0c4c826aad11bdc",
        5_388,
        "0644",
        0,
        0,
        1,
    ),
    (
        "sdk-foundation-tbd",
        _SWIFT_SDK_ROOT / "System/Library/Frameworks/Foundation.framework/Versions/C/Foundation.tbd",
        _SWIFT_SDK_RESOLVED_ROOT / "System/Library/Frameworks/Foundation.framework/Versions/C/Foundation.tbd",
        None,
        "f425b7c55986e46ab62fd8d8a457ee3fb1ddbe4af46b41abe1e63110ef7fba44",
        5_602_567,
        "0644",
        0,
        0,
        1,
    ),
    (
        "sdk-libswift-foundation-tbd",
        _SWIFT_SDK_ROOT / "usr/lib/swift/libswiftFoundation.tbd",
        _SWIFT_SDK_RESOLVED_ROOT / "usr/lib/swift/libswiftFoundation.tbd",
        None,
        "c9a08100fa08663ed70835c177b05ce9ff4a0f81bfb6b7d32114cdc0e0371539",
        420,
        "0644",
        0,
        0,
        1,
    ),
)

# role, lexical root, resolved root, sha256({files}), file count, logical bytes
_SWIFT_BUILD_TREE_SPECS: tuple[tuple[object, ...], ...] = (
    (
        "manifest-api",
        _SWIFT_TOOLCHAIN_ROOT / "usr/lib/swift/pm/ManifestAPI",
        _SWIFT_TOOLCHAIN_ROOT / "usr/lib/swift/pm/ManifestAPI",
        "aaf47697e4ada643c682431426648cc1a915416afd2caf5beec096f8fa36417a",
        9,
        3_659_442,
    ),
    (
        "plugin-api",
        _SWIFT_TOOLCHAIN_ROOT / "usr/lib/swift/pm/PluginAPI",
        _SWIFT_TOOLCHAIN_ROOT / "usr/lib/swift/pm/PluginAPI",
        "1a3dd060b6803d6873648832cea0b52635f9ae1a261e34bfeb133f7178ca645a",
        5,
        3_386_557,
    ),
    (
        "toolchain-host-plugins",
        _SWIFT_TOOLCHAIN_ROOT / "usr/lib/swift/host/plugins",
        _SWIFT_TOOLCHAIN_ROOT / "usr/lib/swift/host/plugins",
        "912a7dbdbe6735e08ce84b0c7f313d18e4bb0ebf850c36f199cc1b46e35357ed",
        4,
        1_617_344,
    ),
    (
        "platform-host-plugins",
        _SWIFT_PLATFORM_ROOT / "usr/lib/swift/host/plugins",
        _SWIFT_PLATFORM_ROOT / "usr/lib/swift/host/plugins",
        "6408d05c19f22daf7918307aa95077d8f2849fce8c85b722c90d5d9b1fa6d417",
        15,
        5_125_484,
    ),
    (
        "sdk-foundation-module",
        _SWIFT_SDK_ROOT / "System/Library/Frameworks/Foundation.framework/Versions/C/Modules",
        _SWIFT_SDK_RESOLVED_ROOT / "System/Library/Frameworks/Foundation.framework/Versions/C/Modules",
        "7165c4716fa827f8803998ea3e436e4458539900c0511cd61d3327293890d1f9",
        9,
        7_727_385,
    ),
    (
        "sdk-corefoundation-module",
        _SWIFT_SDK_ROOT / "usr/lib/swift/CoreFoundation.swiftmodule",
        _SWIFT_SDK_RESOLVED_ROOT / "usr/lib/swift/CoreFoundation.swiftmodule",
        "a0405db90f83fb73a3fa7c63d4aa5f23c801d9fe07c24e690fb309837569710d",
        8,
        104_510,
    ),
    (
        "sdk-objectivec-module",
        _SWIFT_SDK_ROOT / "usr/lib/swift/ObjectiveC.swiftmodule",
        _SWIFT_SDK_RESOLVED_ROOT / "usr/lib/swift/ObjectiveC.swiftmodule",
        "09c0b3b5ccc32bf959edf60385077623eda7e9f3b8a03f229fd655a08376845c",
        8,
        52_177,
    ),
    (
        "sdk-darwin-foundation1-module",
        _SWIFT_SDK_ROOT / "usr/lib/swift/_DarwinFoundation1.swiftmodule",
        _SWIFT_SDK_RESOLVED_ROOT / "usr/lib/swift/_DarwinFoundation1.swiftmodule",
        "afd2771e20e7908556e4093be833fc27a989610d1a67adcf3d2192fc0bed20a1",
        8,
        162_910,
    ),
    (
        "sdk-darwin-foundation2-module",
        _SWIFT_SDK_ROOT / "usr/lib/swift/_DarwinFoundation2.swiftmodule",
        _SWIFT_SDK_RESOLVED_ROOT / "usr/lib/swift/_DarwinFoundation2.swiftmodule",
        "7cb0327244e386b14d8464ed2bcabcbd307ac72e303786d590a0dc90b9535b72",
        8,
        12_270,
    ),
    (
        "sdk-darwin-foundation3-module",
        _SWIFT_SDK_ROOT / "usr/lib/swift/_DarwinFoundation3.swiftmodule",
        _SWIFT_SDK_RESOLVED_ROOT / "usr/lib/swift/_DarwinFoundation3.swiftmodule",
        "8662a95e3ab622e93e92ce13177a31d6831760e49906357c457e7aa811ece40a",
        8,
        7_854,
    ),
    (
        "toolchain-foundation-prebuilt-module",
        _SWIFT_TOOLCHAIN_ROOT / "usr/lib/swift/macosx/prebuilt-modules/26.5/Foundation.swiftmodule",
        _SWIFT_TOOLCHAIN_ROOT / "usr/lib/swift/macosx/prebuilt-modules/26.5/Foundation.swiftmodule",
        "cc03cfb24425d6842fe72ed89c2f2b2e26ae641cb35cd3211e3f2d93d5bd9b93",
        4,
        15_112_272,
    ),
    (
        "sdk-foundation-headers",
        _SWIFT_SDK_ROOT / "System/Library/Frameworks/Foundation.framework/Versions/C/Headers",
        _SWIFT_SDK_RESOLVED_ROOT / "System/Library/Frameworks/Foundation.framework/Versions/C/Headers",
        "7c6b6a8f06f51aeaa26411b9fb79cb28800461f939eac310c2be9a4f5edcec91",
        174,
        1_707_906,
    ),
    (
        "sdk-objc-headers",
        _SWIFT_SDK_ROOT / "usr/include/objc",
        _SWIFT_SDK_RESOLVED_ROOT / "usr/include/objc",
        "798fa35ace9193dc45fceb26954f025f04b67116e329596673319d851485517a",
        17,
        136_132,
    ),
)
_SWIFT_ANALYZER_LOCK = threading.Lock()
_SWIFT_ANALYZER_TEMPORARY: tempfile.TemporaryDirectory[str] | None = None
_SWIFT_ANALYZER_BINARY: Path | None = None
_SWIFT_ANALYZER_RECEIPT: dict[str, Any] | None = None
_SWIFT_ANALYZER_FAILURE: tuple[str, str, str] | None = None
_SWIFT_ANALYZE_PROMOTABLE_DOMAIN_ERRORS = frozenset(
    {
        "SWIFT_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:Int",
    }
)
_JAVA_ANALYZER_SOURCE_MAX_BYTES = 1_000_000
_JAVA_ANALYZE_PROMOTABLE_DOMAIN_ERRORS = frozenset(
    {
        "JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:int",
        "JAVA_STRING_REFERENCE_EQUALITY_OUTSIDE_CERTIFIED_SUBSET",
    }
)
_CSHARP_ANALYZER_KIND = "elmos.csharp-semantic-cli-build-receipt"
_CSHARP_ANALYZER_INPUTS = (
    "global.json",
    "Directory.Build.props",
    "Directory.Packages.props",
    "src/Elmos.Dotnet.SemanticCli/Elmos.Dotnet.SemanticCli.csproj",
    "src/Elmos.Dotnet.SemanticCli/Program.cs",
    "src/Elmos.Dotnet.SemanticCli/packages.lock.json",
)
_CSHARP_ANALYZER_ENTRYPOINT = "Elmos.Dotnet.SemanticCli.dll"
_CSHARP_ANALYZER_MAX_INPUT_BYTES = 2_000_000
_CSHARP_ANALYZER_MAX_OUTPUT_FILE_BYTES = 100_000_000
_CSHARP_ANALYZER_MAX_OUTPUT_BYTES = 250_000_000
_CSHARP_ANALYZER_LOCK = threading.Lock()
_CSHARP_ANALYZER_TEMPORARY: tempfile.TemporaryDirectory[str] | None = None
_CSHARP_ANALYZER_BINARY: Path | None = None
_CSHARP_ANALYZER_RECEIPT: dict[str, Any] | None = None
_CSHARP_ANALYZER_FAILURE: tuple[str, str, str] | None = None


def _scan_preprocessor_directives(
    source: Path,
    language: Language,
    source_bytes: bytes,
) -> list[dict[str, Any]]:
    if language not in {"cpp", "objc"}:
        return []
    directives: list[dict[str, Any]] = []
    offset = 0
    for line in source_bytes.splitlines(keepends=True):
        content = line.rstrip(b"\r\n")
        candidates = [(index, marker) for marker in (b"#", b"%:", b"??=") if (index := content.find(marker)) >= 0]
        if not candidates:
            offset += len(line)
            continue
        marker_offset, marker = min(candidates, key=lambda item: item[0])
        raw = content[marker_offset:]
        payload = raw[len(marker) :].lstrip()
        match = re.match(rb"([A-Za-z_][A-Za-z0-9_]*)", payload)
        if marker != b"#":
            kind = "alternative-directive-marker"
            value_bytes = raw
        elif match is None:
            kind = "invalid"
            value_bytes = payload
        else:
            kind = match.group(1).decode("ascii").lower()
            value_bytes = payload[match.end() :].strip()
        start_byte = offset + marker_offset
        end_byte = offset + len(content)
        directives.append(
            {
                "order": len(directives),
                "kind": kind,
                "value": value_bytes.decode("utf-8", errors="backslashreplace"),
                "source_span": {
                    "file": source.name,
                    "start_byte": start_byte,
                    "end_byte": end_byte,
                },
                "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
            }
        )
        offset += len(line)
    return directives


def _verify_emitted_helper_sources(source: Path, language: Language) -> None:
    # JavaScript helper identity is established by the pinned TypeScript AST
    # frontend.  Text search cannot distinguish a call from the same bytes in
    # a string or comment, and therefore must not pre-empt that exact parser
    # boundary.  Native targets below retain their existing source precheck.
    if language == "javascript":
        return
    registries = {
        "cpp": _CPP_HELPERS,
        "objc": _OBJC_HELPERS,
        "swift": _SWIFT_HELPERS,
        # The PHP frontend deliberately *skips* the helper bodies when it
        # relifts (see native/php/analyzer.php, skipBalancedBlock). That is only
        # sound because this check has already asserted each helper's source
        # appears byte-for-byte exactly once, so the bytes are pinned here
        # rather than re-parsed there.
        "php": _PHP_HELPERS,
    }
    registry = registries.get(language)
    if registry is None:
        return
    content = source.read_text(encoding="utf-8")
    for helper_id, expected in registry.items():
        first_line = expected.splitlines()[0]
        names = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", first_line)
        if not names:
            raise RouteError(f"EMITTED_HELPER_REGISTRY_INVALID:{language}:{helper_id}")
        name = names[-1]
        if f"{name}(" not in content:
            continue
        if content.count(expected) != 1:
            raise RouteError(f"EMITTED_HELPER_SOURCE_MISMATCH:{language}:{helper_id}:{name}")


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _swift_analyzer_input_manifest(package: Path) -> dict[str, Any]:
    try:
        package = package.absolute()
        package_identity = _verify_secure_directory_chain(package, "SWIFT_ANALYZER_PACKAGE_UNSAFE")
    except OSError as error:
        raise RouteError("SWIFT_ANALYZER_INPUT_MISSING") from error
    sources = package / "Sources"
    sources_identity = _verify_secure_directory_chain(sources, "SWIFT_ANALYZER_SOURCES_UNSAFE")

    def discover() -> list[Path]:
        candidates = [
            package / "Package.swift",
            package / "Package.resolved",
            *sorted(sources.rglob("*.swift"), key=lambda item: item.relative_to(package).as_posix()),
        ]
        paths: list[Path] = []
        for path in candidates:
            relative = path.relative_to(package).as_posix()
            try:
                metadata = path.lstat()
            except OSError as error:
                raise RouteError(f"SWIFT_ANALYZER_INPUT_MISSING:{relative}") from error
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) & 0o022
                or metadata.st_nlink != 1
                or metadata.st_size <= 0
                or metadata.st_size > 2_000_000
            ):
                raise RouteError(f"SWIFT_ANALYZER_INPUT_UNSAFE:{relative}")
            paths.append(path)
        return paths

    inputs = discover()
    if len(inputs) < 3 or len({item.relative_to(package).as_posix() for item in inputs}) != len(inputs):
        raise RouteError("SWIFT_ANALYZER_INPUT_SET_INVALID")
    files: list[dict[str, Any]] = []
    contents: dict[str, bytes] = {}
    for path in inputs:
        relative = path.relative_to(package).as_posix()
        data = _stable_read_regular_file(
            path,
            failure=f"SWIFT_ANALYZER_INPUT_CHANGED:{relative}",
            maximum_bytes=2_000_000,
            require_nlink_one=True,
        )
        contents[relative] = data
        files.append(
            {
                "path": relative,
                "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            }
        )
    if [item.relative_to(package).as_posix() for item in discover()] != [item["path"] for item in files]:
        raise RouteError("SWIFT_ANALYZER_INPUT_SET_CHANGED")
    if (
        _verify_secure_directory_chain(package, "SWIFT_ANALYZER_PACKAGE_CHANGED") != package_identity
        or _verify_secure_directory_chain(sources, "SWIFT_ANALYZER_SOURCES_CHANGED") != sources_identity
    ):
        raise RouteError("SWIFT_ANALYZER_INPUT_DIRECTORY_CHANGED")
    try:
        resolved = json.loads(contents["Package.resolved"])
    except (KeyError, json.JSONDecodeError) as error:
        raise RouteError("SWIFT_ANALYZER_RESOLUTION_INVALID") from error
    pins = resolved.get("pins") if isinstance(resolved, dict) else None
    expected_pin = {
        "identity": _SWIFT_DEPENDENCY_IDENTITY,
        "kind": "remoteSourceControl",
        "location": "https://github.com/swiftlang/swift-syntax.git",
        "state": {"revision": _SWIFT_SYNTAX_REVISION, "version": _SWIFT_SYNTAX_VERSION},
    }
    if resolved.get("version") != 2 or pins != [expected_pin]:
        raise RouteError("SWIFT_ANALYZER_RESOLUTION_MISMATCH")
    summary = {"files": files}
    return {
        "package": package,
        "files": files,
        "contents": contents,
        "sha256": _canonical_digest(summary),
    }


def _swift_dependency_tree(checkout: Path) -> dict[str, Any]:
    failure = "SWIFT_ANALYZER_DEPENDENCY_CHECKOUT_UNSAFE"
    _verify_secure_directory_chain(checkout, failure)

    def discover() -> list[Path]:
        paths: list[Path] = []
        try:
            for path in sorted(checkout.rglob("*"), key=lambda item: item.relative_to(checkout).as_posix()):
                relative_path = path.relative_to(checkout)
                if ".git" in relative_path.parts:
                    continue
                metadata = path.lstat()
                if (
                    stat.S_ISLNK(metadata.st_mode)
                    or metadata.st_uid != os.getuid()
                    or stat.S_IMODE(metadata.st_mode) & 0o022
                    or not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode))
                ):
                    raise RouteError(f"{failure}:{relative_path.as_posix()}")
                if stat.S_ISREG(metadata.st_mode):
                    paths.append(path)
        except OSError as error:
            raise RouteError(failure) from error
        return paths

    paths = discover()
    files: list[dict[str, Any]] = []
    total = 0
    for path in paths:
        relative_path = path.relative_to(checkout)
        data = _stable_read_regular_file(
            path,
            failure=f"{failure}:{relative_path.as_posix()}",
            maximum_bytes=_SWIFT_SYNTAX_TREE_BYTES,
            minimum_bytes=0,
            require_nlink_one=True,
        )
        total += len(data)
        files.append(
            {
                "path": relative_path.as_posix(),
                "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            }
        )
    if [item.relative_to(checkout).as_posix() for item in discover()] != [item["path"] for item in files]:
        raise RouteError("SWIFT_ANALYZER_DEPENDENCY_PATH_SET_CHANGED")
    digest = _canonical_digest({"files": files})
    if (
        digest != "sha256:" + _SWIFT_SYNTAX_TREE_SHA256
        or len(files) != _SWIFT_SYNTAX_TREE_FILE_COUNT
        or total != _SWIFT_SYNTAX_TREE_BYTES
    ):
        raise RouteError(f"SWIFT_ANALYZER_DEPENDENCY_TREE_MISMATCH:sha256={digest}:files={len(files)}:bytes={total}")
    return {"sha256": digest, "file_count": len(files), "bytes": total}


def _verify_secure_directory_chain(directory: Path, failure: str) -> tuple[tuple[object, ...], ...]:
    """Bind one absolute cache/build path without following symlink components."""

    if not directory.is_absolute():
        raise RouteError(failure)
    cursor = Path("/")
    identities: list[tuple[object, ...]] = []
    try:
        for part in directory.parts[1:]:
            cursor = cursor / part
            metadata = cursor.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid not in {0, os.getuid()}
                or stat.S_IMODE(metadata.st_mode) & 0o022
            ):
                raise RouteError(failure)
            identities.append(
                (
                    str(cursor),
                    metadata.st_dev,
                    metadata.st_ino,
                    metadata.st_mode,
                    metadata.st_uid,
                    metadata.st_gid,
                    metadata.st_mtime_ns,
                    metadata.st_ctime_ns,
                )
            )
        if directory.resolve(strict=True) != directory:
            raise RouteError(failure)
    except OSError as error:
        raise RouteError(failure) from error
    return tuple(identities)


def _stable_read_regular_file(
    path: Path,
    *,
    failure: str,
    maximum_bytes: int,
    minimum_bytes: int = 1,
    allowed_uids: frozenset[int] | None = None,
    require_nlink_one: bool = False,
) -> bytes:
    permitted_uids = allowed_uids if allowed_uids is not None else frozenset({os.getuid()})
    try:
        before = path.lstat()
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened_before = os.fstat(descriptor)
            chunks: list[bytes] = []
            total = 0
            while chunk := os.read(descriptor, 1024 * 1024):
                total += len(chunk)
                if total > maximum_bytes:
                    raise RouteError(failure)
                chunks.append(chunk)
            opened_after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        after = path.lstat()
    except OSError as error:
        raise RouteError(failure) from error
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_uid,
        before.st_gid,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    if (
        identity
        != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_nlink,
            after.st_uid,
            after.st_gid,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        or identity
        != (
            opened_before.st_dev,
            opened_before.st_ino,
            opened_before.st_mode,
            opened_before.st_nlink,
            opened_before.st_uid,
            opened_before.st_gid,
            opened_before.st_size,
            opened_before.st_mtime_ns,
            opened_before.st_ctime_ns,
        )
        or identity
        != (
            opened_after.st_dev,
            opened_after.st_ino,
            opened_after.st_mode,
            opened_after.st_nlink,
            opened_after.st_uid,
            opened_after.st_gid,
            opened_after.st_size,
            opened_after.st_mtime_ns,
            opened_after.st_ctime_ns,
        )
        or not stat.S_ISREG(after.st_mode)
        or after.st_uid not in permitted_uids
        or stat.S_IMODE(after.st_mode) & 0o022
        or after.st_size < minimum_bytes
        or (require_nlink_one and after.st_nlink != 1)
    ):
        raise RouteError(failure)
    return b"".join(chunks)


def _swift_dependency_cache_key() -> str:
    return (
        f"swift-syntax-{_SWIFT_DEPENDENCY_CACHE_KEY_SCHEMA}-"
        f"{_SWIFT_SYNTAX_VERSION}-{_SWIFT_SYNTAX_REVISION}-{_SWIFT_SYNTAX_TREE_SHA256}"
    )


def _swift_dependency_cache_base() -> Path:
    return (
        _swift_dependency_cache_home()
        / "Library"
        / "Caches"
        / "elmos-polyglot-route-engine"
        / _SWIFT_DEPENDENCY_CACHE_SCHEMA
    )


def _swift_dependency_cache_home() -> Path:
    return Path(pwd.getpwuid(os.getuid()).pw_dir)


def _swift_dependency_cache_receipt(
    cache: Path,
    cache_key: str,
    dependency: dict[str, Any],
) -> dict[str, Any]:
    """Verify the local cache path and return its portable content identity."""

    expected_cache = (_swift_dependency_cache_base() / cache_key).absolute()
    if (
        cache.absolute() != expected_cache
        or cache_key != _swift_dependency_cache_key()
        or dependency
        != {
            "sha256": "sha256:" + _SWIFT_SYNTAX_TREE_SHA256,
            "file_count": _SWIFT_SYNTAX_TREE_FILE_COUNT,
            "bytes": _SWIFT_SYNTAX_TREE_BYTES,
        }
    ):
        raise RouteError("SWIFT_ANALYZER_DEPENDENCY_CACHE_RECEIPT_INVALID")
    return {
        "cache_key": cache_key,
        "cache_schema": _SWIFT_DEPENDENCY_CACHE_SCHEMA,
        "object_store_policy": _SWIFT_DEPENDENCY_OBJECT_STORE_POLICY,
        "identity": _SWIFT_DEPENDENCY_IDENTITY,
        "version": _SWIFT_SYNTAX_VERSION,
        "revision": _SWIFT_SYNTAX_REVISION,
        "seed": _SWIFT_DEPENDENCY_CACHE_SEED,
        "sha256": dependency["sha256"],
        "file_count": dependency["file_count"],
        "bytes": dependency["bytes"],
    }


def _verified_swift_xcode_regular_file(
    path: Path,
    *,
    expected_sha256: str,
    expected_bytes: int,
    failure: str,
) -> tuple[dict[str, Any], tuple[object, ...]]:
    chain_before = _verify_swift_xcode_directory_chain(path.parent, failure)
    data = _stable_read_regular_file(
        path,
        failure=failure,
        maximum_bytes=max(expected_bytes, 1),
        allowed_uids=frozenset({0}),
        require_nlink_one=True,
    )
    try:
        metadata = path.lstat()
        if path.resolve(strict=True) != path:
            raise RouteError(failure)
    except OSError as error:
        raise RouteError(failure) from error
    chain_after = _verify_swift_xcode_directory_chain(path.parent, failure)
    receipt = {
        "path": str(path),
        "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
        "nlink": metadata.st_nlink,
    }
    expected = {
        "path": str(path),
        "sha256": "sha256:" + expected_sha256,
        "bytes": expected_bytes,
        "mode": "0755",
        "uid": 0,
        "gid": 0,
        "nlink": 1,
    }
    identity = (
        chain_after,
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )
    if chain_before != chain_after or receipt != expected:
        raise RouteError(failure)
    return receipt, identity


def _capture_apple_git(
    root: Path,
    environment: dict[str, str],
) -> tuple[dict[str, str], tuple[object, ...]]:
    file_before, identity_before = _verified_swift_xcode_regular_file(
        _APPLE_GIT,
        expected_sha256=_APPLE_GIT_SHA256,
        expected_bytes=_APPLE_GIT_BYTES,
        failure="SWIFT_ANALYZER_GIT_PROVENANCE_MISMATCH",
    )
    version = _run_swift_build_step(
        [str(_APPLE_GIT), "--version"],
        cwd=root,
        environment=environment,
        timeout=30,
        failure="SWIFT_ANALYZER_GIT_UNAVAILABLE",
    ).stdout.strip()
    file_after, identity_after = _verified_swift_xcode_regular_file(
        _APPLE_GIT,
        expected_sha256=_APPLE_GIT_SHA256,
        expected_bytes=_APPLE_GIT_BYTES,
        failure="SWIFT_ANALYZER_GIT_PROVENANCE_MISMATCH",
    )
    if file_before != file_after or identity_before != identity_after:
        raise RouteError("SWIFT_ANALYZER_GIT_PROVENANCE_MISMATCH")
    if version != _APPLE_GIT_VERSION:
        raise RouteError("SWIFT_ANALYZER_GIT_VERSION_MISMATCH")
    return (
        {
            "path": str(_APPLE_GIT),
            "sha256": file_after["sha256"],
            "version": _APPLE_GIT_VERSION,
        },
        identity_after,
    )


def _verify_apple_git(root: Path, environment: dict[str, str]) -> dict[str, str]:
    return _capture_apple_git(root, environment)[0]


def _run_verified_apple_git(
    arguments: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout: int,
    failure: str,
) -> subprocess.CompletedProcess[str]:
    receipt_before, identity_before = _capture_apple_git(cwd, environment)
    completed = _run_swift_build_step(
        [str(_APPLE_GIT), *arguments],
        cwd=cwd,
        environment=environment,
        timeout=timeout,
        failure=failure,
    )
    receipt_after, identity_after = _capture_apple_git(cwd, environment)
    if receipt_before != receipt_after or identity_before != identity_after:
        raise RouteError("SWIFT_ANALYZER_GIT_CHANGED_DURING_OPERATION")
    return completed


def _verified_swift_system_tool(
    path: Path,
    *,
    expected_sha256: str,
    expected_bytes: int,
    failure: str,
) -> tuple[dict[str, Any], tuple[object, ...]]:
    chain_before = _verify_secure_directory_chain(path.parent, failure)
    data = _stable_read_regular_file(
        path,
        failure=failure,
        maximum_bytes=max(expected_bytes, 1),
        allowed_uids=frozenset({0}),
        require_nlink_one=True,
    )
    try:
        metadata = path.lstat()
        if path.resolve(strict=True) != path:
            raise RouteError(failure)
    except OSError as error:
        raise RouteError(failure) from error
    chain_after = _verify_secure_directory_chain(path.parent, failure)
    receipt = {
        "path": str(path),
        "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
        "nlink": metadata.st_nlink,
    }
    expected = {
        "path": str(path),
        "sha256": "sha256:" + expected_sha256,
        "bytes": expected_bytes,
        "mode": "0755",
        "uid": 0,
        "gid": 0,
        "nlink": 1,
    }
    identity = (
        chain_after,
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )
    if chain_before != chain_after or receipt != expected:
        raise RouteError(failure)
    return receipt, identity


def _verify_swift_sandbox_signature(root: Path, environment: dict[str, str]) -> None:
    _run_swift_build_step(
        [str(_CODESIGN), "--verify", "--strict", str(_SANDBOX_EXEC)],
        cwd=root,
        environment=environment,
        timeout=30,
        failure="NETWORK_ISOLATION_NOT_RUN:sandbox-exec-signature",
    )
    signature_result = _run_swift_build_step(
        [str(_CODESIGN), "-d", "--verbose=4", str(_SANDBOX_EXEC)],
        cwd=root,
        environment=environment,
        timeout=30,
        failure="NETWORK_ISOLATION_NOT_RUN:sandbox-exec-signature",
    )
    signature_lines = set((signature_result.stdout + signature_result.stderr).splitlines())
    if (
        "Identifier=com.apple.sandbox-exec" not in signature_lines
        or "Authority=Apple Root CA" not in signature_lines
        or "TeamIdentifier=not set" not in signature_lines
        or f"CandidateCDHashFull sha256={_SANDBOX_EXEC_CDHASH_FULL}" not in signature_lines
    ):
        raise RouteError("NETWORK_ISOLATION_NOT_RUN:sandbox-exec-signature")


def _swift_network_probe_macho_receipt(data: bytes) -> dict[str, Any]:
    failure = "NETWORK_ISOLATION_NOT_RUN:probe-mach-o"
    if len(data) < 32:
        raise RouteError(failure)
    magic, cpu_type, _cpu_subtype, file_type, command_count, command_bytes, _flags, _reserved = struct.unpack_from(
        "<IiiIIIII", data, 0
    )
    if magic != 0xFEEDFACF or cpu_type != 0x0100000C or file_type != 2:
        raise RouteError(failure)
    command_end = 32 + command_bytes
    if command_end > len(data):
        raise RouteError(failure)
    offset = 32
    uuids: list[bytes] = []
    linked_libraries: list[str] = []
    signature_commands: list[tuple[int, int]] = []
    dylib_commands = frozenset({0xC, 0x18 | 0x80000000, 0x1F | 0x80000000, 0x23 | 0x80000000, 0x20})
    for _index in range(command_count):
        if offset + 8 > command_end:
            raise RouteError(failure)
        command, size = struct.unpack_from("<II", data, offset)
        if size < 8 or size % 8 != 0 or offset + size > command_end:
            raise RouteError(failure)
        if command == 0x1B:
            if size != 24:
                raise RouteError(failure)
            uuids.append(data[offset + 8 : offset + 24])
        elif command in dylib_commands:
            if size < 24:
                raise RouteError(failure)
            name_offset = struct.unpack_from("<I", data, offset + 8)[0]
            if name_offset < 24 or name_offset >= size:
                raise RouteError(failure)
            name_bytes = data[offset + name_offset : offset + size].split(b"\0", 1)[0]
            try:
                linked_libraries.append(name_bytes.decode("utf-8"))
            except UnicodeDecodeError as error:
                raise RouteError(failure) from error
        elif command == 0x1D:
            if size != 16:
                raise RouteError(failure)
            data_offset, data_size = struct.unpack_from("<II", data, offset + 8)
            signature_commands.append((data_offset, data_size))
        offset += size
    if offset != command_end or len(uuids) != 1 or len(signature_commands) != 1:
        raise RouteError(failure)
    signature_offset, signature_size = signature_commands[0]
    if signature_size == 0 or signature_offset + signature_size != len(data):
        raise RouteError(failure)
    uuid_hex = uuids[0].hex().upper()
    uuid_value = f"{uuid_hex[:8]}-{uuid_hex[8:12]}-{uuid_hex[12:16]}-{uuid_hex[16:20]}-{uuid_hex[20:]}"
    if uuid_value != _SANDBOX_NETWORK_PROBE_UUID or tuple(linked_libraries) != _SANDBOX_NETWORK_PROBE_LINKED_LIBRARIES:
        raise RouteError(failure)
    return {
        "architecture": "arm64",
        "file_type": "MH_EXECUTE",
        "uuid": uuid_value,
        "cdhash_full": _SANDBOX_NETWORK_PROBE_CDHASH_FULL,
        "linked_libraries": list(linked_libraries),
    }


def _verify_swift_network_probe_signature(
    binary: Path,
    *,
    root: Path,
    environment: dict[str, str],
) -> None:
    failure = "NETWORK_ISOLATION_NOT_RUN:probe-signature"
    _run_swift_build_step(
        [str(_CODESIGN), "--verify", "--strict", str(binary)],
        cwd=root,
        environment=environment,
        timeout=30,
        failure=failure,
    )
    signature_result = _run_swift_build_step(
        [str(_CODESIGN), "-d", "--verbose=4", str(binary)],
        cwd=root,
        environment=environment,
        timeout=30,
        failure=failure,
    )
    signature_lines = set((signature_result.stdout + signature_result.stderr).splitlines())
    if (
        f"Identifier={_SANDBOX_NETWORK_PROBE_BINARY_NAME}" not in signature_lines
        or "Signature=adhoc" not in signature_lines
        or "TeamIdentifier=not set" not in signature_lines
        or f"CandidateCDHashFull sha256={_SANDBOX_NETWORK_PROBE_CDHASH_FULL}" not in signature_lines
    ):
        raise RouteError(failure)


def _verify_swift_network_probe_binary(
    binary: Path,
    *,
    expected_mode: str,
    root: Path,
    environment: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    failure = "NETWORK_ISOLATION_NOT_RUN:probe-binary"
    binary = binary.absolute()
    _verify_secure_directory_chain(binary.parent, failure)
    data = _stable_read_regular_file(
        binary,
        failure=failure,
        maximum_bytes=_SANDBOX_NETWORK_PROBE_BINARY_BYTES,
        allowed_uids=frozenset({os.getuid()}),
        require_nlink_one=True,
    )
    try:
        metadata = binary.lstat()
        if binary.resolve(strict=True) != binary:
            raise RouteError(failure)
    except OSError as error:
        raise RouteError(failure) from error
    receipt = {
        "name": _SANDBOX_NETWORK_PROBE_BINARY_NAME,
        "path": str(binary),
        "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
        "nlink": metadata.st_nlink,
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
    }
    if (
        receipt["sha256"] != "sha256:" + _SANDBOX_NETWORK_PROBE_BINARY_SHA256
        or receipt["bytes"] != _SANDBOX_NETWORK_PROBE_BINARY_BYTES
        or receipt["mode"] != expected_mode
        or receipt["uid"] != os.getuid()
        or receipt["nlink"] != 1
    ):
        raise RouteError(failure)
    mach_o = _swift_network_probe_macho_receipt(data)
    _verify_swift_network_probe_signature(binary, root=root, environment=environment)
    return receipt, mach_o


def _seal_swift_network_probe_binary(
    source: Path,
    *,
    root: Path,
    environment: dict[str, str],
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    source_data = _stable_read_regular_file(
        source,
        failure="NETWORK_ISOLATION_NOT_RUN:probe-binary-source",
        maximum_bytes=_SANDBOX_NETWORK_PROBE_BINARY_BYTES,
        allowed_uids=frozenset({os.getuid()}),
        require_nlink_one=True,
    )
    if hashlib.sha256(source_data).hexdigest() != _SANDBOX_NETWORK_PROBE_BINARY_SHA256:
        raise RouteError("NETWORK_ISOLATION_NOT_RUN:probe-binary-source")
    execution_root = root / "network-probe-execution"
    try:
        execution_root.mkdir(mode=0o700)
        sealed = execution_root / _SANDBOX_NETWORK_PROBE_BINARY_NAME
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(sealed, flags, 0o500)
        try:
            offset = 0
            while offset < len(source_data):
                offset += os.write(descriptor, source_data[offset:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        sealed.chmod(0o500)
        execution_root.chmod(0o500)
        root_metadata = execution_root.lstat()
    except OSError as error:
        raise RouteError("NETWORK_ISOLATION_NOT_RUN:probe-seal") from error
    binary, mach_o = _verify_swift_network_probe_binary(
        sealed,
        expected_mode="0500",
        root=root,
        environment=environment,
    )
    seal = {
        "policy": "private-nonwritable-execution-root-v1",
        "root": str(execution_root),
        "mode": f"{stat.S_IMODE(root_metadata.st_mode):04o}",
        "uid": root_metadata.st_uid,
        "gid": root_metadata.st_gid,
        "device": root_metadata.st_dev,
        "inode": root_metadata.st_ino,
        "binary": binary,
    }
    if seal["mode"] != "0500" or seal["uid"] != os.getuid():
        raise RouteError("NETWORK_ISOLATION_NOT_RUN:probe-seal")
    return sealed, seal, mach_o


def _verify_swift_network_probe_seal(
    binary: Path,
    seal: dict[str, Any],
    *,
    root: Path,
    environment: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    failure = "NETWORK_ISOLATION_NOT_RUN:probe-seal-changed"
    if set(seal) != {"policy", "root", "mode", "uid", "gid", "device", "inode", "binary"}:
        raise RouteError(failure)
    try:
        execution_root = Path(str(seal["root"]))
        metadata = execution_root.lstat()
    except OSError as error:
        raise RouteError(failure) from error
    observed_root = {
        "policy": "private-nonwritable-execution-root-v1",
        "root": str(execution_root),
        "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
    }
    if (
        observed_root != {key: seal[key] for key in observed_root}
        or observed_root["mode"] != "0500"
        or binary.parent != execution_root
    ):
        raise RouteError(failure)
    observed_binary, mach_o = _verify_swift_network_probe_binary(
        binary,
        expected_mode="0500",
        root=root,
        environment=environment,
    )
    if observed_binary != seal["binary"]:
        raise RouteError(failure)
    return observed_binary, mach_o


def _swift_network_probe_sdk_identity() -> tuple[object, ...]:
    failure = "NETWORK_ISOLATION_NOT_RUN:probe-sdk"
    try:
        metadata = _SWIFT_SDK_ROOT.lstat()
        target = os.readlink(_SWIFT_SDK_ROOT)
        resolved = _SWIFT_SDK_ROOT.resolve(strict=True)
    except OSError as error:
        raise RouteError(failure) from error
    if (
        not stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or target != "MacOSX.sdk"
        or resolved != _SWIFT_SDK_RESOLVED_ROOT
    ):
        raise RouteError(failure)
    return (
        _verify_swift_xcode_directory_chain(resolved, failure),
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_mtime_ns,
        target,
    )


def _swift_network_probe_compiler_receipt() -> dict[str, Any]:
    matches = [spec for spec in _SWIFT_BUILD_COMPONENT_SPECS if spec[0] == "clang"]
    if len(matches) != 1:
        raise RouteError("NETWORK_ISOLATION_NOT_RUN:probe-compiler")
    return _swift_build_component_receipt(matches[0], {})


def _require_swift_network_probe_build_environment(
    root: Path,
    environment: dict[str, str],
) -> None:
    toolchain_bin = _SWIFT_TOOLCHAIN_ROOT / "usr/bin"
    expected = {
        "PATH": os.pathsep.join(
            str(path) for path in (toolchain_bin, Path("/usr/bin"), Path("/bin"), Path("/usr/sbin"), Path("/sbin"))
        ),
        "HOME": str((root / "home").resolve()),
        "TMPDIR": str((root / "tmp").resolve()),
        "LANG": "C",
        "LC_ALL": "C",
        "TZ": "UTC",
        "NO_COLOR": "1",
        "CLICOLOR": "0",
        "SOURCE_DATE_EPOCH": "0",
        "ZERO_AR_DATE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "TEST_TELEMETRY_DIR": str((root / "home" / ".elmos-go-telemetry").resolve()),
        "XDG_CACHE_HOME": str((root / "home" / ".cache").resolve()),
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "SWIFT_DETERMINISTIC_HASHING": "1",
    }
    if environment != expected:
        raise RouteError("NETWORK_ISOLATION_NOT_RUN:probe-environment")


def _verified_swift_network_isolation(
    root: Path,
    environment: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    policy_bytes = _SANDBOX_EXEC_POLICY.encode("utf-8")
    _require_swift_network_probe_build_environment(root, environment)
    source_bytes = _SANDBOX_NETWORK_PROBE_SOURCE.encode("utf-8")
    if (
        len(source_bytes) != _SANDBOX_NETWORK_PROBE_SOURCE_BYTES
        or hashlib.sha256(source_bytes).hexdigest() != _SANDBOX_NETWORK_PROBE_SOURCE_SHA256
    ):
        raise RouteError("NETWORK_ISOLATION_NOT_RUN:probe-source")
    try:
        sandbox_before, sandbox_identity_before = _verified_swift_system_tool(
            _SANDBOX_EXEC,
            expected_sha256=_SANDBOX_EXEC_SHA256,
            expected_bytes=_SANDBOX_EXEC_BYTES,
            failure="NETWORK_ISOLATION_NOT_RUN:sandbox-exec-provenance",
        )
        verifier_before, verifier_identity_before = _verified_swift_system_tool(
            _CODESIGN,
            expected_sha256=_CODESIGN_SHA256,
            expected_bytes=_CODESIGN_BYTES,
            failure="NETWORK_ISOLATION_NOT_RUN:codesign-provenance",
        )
        _verify_swift_sandbox_signature(root, environment)
        compiler_before = _swift_network_probe_compiler_receipt()
        sdk_identity_before = _swift_network_probe_sdk_identity()
        build_root = root / "network-probe-build"
        build_root.mkdir(mode=0o700)
        candidate = build_root / _SANDBOX_NETWORK_PROBE_BINARY_NAME
        compile_command = [
            str(_SANDBOX_EXEC),
            "-p",
            _SANDBOX_EXEC_POLICY,
            str(compiler_before["path"]),
            "-x",
            "c",
            "-std=c17",
            "-target",
            "arm64-apple-macosx26.0",
            "-Os",
            "-fno-ident",
            "-isysroot",
            str(_SWIFT_SDK_ROOT),
            "-Wl,-dead_strip",
            "-o",
            str(candidate),
            "-",
        ]
        _run_swift_build_step(
            compile_command,
            cwd=build_root,
            environment=environment,
            timeout=120,
            failure="NETWORK_ISOLATION_NOT_RUN:probe-build",
            input_text=_SANDBOX_NETWORK_PROBE_SOURCE,
        )
        compiler_after = _swift_network_probe_compiler_receipt()
        sdk_identity_after = _swift_network_probe_sdk_identity()
        if compiler_before != compiler_after or sdk_identity_before != sdk_identity_after:
            raise RouteError("NETWORK_ISOLATION_NOT_RUN:probe-toolchain-changed")
        _verify_swift_network_probe_binary(
            candidate,
            expected_mode="0755",
            root=root,
            environment=environment,
        )
        sealed, execution_seal, mach_o = _seal_swift_network_probe_binary(
            candidate,
            root=root,
            environment=environment,
        )
        binary_before, mach_o_before = _verify_swift_network_probe_seal(
            sealed,
            execution_seal,
            root=root,
            environment=environment,
        )
        probe = _run_swift_build_step(
            [str(_SANDBOX_EXEC), "-p", _SANDBOX_EXEC_POLICY, str(sealed)],
            cwd=root,
            environment=environment,
            timeout=30,
            failure="NETWORK_ISOLATION_NOT_RUN:socket-probe",
        )
        if probe.stdout != "NETWORK_DENIED:1\n" or probe.stderr != "":
            raise RouteError("NETWORK_ISOLATION_NOT_RUN:socket-probe-result")
        binary_after, mach_o_after = _verify_swift_network_probe_seal(
            sealed,
            execution_seal,
            root=root,
            environment=environment,
        )
        sandbox_after, sandbox_identity_after = _verified_swift_system_tool(
            _SANDBOX_EXEC,
            expected_sha256=_SANDBOX_EXEC_SHA256,
            expected_bytes=_SANDBOX_EXEC_BYTES,
            failure="NETWORK_ISOLATION_NOT_RUN:sandbox-exec-provenance",
        )
        verifier_after, verifier_identity_after = _verified_swift_system_tool(
            _CODESIGN,
            expected_sha256=_CODESIGN_SHA256,
            expected_bytes=_CODESIGN_BYTES,
            failure="NETWORK_ISOLATION_NOT_RUN:codesign-provenance",
        )
        _verify_swift_sandbox_signature(root, environment)
        if (
            sandbox_before != sandbox_after
            or sandbox_identity_before != sandbox_identity_after
            or verifier_before != verifier_after
            or verifier_identity_before != verifier_identity_after
            or binary_before != binary_after
            or mach_o != mach_o_before
            or mach_o != mach_o_after
            or hashlib.sha256(_SANDBOX_NETWORK_PROBE_SOURCE.encode("utf-8")).hexdigest()
            != _SANDBOX_NETWORK_PROBE_SOURCE_SHA256
        ):
            raise RouteError("NETWORK_ISOLATION_NOT_RUN:probe-identity-changed")
    except (OSError, RouteError) as error:
        if isinstance(error, RouteError) and str(error).startswith("NETWORK_ISOLATION_NOT_RUN"):
            raise
        raise RouteError("NETWORK_ISOLATION_NOT_RUN:unavailable") from error
    receipt: dict[str, Any] = {
        "status": "PASSED",
        "scope": "swift-build-process-tree",
        "sandbox": {**sandbox_after, "cdhash_full": _SANDBOX_EXEC_CDHASH_FULL},
        "verifier": verifier_after,
        "policy": {
            "text": _SANDBOX_EXEC_POLICY,
            "sha256": "sha256:" + hashlib.sha256(policy_bytes).hexdigest(),
            "bytes": len(policy_bytes),
        },
        "probe": {
            "result": "NETWORK_DENIED:1",
            "source": {
                "text": _SANDBOX_NETWORK_PROBE_SOURCE,
                "sha256": "sha256:" + _SANDBOX_NETWORK_PROBE_SOURCE_SHA256,
                "bytes": _SANDBOX_NETWORK_PROBE_SOURCE_BYTES,
            },
            "build": {
                "environment_policy": "sanitized-swift-build-deterministic-v1",
                "argv": list(_SANDBOX_NETWORK_PROBE_BUILD_ARGV),
                "environment": dict(_SANDBOX_NETWORK_PROBE_BUILD_ENVIRONMENT),
                "compiler": compiler_after,
            },
            "binary": binary_after,
            "execution_seal": execution_seal,
            "mach_o": mach_o,
        },
    }
    execution_identity = {
        "policy_sha256": receipt["policy"]["sha256"],
        "sandbox": sandbox_after,
        "sandbox_identity": sandbox_identity_after,
        "verifier": verifier_after,
        "verifier_identity": verifier_identity_after,
        "compiler": compiler_after,
        "sdk_identity": sdk_identity_after,
        "probe_path": sealed,
        "probe_seal": execution_seal,
        "probe_binary": binary_after,
        "probe_mach_o": mach_o,
    }
    return receipt, execution_identity


def _require_current_swift_network_execution_identity(
    expected: dict[str, Any],
    *,
    root: Path,
    environment: dict[str, str],
) -> None:
    _require_swift_network_probe_build_environment(root, environment)
    expected_keys = {
        "policy_sha256",
        "sandbox",
        "sandbox_identity",
        "verifier",
        "verifier_identity",
        "compiler",
        "sdk_identity",
        "probe_path",
        "probe_seal",
        "probe_binary",
        "probe_mach_o",
    }
    if set(expected) != expected_keys:
        raise RouteError("NETWORK_ISOLATION_NOT_RUN:execution-identity-invalid")
    policy_bytes = _SANDBOX_EXEC_POLICY.encode("utf-8")
    policy_sha256 = "sha256:" + hashlib.sha256(policy_bytes).hexdigest()
    sandbox_before, sandbox_identity_before = _verified_swift_system_tool(
        _SANDBOX_EXEC,
        expected_sha256=_SANDBOX_EXEC_SHA256,
        expected_bytes=_SANDBOX_EXEC_BYTES,
        failure="NETWORK_ISOLATION_NOT_RUN:sandbox-exec-provenance",
    )
    verifier_before, verifier_identity_before = _verified_swift_system_tool(
        _CODESIGN,
        expected_sha256=_CODESIGN_SHA256,
        expected_bytes=_CODESIGN_BYTES,
        failure="NETWORK_ISOLATION_NOT_RUN:codesign-provenance",
    )
    _verify_swift_sandbox_signature(root, environment)
    compiler = _swift_network_probe_compiler_receipt()
    sdk_identity = _swift_network_probe_sdk_identity()
    probe_path = expected.get("probe_path")
    probe_seal = expected.get("probe_seal")
    if not isinstance(probe_path, Path) or not isinstance(probe_seal, dict):
        raise RouteError("NETWORK_ISOLATION_NOT_RUN:execution-identity-invalid")
    binary_before, mach_o_before = _verify_swift_network_probe_seal(
        probe_path,
        probe_seal,
        root=root,
        environment=environment,
    )
    probe = _run_swift_build_step(
        [str(_SANDBOX_EXEC), "-p", _SANDBOX_EXEC_POLICY, str(probe_path)],
        cwd=root,
        environment=environment,
        timeout=30,
        failure="NETWORK_ISOLATION_NOT_RUN:socket-probe-recheck",
    )
    if probe.stdout != "NETWORK_DENIED:1\n" or probe.stderr != "":
        raise RouteError("NETWORK_ISOLATION_NOT_RUN:socket-probe-recheck-result")
    binary_after, mach_o_after = _verify_swift_network_probe_seal(
        probe_path,
        probe_seal,
        root=root,
        environment=environment,
    )
    sandbox_after, sandbox_identity_after = _verified_swift_system_tool(
        _SANDBOX_EXEC,
        expected_sha256=_SANDBOX_EXEC_SHA256,
        expected_bytes=_SANDBOX_EXEC_BYTES,
        failure="NETWORK_ISOLATION_NOT_RUN:sandbox-exec-provenance",
    )
    verifier_after, verifier_identity_after = _verified_swift_system_tool(
        _CODESIGN,
        expected_sha256=_CODESIGN_SHA256,
        expected_bytes=_CODESIGN_BYTES,
        failure="NETWORK_ISOLATION_NOT_RUN:codesign-provenance",
    )
    _verify_swift_sandbox_signature(root, environment)
    observed = {
        "policy_sha256": policy_sha256,
        "sandbox": sandbox_after,
        "sandbox_identity": sandbox_identity_after,
        "verifier": verifier_after,
        "verifier_identity": verifier_identity_after,
        "compiler": compiler,
        "sdk_identity": sdk_identity,
        "probe_path": probe_path,
        "probe_seal": probe_seal,
        "probe_binary": binary_after,
        "probe_mach_o": mach_o_after,
    }
    # One opaque code for six before/after pairs and an eleven-key comparison
    # cannot say what moved, which is the difference between a gate that fails
    # closed and one that can be acted on. The names are appended to the code;
    # every condition that used to fail still fails, on exactly the same inputs.
    unstable = [
        name
        for name, before, after in (
            ("sandbox", sandbox_before, sandbox_after),
            ("sandbox_identity", sandbox_identity_before, sandbox_identity_after),
            ("verifier", verifier_before, verifier_after),
            ("verifier_identity", verifier_identity_before, verifier_identity_after),
            ("probe_binary", binary_before, binary_after),
            ("probe_mach_o", mach_o_before, mach_o_after),
        )
        if before != after
    ]
    mismatched = sorted(
        key for key in expected_keys if observed.get(key) != expected.get(key)
    )
    if unstable or mismatched:
        detail = ";".join(
            part
            for part in (
                "unstable=" + ",".join(unstable) if unstable else "",
                "mismatched=" + ",".join(mismatched) if mismatched else "",
            )
            if part
        )
        raise RouteError(
            "NETWORK_ISOLATION_NOT_RUN:execution-identity-changed:" + detail
        )


def _stable_secure_directory_chain_identity(
    chain: tuple[tuple[object, ...], ...],
) -> tuple[tuple[object, ...], ...]:
    """Retain path security identity while ignoring directory timestamp churn."""

    return tuple(identity[:-2] for identity in chain)


def _bounded_swift_object_store_paths(objects: Path) -> list[Path]:
    """Discover at most the configured object-store entry count plus one."""

    paths: list[Path] = []
    pending = [objects]
    while pending:
        directory = pending.pop()
        remaining = _SWIFT_DEPENDENCY_OBJECT_STORE_MAXIMUM_ENTRIES - len(paths)
        entries: list[Path] = []
        try:
            with os.scandir(directory) as iterator:
                for entry in iterator:
                    entries.append(Path(entry.path))
                    if len(entries) > remaining:
                        raise RouteError("SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_ENTRY_LIMIT_EXCEEDED")
        except RouteError:
            raise
        except OSError as error:
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_CHANGED") from error
        entries.sort(key=lambda item: item.name)
        paths.extend(entries)
        child_directories: list[Path] = []
        try:
            for path in entries:
                if stat.S_ISDIR(path.lstat().st_mode):
                    child_directories.append(path)
        except OSError as error:
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_CHANGED") from error
        pending.extend(reversed(child_directories))
    return paths


def _streaming_regular_file_sha256(
    path: Path,
    *,
    maximum_bytes: int,
    limit_failure: str,
) -> tuple[int, str]:
    """Hash one stable private regular file without materializing its content."""

    failure = "SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_CHANGED"
    try:
        before = path.lstat()
        if before.st_size > maximum_bytes:
            raise RouteError(limit_failure)
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            opened_before = os.fstat(descriptor)
            digest = hashlib.sha256()
            total = 0
            while chunk := os.read(descriptor, 1024 * 1024):
                total += len(chunk)
                if total > maximum_bytes:
                    raise RouteError(limit_failure)
                digest.update(chunk)
            opened_after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        after = path.lstat()
    except RouteError:
        raise
    except OSError as error:
        raise RouteError(failure) from error
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_uid,
        before.st_gid,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    if (
        identity
        != (
            opened_before.st_dev,
            opened_before.st_ino,
            opened_before.st_mode,
            opened_before.st_nlink,
            opened_before.st_uid,
            opened_before.st_gid,
            opened_before.st_size,
            opened_before.st_mtime_ns,
            opened_before.st_ctime_ns,
        )
        or identity
        != (
            opened_after.st_dev,
            opened_after.st_ino,
            opened_after.st_mode,
            opened_after.st_nlink,
            opened_after.st_uid,
            opened_after.st_gid,
            opened_after.st_size,
            opened_after.st_mtime_ns,
            opened_after.st_ctime_ns,
        )
        or identity
        != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_nlink,
            after.st_uid,
            after.st_gid,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        or not stat.S_ISREG(after.st_mode)
        or after.st_uid != os.getuid()
        or stat.S_IMODE(after.st_mode) & 0o022
        or after.st_nlink != 1
        or total != after.st_size
    ):
        raise RouteError(failure)
    return total, "sha256:" + digest.hexdigest()


def _swift_object_store_manifest(objects: Path) -> tuple[tuple[object, ...], ...]:
    """Return a stable path/content/inode manifest for one Git object store."""

    paths = _bounded_swift_object_store_paths(objects)
    metadata_before: dict[str, tuple[object, ...]] = {}
    manifest: list[tuple[object, ...]] = []
    aggregate_bytes = 0
    for path in paths:
        relative = path.relative_to(objects).as_posix()
        try:
            metadata = path.lstat()
        except OSError as error:
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_CHANGED") from error
        identity = (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_uid,
            metadata.st_gid,
            metadata.st_nlink,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        )
        metadata_before[relative] = identity
        if (
            stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_REPOSITORY_UNSAFE")
        if stat.S_ISDIR(metadata.st_mode):
            manifest.append(
                (
                    relative,
                    "directory",
                    metadata.st_dev,
                    metadata.st_ino,
                    metadata.st_mode,
                    metadata.st_uid,
                    metadata.st_gid,
                    metadata.st_nlink,
                    None,
                    None,
                )
            )
            continue
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_REPOSITORY_UNSAFE")
        if metadata.st_size > _SWIFT_DEPENDENCY_OBJECT_STORE_MAXIMUM_FILE_BYTES:
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_FILE_LIMIT_EXCEEDED")
        remaining_bytes = _SWIFT_DEPENDENCY_OBJECT_STORE_MAXIMUM_BYTES - aggregate_bytes
        if metadata.st_size > remaining_bytes:
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_BYTE_LIMIT_EXCEEDED")
        maximum_bytes = min(
            _SWIFT_DEPENDENCY_OBJECT_STORE_MAXIMUM_FILE_BYTES,
            remaining_bytes,
        )
        limit_failure = (
            "SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_BYTE_LIMIT_EXCEEDED"
            if remaining_bytes <= _SWIFT_DEPENDENCY_OBJECT_STORE_MAXIMUM_FILE_BYTES
            else "SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_FILE_LIMIT_EXCEEDED"
        )
        byte_count, digest = _streaming_regular_file_sha256(
            path,
            maximum_bytes=maximum_bytes,
            limit_failure=limit_failure,
        )
        aggregate_bytes += byte_count
        manifest.append(
            (
                relative,
                "file",
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_mode,
                metadata.st_uid,
                metadata.st_gid,
                metadata.st_nlink,
                byte_count,
                digest,
            )
        )

    observed_paths = _bounded_swift_object_store_paths(objects)
    if [path.relative_to(objects).as_posix() for path in observed_paths] != list(metadata_before):
        raise RouteError("SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_CHANGED")
    try:
        for path in observed_paths:
            relative = path.relative_to(objects).as_posix()
            metadata = path.lstat()
            observed = (
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_mode,
                metadata.st_uid,
                metadata.st_gid,
                metadata.st_nlink,
                metadata.st_size,
                metadata.st_mtime_ns,
                metadata.st_ctime_ns,
            )
            if observed != metadata_before[relative]:
                raise RouteError("SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_CHANGED")
    except OSError as error:
        raise RouteError("SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_CHANGED") from error
    return tuple(manifest)


def _swift_object_store_content_digest(
    manifest: tuple[tuple[object, ...], ...],
) -> str:
    portable_entries = [
        {
            "path": entry[0],
            "kind": entry[1],
            "mode": entry[4],
            "bytes": entry[8],
            "sha256": entry[9],
        }
        for entry in manifest
    ]
    return _canonical_digest(
        {
            "schema_version": _SWIFT_DEPENDENCY_OBJECT_STORE_MANIFEST_SCHEMA,
            "entries": portable_entries,
        }
    )


def _swift_object_store_manifest_receipt(
    manifest: tuple[tuple[object, ...], ...],
) -> dict[str, object]:
    files = [entry for entry in manifest if entry[1] == "file"]
    return {
        "manifest_schema": _SWIFT_DEPENDENCY_OBJECT_STORE_MANIFEST_SCHEMA,
        "entry_count": len(manifest),
        "file_count": len(files),
        "bytes": sum(cast(int, entry[8]) for entry in files),
        "manifest_sha256": _swift_object_store_content_digest(manifest),
    }


def _swift_standalone_object_store_identity(
    repository: Path,
    *,
    environment: dict[str, str],
    require_worktree: bool,
) -> tuple[tuple[tuple[object, ...], ...], frozenset[tuple[int, int]]]:
    if any(
        environment.get(name)
        for name in (
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            "GIT_OBJECT_DIRECTORY",
            "GIT_COMMON_DIR",
        )
    ):
        raise RouteError("SWIFT_ANALYZER_DEPENDENCY_ALTERNATE_OBJECT_STORE_FORBIDDEN")
    metadata_root = repository / ".git" if require_worktree else repository
    objects = metadata_root / "objects"
    metadata_before = _verify_secure_directory_chain(
        metadata_root,
        "SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_UNSAFE",
    )
    objects_before = _verify_secure_directory_chain(
        objects,
        "SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_UNSAFE",
    )
    alternate_paths = (
        objects / "info" / "alternates",
        objects / "info" / "http-alternates",
    )

    def require_no_alternates() -> None:
        for path in alternate_paths:
            try:
                path.lstat()
            except FileNotFoundError:
                continue
            except OSError as error:
                raise RouteError("SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_UNSAFE") from error
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_ALTERNATE_OBJECT_STORE_FORBIDDEN")

    require_no_alternates()
    manifest_before = _swift_object_store_manifest(objects)
    require_no_alternates()
    metadata_after = _verify_secure_directory_chain(
        metadata_root,
        "SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_CHANGED",
    )
    objects_after = _verify_secure_directory_chain(
        objects,
        "SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_CHANGED",
    )
    manifest_after = _swift_object_store_manifest(objects)
    if (
        _stable_secure_directory_chain_identity(metadata_after)
        != _stable_secure_directory_chain_identity(metadata_before)
        or _stable_secure_directory_chain_identity(objects_after)
        != _stable_secure_directory_chain_identity(objects_before)
        or manifest_after != manifest_before
    ):
        raise RouteError("SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_CHANGED")
    identities = frozenset(
        (cast(int, entry[2]), cast(int, entry[3]))
        for entry in manifest_after
        if entry[1] == "file"
    )
    return manifest_after, identities


def _verify_swift_git_repository(
    repository: Path,
    *,
    root: Path,
    environment: dict[str, str],
    require_worktree: bool,
    require_standalone_object_store: bool = True,
) -> dict[str, Any]:
    _verify_secure_directory_chain(repository, "SWIFT_ANALYZER_DEPENDENCY_REPOSITORY_UNSAFE")
    object_store_before = (
        _swift_standalone_object_store_identity(
            repository,
            environment=environment,
            require_worktree=require_worktree,
        )
        if require_standalone_object_store
        else None
    )
    revision = _run_verified_apple_git(
        ["-C", str(repository), "rev-parse", f"{_SWIFT_SYNTAX_REVISION}^{{commit}}"],
        cwd=root,
        environment=environment,
        timeout=30,
        failure="SWIFT_ANALYZER_DEPENDENCY_REVISION_FAILED",
    ).stdout.strip()
    if revision != _SWIFT_SYNTAX_REVISION:
        raise RouteError("SWIFT_ANALYZER_DEPENDENCY_REVISION_MISMATCH")
    _run_verified_apple_git(
        ["-C", str(repository), "fsck", "--strict", "--full", "--no-dangling"],
        cwd=root,
        environment=environment,
        timeout=300,
        failure="SWIFT_ANALYZER_DEPENDENCY_FSCK_FAILED",
    )
    if require_standalone_object_store:
        remotes = _run_verified_apple_git(
            ["-C", str(repository), "remote"],
            cwd=root,
            environment=environment,
            timeout=30,
            failure="SWIFT_ANALYZER_DEPENDENCY_REMOTE_INSPECTION_FAILED",
        ).stdout.splitlines()
        if remotes:
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_REMOTE_FORBIDDEN")
    metadata = _swift_git_metadata_manifest(repository, require_worktree=require_worktree)
    result: dict[str, Any] = {"git_metadata": metadata}
    if require_worktree:
        observed_head = _run_verified_apple_git(
            ["-C", str(repository), "rev-parse", "HEAD"],
            cwd=root,
            environment=environment,
            timeout=30,
            failure="SWIFT_ANALYZER_DEPENDENCY_REVISION_FAILED",
        ).stdout.strip()
        if observed_head != _SWIFT_SYNTAX_REVISION:
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_REVISION_MISMATCH")
        result = {**_swift_dependency_tree(repository), **result}
    if require_standalone_object_store:
        object_store_after = _swift_standalone_object_store_identity(
            repository,
            environment=environment,
            require_worktree=require_worktree,
        )
        if object_store_after != object_store_before:
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_CHANGED")
        result["object_store"] = {
            "policy": _SWIFT_DEPENDENCY_OBJECT_STORE_POLICY,
            "alternates": False,
            "hardlinks": False,
            **_swift_object_store_manifest_receipt(object_store_after[0]),
        }
    return result


def _swift_git_metadata_manifest(repository: Path, *, require_worktree: bool) -> dict[str, Any]:
    metadata_root = repository / ".git" if require_worktree else repository

    def discover() -> list[tuple[Path, tuple[object, ...]]]:
        files: list[tuple[Path, tuple[object, ...]]] = []
        try:
            for path in sorted(metadata_root.rglob("*"), key=lambda item: item.relative_to(metadata_root).as_posix()):
                relative = path.relative_to(metadata_root).as_posix()
                metadata = path.lstat()
                if (
                    stat.S_ISLNK(metadata.st_mode)
                    or metadata.st_uid != os.getuid()
                    or stat.S_IMODE(metadata.st_mode) & 0o022
                    or not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode))
                    or (stat.S_ISREG(metadata.st_mode) and metadata.st_nlink != 1)
                ):
                    raise RouteError(f"SWIFT_ANALYZER_DEPENDENCY_GIT_METADATA_UNSAFE:{relative}")
                if stat.S_ISREG(metadata.st_mode):
                    files.append(
                        (
                            path,
                            (
                                relative,
                                metadata.st_dev,
                                metadata.st_ino,
                                metadata.st_mode,
                                metadata.st_uid,
                                metadata.st_gid,
                                metadata.st_nlink,
                                metadata.st_size,
                                metadata.st_mtime_ns,
                                metadata.st_ctime_ns,
                            ),
                        )
                    )
        except OSError as error:
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_GIT_METADATA_UNSAFE") from error
        return files

    def capture() -> tuple[dict[str, Any], tuple[tuple[object, ...], ...], tuple[tuple[object, ...], ...]]:
        root_before = _verify_secure_directory_chain(
            metadata_root,
            "SWIFT_ANALYZER_DEPENDENCY_GIT_METADATA_UNSAFE",
        )
        discovered_before = discover()
        files: list[dict[str, Any]] = []
        total = 0
        for path, identity in discovered_before:
            relative = str(identity[0])
            data = _stable_read_regular_file(
                path,
                failure=f"SWIFT_ANALYZER_DEPENDENCY_GIT_METADATA_CHANGED:{relative}",
                maximum_bytes=100_000_000,
                minimum_bytes=0,
                require_nlink_one=True,
            )
            total += len(data)
            files.append(
                {
                    "path": relative,
                    "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
                    "bytes": len(data),
                }
            )
        discovered_after = discover()
        before_paths = [str(identity[0]) for _path, identity in discovered_before]
        after_paths = [str(identity[0]) for _path, identity in discovered_after]
        if after_paths != before_paths:
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_GIT_METADATA_PATH_SET_CHANGED")
        before_identities = tuple(identity for _path, identity in discovered_before)
        after_identities = tuple(identity for _path, identity in discovered_after)
        if after_identities != before_identities:
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_GIT_METADATA_CHANGED")
        root_after = _verify_secure_directory_chain(
            metadata_root,
            "SWIFT_ANALYZER_DEPENDENCY_GIT_METADATA_CHANGED",
        )
        # The chain is walked from / down, so it includes the per-user temporary
        # directory, whose mtime every other process on the machine moves. Only
        # the two timestamps are dropped: dev, ino, mode, uid, gid and the path
        # still have to match, and every capture re-checks that no component is
        # a symlink, a non-directory or group/world-writable. This is the
        # comparison _verify_swift_git_repository already makes on the same kind
        # of chain.
        if _stable_secure_directory_chain_identity(
            root_after
        ) != _stable_secure_directory_chain_identity(root_before):
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_GIT_METADATA_CHANGED")
        return (
            {
                "sha256": _canonical_digest({"files": files}),
                "file_count": len(files),
                "bytes": total,
            },
            root_after,
            after_identities,
        )

    # Two captures that have to agree. The three-attempt budget existed only to
    # absorb a capture voided by timestamp churn; now that churn cannot void
    # one, a third attempt could not observe anything the second did not.
    previous_receipt, previous_root, previous_files = capture()
    receipt, root_identity, file_identities = capture()
    if (
        receipt != previous_receipt
        or file_identities != previous_files
        or _stable_secure_directory_chain_identity(root_identity)
        != _stable_secure_directory_chain_identity(previous_root)
    ):
        raise RouteError("SWIFT_ANALYZER_DEPENDENCY_GIT_METADATA_CHANGED")
    return receipt


def _swift_dependency_tree_identity(value: dict[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in ("sha256", "file_count", "bytes")}


def _regular_file_identities(root: Path) -> frozenset[tuple[int, int]]:
    def discover() -> list[Path]:
        paths: list[Path] = []
        try:
            paths = sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
        except OSError as error:
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_REPOSITORY_UNSAFE") from error
        return paths

    paths = discover()
    identities: set[tuple[int, int]] = set()
    try:
        for path in paths:
            metadata = path.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) & 0o022
                or (stat.S_ISREG(metadata.st_mode) and metadata.st_nlink != 1)
            ):
                raise RouteError("SWIFT_ANALYZER_DEPENDENCY_REPOSITORY_UNSAFE")
            if stat.S_ISREG(metadata.st_mode):
                identities.add((metadata.st_dev, metadata.st_ino))
            elif not stat.S_ISDIR(metadata.st_mode):
                raise RouteError("SWIFT_ANALYZER_DEPENDENCY_REPOSITORY_UNSAFE")
    except OSError as error:
        raise RouteError("SWIFT_ANALYZER_DEPENDENCY_REPOSITORY_UNSAFE") from error
    if [item.relative_to(root).as_posix() for item in discover()] != [
        item.relative_to(root).as_posix() for item in paths
    ]:
        raise RouteError("SWIFT_ANALYZER_DEPENDENCY_REPOSITORY_PATH_SET_CHANGED")
    return frozenset(identities)


def _clone_verified_swift_dependency(
    source: Path,
    destination: Path,
    *,
    root: Path,
    environment: dict[str, str],
    source_has_worktree: bool,
    source_requires_standalone_object_store: bool = True,
) -> dict[str, Any]:
    source_before = _verify_swift_git_repository(
        source,
        root=root,
        environment=environment,
        require_worktree=source_has_worktree,
        require_standalone_object_store=source_requires_standalone_object_store,
    )
    source_identities_before = _regular_file_identities(source)
    _run_verified_apple_git(
        [
            "clone",
            "--no-local",
            "--no-hardlinks",
            "--no-checkout",
            str(source),
            str(destination),
        ],
        cwd=root,
        environment=environment,
        timeout=900,
        failure="SWIFT_ANALYZER_DEPENDENCY_CLONE_FAILED",
    )
    _run_verified_apple_git(
        ["-C", str(destination), "remote", "remove", "origin"],
        cwd=root,
        environment=environment,
        timeout=30,
        failure="SWIFT_ANALYZER_DEPENDENCY_REMOTE_REMOVAL_FAILED",
    )
    _run_verified_apple_git(
        ["-C", str(destination), "checkout", "--detach", _SWIFT_SYNTAX_REVISION],
        cwd=root,
        environment=environment,
        timeout=300,
        failure="SWIFT_ANALYZER_DEPENDENCY_CHECKOUT_FAILED",
    )
    dependency = _verify_swift_git_repository(
        destination,
        root=root,
        environment=environment,
        require_worktree=True,
    )
    source_after = _verify_swift_git_repository(
        source,
        root=root,
        environment=environment,
        require_worktree=source_has_worktree,
        require_standalone_object_store=source_requires_standalone_object_store,
    )
    source_identities_after = _regular_file_identities(source)
    if source_after != source_before or source_identities_after != source_identities_before:
        raise RouteError("SWIFT_ANALYZER_DEPENDENCY_SOURCE_CHANGED_DURING_CLONE")
    if source_identities_after.intersection(_regular_file_identities(destination)):
        raise RouteError("SWIFT_ANALYZER_DEPENDENCY_HARDLINK_FORBIDDEN")
    return dependency


def _open_swift_dependency_cache_lock(lock_path: Path) -> int:
    common_flags = getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    for _attempt in range(3):
        try:
            return os.open(lock_path, os.O_RDONLY | common_flags)
        except FileNotFoundError:
            try:
                return os.open(
                    lock_path,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | common_flags,
                    0o600,
                )
            except FileExistsError:
                continue
            except OSError as error:
                raise RouteError("SWIFT_ANALYZER_DEPENDENCY_CACHE_LOCK_UNAVAILABLE") from error
        except OSError as error:
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_CACHE_LOCK_UNAVAILABLE") from error
    raise RouteError("SWIFT_ANALYZER_DEPENDENCY_CACHE_LOCK_CHANGED")


def _ensure_swift_dependency_cache(
    package: Path,
    root: Path,
    environment: dict[str, str],
) -> tuple[Path, dict[str, Any]]:
    cache_base = _swift_dependency_cache_base()
    cache_key = _swift_dependency_cache_key()
    cache = cache_base / cache_key
    try:
        account_home = _swift_dependency_cache_home().resolve(strict=True)
        cache_base.relative_to(account_home)
    except (OSError, ValueError) as error:
        raise RouteError("SWIFT_ANALYZER_DEPENDENCY_CACHE_PATH_ESCAPE") from error
    try:
        cache_base.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as error:
        raise RouteError("SWIFT_ANALYZER_DEPENDENCY_CACHE_ROOT_UNAVAILABLE") from error
    base_identity = _verify_secure_directory_chain(cache_base, "SWIFT_ANALYZER_DEPENDENCY_CACHE_ROOT_UNSAFE")
    lock_path = cache_base / ".seed.lock"
    descriptor = _open_swift_dependency_cache_lock(lock_path)
    candidate_root: Path | None = None
    try:
        lock_metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(lock_metadata.st_mode)
            or lock_metadata.st_uid != os.getuid()
            or stat.S_IMODE(lock_metadata.st_mode) & 0o177 != 0
        ):
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_CACHE_LOCK_UNSAFE")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            lock_path_metadata = lock_path.lstat()
        except OSError as error:
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_CACHE_LOCK_CHANGED") from error
        if (
            lock_metadata.st_dev,
            lock_metadata.st_ino,
            lock_metadata.st_mode,
            lock_metadata.st_uid,
            lock_metadata.st_gid,
        ) != (
            lock_path_metadata.st_dev,
            lock_path_metadata.st_ino,
            lock_path_metadata.st_mode,
            lock_path_metadata.st_uid,
            lock_path_metadata.st_gid,
        ):
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_CACHE_LOCK_CHANGED")
        observed_base = _verify_secure_directory_chain(cache_base, "SWIFT_ANALYZER_DEPENDENCY_CACHE_ROOT_CHANGED")
        # Creating our lock file changes only the leaf directory's timestamps.
        # All path identities, modes, owners and parent timestamps stay bound.
        if (
            observed_base[:-1] != base_identity[:-1]
            or not observed_base
            or observed_base[-1][:-2] != base_identity[-1][:-2]
        ):
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_CACHE_ROOT_CHANGED")
        if cache.exists() or cache.is_symlink():
            dependency = _verify_swift_git_repository(
                cache,
                root=root,
                environment=environment,
                require_worktree=True,
            )
            return cache, _swift_dependency_cache_receipt(
                cache,
                cache_key,
                _swift_dependency_tree_identity(dependency),
            )

        seeds = (
            (package / ".build" / "checkouts" / "swift-syntax", True),
            (package / ".build" / "repositories" / "swift-syntax-e1f983d3", False),
        )
        selected = next(
            ((path, worktree) for path, worktree in seeds if path.is_dir()),
            None,
        )
        if selected is None:
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_OFFLINE_SEED_NOT_RUN")
        seed, seed_has_worktree = selected
        try:
            candidate_root = Path(tempfile.mkdtemp(prefix=".seed-", dir=cache_base))
        except OSError as error:
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_CACHE_SEED_UNAVAILABLE") from error
        candidate_root.chmod(0o700)
        candidate = candidate_root / cache_key
        dependency = _clone_verified_swift_dependency(
            seed,
            candidate,
            root=root,
            environment=environment,
            source_has_worktree=seed_has_worktree,
            source_requires_standalone_object_store=False,
        )
        _verify_swift_git_repository(
            candidate,
            root=root,
            environment=environment,
            require_worktree=True,
        )
        try:
            candidate.rename(cache)
            candidate_root.rmdir()
        except OSError as error:
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_CACHE_PUBLISH_FAILED") from error
        candidate_root = None
        published = _verify_swift_git_repository(
            cache,
            root=root,
            environment=environment,
            require_worktree=True,
        )
        if published != dependency:
            raise RouteError("SWIFT_ANALYZER_DEPENDENCY_CACHE_CHANGED_DURING_PUBLISH")
        return cache, _swift_dependency_cache_receipt(
            cache,
            cache_key,
            _swift_dependency_tree_identity(published),
        )
    finally:
        if candidate_root is not None:
            shutil.rmtree(candidate_root, ignore_errors=True)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _verify_swift_analyzer_binary(binary: Path, expected_digest: str | None = None) -> dict[str, Any]:
    try:
        binary = binary.absolute()
        _verify_secure_directory_chain(binary.parent, "SWIFT_ANALYZER_BINARY_PARENT_UNSAFE")
        data = _stable_read_regular_file(
            binary,
            failure="SWIFT_ANALYZER_BINARY_UNSAFE",
            maximum_bytes=_SWIFT_ANALYZER_BINARY_MAX_BYTES,
            require_nlink_one=True,
        )
        metadata = binary.lstat()
    except OSError as error:
        raise RouteError("SWIFT_ANALYZER_BINARY_MISSING") from error
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_size <= 0
        or metadata.st_size > _SWIFT_ANALYZER_BINARY_MAX_BYTES
        or stat.S_IMODE(metadata.st_mode) & 0o111 == 0
        or stat.S_IMODE(metadata.st_mode) & 0o022 != 0
        or metadata.st_nlink != 1
        or binary.resolve(strict=True) != binary
    ):
        raise RouteError("SWIFT_ANALYZER_BINARY_UNSAFE")
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    if expected_digest is not None and digest != expected_digest:
        raise RouteError("SWIFT_ANALYZER_BINARY_CHANGED")
    return {
        "name": "ElmosSwiftAnalyzer",
        "path": str(binary),
        "sha256": digest,
        "bytes": metadata.st_size,
        "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
        "nlink": metadata.st_nlink,
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
    }


def _seal_swift_analyzer_binary(source: Path, root: Path) -> tuple[Path, dict[str, Any]]:
    source_data = _stable_read_regular_file(
        source,
        failure="SWIFT_ANALYZER_BINARY_SOURCE_UNSAFE",
        maximum_bytes=_SWIFT_ANALYZER_BINARY_MAX_BYTES,
        require_nlink_one=True,
    )
    sealed = root / "ElmosSwiftAnalyzer"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(sealed, flags, 0o500)
        try:
            offset = 0
            while offset < len(source_data):
                offset += os.write(descriptor, source_data[offset:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        sealed.chmod(0o500)
        root.chmod(0o500)
        root_metadata = root.lstat()
    except OSError as error:
        raise RouteError("SWIFT_ANALYZER_BINARY_SEAL_FAILED") from error
    binary = _verify_swift_analyzer_binary(sealed)
    return sealed, {
        "policy": "private-nonwritable-execution-root-v1",
        "root": str(root),
        "mode": f"{stat.S_IMODE(root_metadata.st_mode):04o}",
        "uid": root_metadata.st_uid,
        "gid": root_metadata.st_gid,
        "device": root_metadata.st_dev,
        "inode": root_metadata.st_ino,
        "binary": binary,
    }


def _verify_swift_execution_seal(binary: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    seal = receipt.get("execution_seal")
    if not isinstance(seal, dict) or set(seal) != {
        "policy",
        "root",
        "mode",
        "uid",
        "gid",
        "device",
        "inode",
        "binary",
    }:
        raise RouteError("SWIFT_ANALYZER_EXECUTION_SEAL_INVALID")
    try:
        root = Path(str(seal["root"]))
        metadata = root.lstat()
    except OSError as error:
        raise RouteError("SWIFT_ANALYZER_EXECUTION_SEAL_CHANGED") from error
    observed_root = {
        "policy": "private-nonwritable-execution-root-v1",
        "root": str(root),
        "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
    }
    expected_root = {key: seal[key] for key in observed_root}
    if (
        observed_root != expected_root
        or seal["mode"] != "0500"
        or binary.parent != root
        or not isinstance(seal["binary"], dict)
    ):
        raise RouteError("SWIFT_ANALYZER_EXECUTION_SEAL_CHANGED")
    binary_observed = _verify_swift_analyzer_binary(binary, str(seal["binary"].get("sha256")))
    if binary_observed != seal["binary"] or binary_observed != receipt.get("binary"):
        raise RouteError("SWIFT_ANALYZER_EXECUTION_SEAL_CHANGED")
    return {**observed_root, "binary": binary_observed}


def _run_swift_build_step(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout: int,
    failure: str,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.PIPE if input_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
            start_new_session=True,
        )
    except OSError as error:
        raise RouteError(failure + ":process") from error
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout)
    except BaseException as error:
        cleanup_error, cleanup_diagnostics = _attempt_swift_build_session_cleanup(process)
        if cleanup_error is not None or cleanup_diagnostics:
            _add_swift_build_cleanup_notes(error, cleanup_error, cleanup_diagnostics)
        if isinstance(error, KeyboardInterrupt | SystemExit):
            raise
        if isinstance(cleanup_error, KeyboardInterrupt | SystemExit):
            raise cleanup_error from error
        if isinstance(error, OSError | subprocess.TimeoutExpired):
            converted = RouteError(failure + ":process")
            if cleanup_error is not None or cleanup_diagnostics:
                _add_swift_build_cleanup_notes(
                    converted,
                    cleanup_error,
                    cleanup_diagnostics,
                )
            raise converted from error
        raise
    known_members: dict[int, int] = {}
    # communicate() reaps an ordinarily completed leader before this
    # defense-in-depth residual-session scan. Darwin cannot atomically pin that
    # now-free numeric PID/SID; a reuse collision remains a platform boundary.
    try:
        session_empty = _wait_for_swift_build_session_exit(
            process.pid,
            deadline=time.monotonic() + _SWIFT_BUILD_POST_COMPLETION_TIMEOUT_SECONDS,
            known_members=known_members,
        )
    except BaseException as error:
        cleanup_error, cleanup_diagnostics = _attempt_swift_build_session_cleanup(
            process,
            known_members=known_members,
        )
        if cleanup_error is not None or cleanup_diagnostics:
            _add_swift_build_cleanup_notes(error, cleanup_error, cleanup_diagnostics)
        if isinstance(error, KeyboardInterrupt | SystemExit):
            raise
        if isinstance(cleanup_error, KeyboardInterrupt | SystemExit):
            raise cleanup_error from error
        if not isinstance(error, Exception):
            raise
        converted = RouteError(failure + ":process")
        if cleanup_error is not None or cleanup_diagnostics:
            _add_swift_build_cleanup_notes(
                converted,
                cleanup_error,
                cleanup_diagnostics,
            )
        raise converted from error
    if not session_empty:
        cleanup_error, cleanup_diagnostics = _attempt_swift_build_session_cleanup(
            process,
            known_members=known_members,
        )
        if isinstance(cleanup_error, KeyboardInterrupt | SystemExit):
            raise cleanup_error
        converted = RouteError(failure + ":process")
        if cleanup_error is not None or cleanup_diagnostics:
            _add_swift_build_cleanup_notes(
                converted,
                cleanup_error,
                cleanup_diagnostics,
            )
        raise converted
    completed = subprocess.CompletedProcess(command, cast(int, process.returncode), stdout, stderr)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-2_000:]
        raise RouteError(failure + ":" + detail)
    return completed


def _swift_build_process_ids_from_ps(deadline: float) -> tuple[int, ...]:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RuntimeError("swift build process-list deadline expired")
    try:
        completed = subprocess.run(
            [str(_PROCESS_LIST), "-axo", "pid="],
            check=False,
            capture_output=True,
            timeout=min(_SWIFT_BUILD_PROCESS_LIST_TIMEOUT_SECONDS, remaining),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError("swift build process-list command failed") from error
    if completed.returncode != 0 or completed.stderr.strip():
        raise RuntimeError("swift build process-list command failed")
    if len(completed.stdout) > _SWIFT_BUILD_MAXIMUM_PROCESS_LIST_BYTES:
        raise RuntimeError("swift build process-list output exceeded its bound")
    lines = completed.stdout.splitlines()
    if len(lines) > _SWIFT_BUILD_MAXIMUM_PROCESS_IDS:
        raise RuntimeError("swift build process-list count exceeded its bound")
    process_ids: set[int] = set()
    for line in lines:
        if time.monotonic() >= deadline:
            raise RuntimeError("swift build process-list deadline expired")
        fields = line.split()
        if len(fields) != 1:
            raise RuntimeError("swift build process-list output was malformed")
        try:
            pid = int(fields[0])
        except ValueError as error:
            raise RuntimeError("swift build process-list output was malformed") from error
        if pid > 0:
            process_ids.add(pid)
    if time.monotonic() >= deadline:
        raise RuntimeError("swift build process-list deadline expired")
    if len(process_ids) > _SWIFT_BUILD_MAXIMUM_PROCESS_IDS:
        raise RuntimeError("swift build process-list count exceeded its bound")
    return tuple(sorted(process_ids))


def _swift_build_process_ids_from_libproc(deadline: float) -> tuple[int, ...]:
    """Use Darwin's fixed-cap process API without spawning another process."""

    if deadline - time.monotonic() <= 0:
        raise RuntimeError("swift build process-list deadline expired")
    import ctypes

    try:
        library = ctypes.CDLL(str(_LIBPROC), use_errno=True)
        proc_listallpids = cast(Any, library.proc_listallpids)
        proc_listallpids.argtypes = [ctypes.c_void_p, ctypes.c_int]
        proc_listallpids.restype = ctypes.c_int
        buffer_type = ctypes.c_int32 * (_SWIFT_BUILD_MAXIMUM_PROCESS_IDS + 1)
        buffer = buffer_type()
        count = cast(
            int,
            proc_listallpids(
                ctypes.cast(buffer, ctypes.c_void_p),
                ctypes.sizeof(buffer),
            ),
        )
    except (AttributeError, OSError, ValueError) as error:
        raise RuntimeError("swift build libproc enumeration failed") from error
    if time.monotonic() > deadline:
        raise RuntimeError("swift build process-list deadline expired")
    if count < 0 or count >= len(buffer):
        raise RuntimeError("swift build libproc process count exceeded its bound")
    process_ids: set[int] = set()
    for index in range(count):
        if time.monotonic() >= deadline:
            raise RuntimeError("swift build process-list deadline expired")
        if buffer[index] > 0:
            process_ids.add(int(buffer[index]))
    if len(process_ids) > _SWIFT_BUILD_MAXIMUM_PROCESS_IDS:
        raise RuntimeError("swift build libproc process count exceeded its bound")
    return tuple(sorted(process_ids))


def _swift_build_process_ids(deadline: float) -> tuple[int, ...]:
    if sys.platform == "darwin":
        try:
            return _swift_build_process_ids_from_libproc(deadline)
        except Exception as primary_error:
            try:
                return _swift_build_process_ids_from_ps(deadline)
            except Exception as fallback_error:
                failure = RuntimeError("swift build process enumeration failed")
                failure.add_note(f"ps fallback: {fallback_error}")
                raise failure from primary_error
    return _swift_build_process_ids_from_ps(deadline)


def _swift_build_session_members(
    session_id: int,
    *,
    deadline: float | None = None,
) -> dict[int, int]:
    """Return exact live PID/PGID members of one isolated build session."""

    enumeration_deadline = deadline or (
        time.monotonic() + _SWIFT_BUILD_PROCESS_LIST_TIMEOUT_SECONDS
    )
    members: dict[int, int] = {}
    for pid in _swift_build_process_ids(enumeration_deadline):
        if time.monotonic() >= enumeration_deadline:
            raise RuntimeError("swift build session identity deadline expired")
        if pid <= 1 or pid == os.getpid():
            continue
        try:
            observed_session = os.getsid(pid)
        except ProcessLookupError:
            continue
        except PermissionError as error:
            raise RuntimeError("swift build session identity was inaccessible") from error
        if time.monotonic() >= enumeration_deadline:
            raise RuntimeError("swift build session identity deadline expired")
        if observed_session != session_id:
            continue
        try:
            process_group = os.getpgid(pid)
        except ProcessLookupError:
            continue
        except PermissionError as error:
            raise RuntimeError("swift build process-group identity was inaccessible") from error
        if time.monotonic() >= enumeration_deadline:
            raise RuntimeError("swift build session identity deadline expired")
        if process_group <= 1 or process_group == os.getpgrp():
            raise RuntimeError("swift build session escaped its isolation boundary")
        members[pid] = process_group
    return members


def _record_swift_build_cleanup_error(
    errors: list[str],
    context: str,
    error: BaseException,
) -> None:
    detail = f"{context}: {type(error).__name__}: {error}"
    if detail not in errors and len(errors) < 16:
        errors.append(detail)


def _signal_swift_build_member(
    session_id: int,
    pid: int,
    signal_number: int,
    known_members: dict[int, int],
    errors: list[str],
    *,
    deadline: float,
) -> bool | None:
    """Signal one member after identity checks, or return None at deadline.

    Darwin has no pidfd-equivalent that makes the last getsid-to-kill step
    atomic. The repeated identity checks narrow and detect PID reuse but cannot
    eliminate that final platform race for a moved-PGID descendant.
    """

    if time.monotonic() >= deadline:
        return None
    try:
        first_session = os.getsid(pid)
    except ProcessLookupError:
        known_members.pop(pid, None)
        return False
    except OSError as error:
        _record_swift_build_cleanup_error(errors, f"getsid({pid})", error)
        return True
    if first_session != session_id:
        known_members.pop(pid, None)
        return False
    if time.monotonic() >= deadline:
        return None
    try:
        process_group = os.getpgid(pid)
        if time.monotonic() >= deadline:
            return None
        second_session = os.getsid(pid)
    except ProcessLookupError:
        known_members.pop(pid, None)
        return False
    except OSError as error:
        _record_swift_build_cleanup_error(errors, f"identity({pid})", error)
        return True
    if second_session != session_id:
        known_members.pop(pid, None)
        return False
    if process_group <= 1 or process_group == os.getpgrp():
        _record_swift_build_cleanup_error(
            errors,
            f"identity({pid})",
            RuntimeError("unsafe process-group identity"),
        )
        return True
    known_members[pid] = process_group
    if time.monotonic() >= deadline:
        return None
    try:
        os.kill(pid, signal_number)
    except ProcessLookupError:
        known_members.pop(pid, None)
        return False
    except OSError as error:
        _record_swift_build_cleanup_error(errors, f"signal({pid})", error)
        return True
    if time.monotonic() >= deadline:
        return None
    try:
        after_session = os.getsid(pid)
    except ProcessLookupError:
        known_members.pop(pid, None)
        return False
    except OSError as error:
        _record_swift_build_cleanup_error(errors, f"post-signal getsid({pid})", error)
        return True
    if after_session != session_id:
        known_members.pop(pid, None)
        return False
    return True


def _signal_swift_build_session(
    session_id: int,
    signal_number: int,
    *,
    deadline: float,
    known_members: dict[int, int],
    errors: list[str],
) -> dict[int, int] | None:
    """Signal the original PGID and exact members that moved to other PGIDs."""

    if session_id <= 1 or session_id == os.getpid() or session_id == os.getpgrp():
        raise RuntimeError("unsafe swift build session identity")
    if time.monotonic() >= deadline:
        return None
    try:
        os.killpg(session_id, signal_number)
    except ProcessLookupError:
        pass
    except OSError as error:
        _record_swift_build_cleanup_error(errors, f"killpg({session_id})", error)
    if deadline - time.monotonic() <= 0:
        return None
    members: dict[int, int] | None
    try:
        members = _swift_build_session_members(session_id, deadline=deadline)
    except Exception as error:
        _record_swift_build_cleanup_error(errors, "session enumeration", error)
        members = None
    if members is not None:
        known_members.update(members)
    live_members: dict[int, int] = {}
    for pid in sorted(known_members, reverse=True):
        live = _signal_swift_build_member(
            session_id,
            pid,
            signal_number,
            known_members,
            errors,
            deadline=deadline,
        )
        if live is None:
            return None
        if live:
            live_members[pid] = known_members[pid]
    if members is None:
        return None
    return {**members, **live_members}


def _signal_known_swift_build_members(
    session_id: int,
    signal_number: int,
    known_members: dict[int, int],
    errors: list[str],
    *,
    deadline: float,
) -> bool:
    if time.monotonic() >= deadline:
        return False
    try:
        os.killpg(session_id, signal_number)
    except ProcessLookupError:
        pass
    except OSError as error:
        _record_swift_build_cleanup_error(errors, f"killpg({session_id})", error)
    for pid in sorted(known_members, reverse=True):
        live = _signal_swift_build_member(
            session_id,
            pid,
            signal_number,
            known_members,
            errors,
            deadline=deadline,
        )
        if live is None:
            return False
    return True


def _wait_for_swift_build_session_exit(
    session_id: int,
    *,
    deadline: float,
    known_members: dict[int, int],
) -> bool:
    """Require repeated empty snapshots; never reap the pinned leader here."""

    empty_snapshots = 0
    while time.monotonic() < deadline:
        try:
            members = _swift_build_session_members(session_id, deadline=deadline)
        except Exception:
            raise
        if members:
            known_members.update(members)
            return False
        else:
            empty_snapshots += 1
            if empty_snapshots >= _SWIFT_BUILD_REQUIRED_EMPTY_SNAPSHOTS:
                return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(_SWIFT_BUILD_SESSION_POLL_SECONDS, remaining))
    return False


def _quiesce_swift_build_session(
    session_id: int,
    signal_number: int,
    *,
    deadline: float,
    known_members: dict[int, int],
    errors: list[str],
) -> bool:
    empty_snapshots = 0
    while time.monotonic() < deadline:
        members = _signal_swift_build_session(
            session_id,
            signal_number,
            deadline=deadline,
            known_members=known_members,
            errors=errors,
        )
        if members is None or members:
            empty_snapshots = 0
        else:
            empty_snapshots += 1
            if empty_snapshots >= _SWIFT_BUILD_REQUIRED_EMPTY_SNAPSHOTS:
                return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(_SWIFT_BUILD_SESSION_POLL_SECONDS, remaining))
    return False


def _terminate_swift_build_session(
    process: subprocess.Popen[str],
    *,
    known_members: dict[int, int] | None = None,
) -> tuple[str, ...]:
    """Boundedly terminate and reap one verified command's POSIX session.

    Swift/system descendants may create their own process groups, so cleanup
    enumerates the isolated session. A descendant deliberately calling setsid()
    is outside POSIX session containment and is not treated as contained here.
    If both bounded enumerators fail before the first snapshot, an already
    moved-PGID member is unknowable: cleanup kills the original PGID and every
    last-known member, then fails closed without claiming absolute no-leak.
    """

    session_id = process.pid
    if session_id <= 1 or session_id == os.getpid() or session_id == os.getpgrp():
        raise RuntimeError("unsafe swift build session identity")
    members = dict(known_members or {})
    members.setdefault(session_id, session_id)
    errors: list[str] = []
    fatal_errors: list[str] = []
    started = time.monotonic()
    cleanup_deadline = started + _SWIFT_BUILD_CLEANUP_TIMEOUT_SECONDS
    session_deadline = cleanup_deadline - _SWIFT_BUILD_REAP_RESERVE_SECONDS
    final_signal_deadline = (
        session_deadline - _SWIFT_BUILD_FINAL_VERIFICATION_RESERVE_SECONDS
    )
    kill_deadline = final_signal_deadline - _SWIFT_BUILD_FINAL_SIGNAL_RESERVE_SECONDS
    termination_deadline = min(
        started + _SWIFT_BUILD_TERMINATION_GRACE_SECONDS,
        kill_deadline,
    )
    interrupted: BaseException | None = None
    session_clean = False
    try:
        session_clean = _quiesce_swift_build_session(
            session_id,
            signal.SIGTERM,
            deadline=termination_deadline,
            known_members=members,
            errors=errors,
        )
        if not session_clean:
            session_clean = _quiesce_swift_build_session(
                session_id,
                signal.SIGKILL,
                deadline=kill_deadline,
                known_members=members,
                errors=errors,
            )
    except BaseException as error:
        interrupted = _capture_swift_build_cleanup_exception(
            interrupted,
            errors,
            "initial session cleanup",
            error,
        )
    finally:
        if not session_clean:
            try:
                final_signals_complete = _signal_known_swift_build_members(
                    session_id,
                    signal.SIGKILL,
                    members,
                    errors,
                    deadline=final_signal_deadline,
                )
                if not final_signals_complete:
                    _record_swift_build_cleanup_error(
                        errors,
                        "final known-member signal",
                        RuntimeError("cleanup deadline expired"),
                    )
            except BaseException as error:
                interrupted = _capture_swift_build_cleanup_exception(
                    interrupted,
                    errors,
                    "final known-member signal",
                    error,
                )
            if process.returncode is None and time.monotonic() < final_signal_deadline:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                except BaseException as error:
                    interrupted = _capture_swift_build_cleanup_exception(
                        interrupted,
                        errors,
                        "direct process kill",
                        error,
                    )
            elif process.returncode is None:
                _record_swift_build_cleanup_error(
                    errors,
                    "direct process kill",
                    RuntimeError("cleanup deadline expired"),
                )
            try:
                session_clean = _quiesce_swift_build_session(
                    session_id,
                    signal.SIGKILL,
                    deadline=session_deadline,
                    known_members=members,
                    errors=errors,
                )
            except BaseException as error:
                interrupted = _capture_swift_build_cleanup_exception(
                    interrupted,
                    errors,
                    "final session verification",
                    error,
                )
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except BaseException as error:
                    interrupted = _capture_swift_build_cleanup_exception(
                        interrupted,
                        errors,
                        "process stream close",
                        error,
                    )
                    fatal_errors.append("process stream close failed")
        process_reaped = False
        attempts = 0
        while attempts < 2 and time.monotonic() <= cleanup_deadline:
            attempts += 1
            try:
                process.wait(timeout=max(0.0, cleanup_deadline - time.monotonic()))
                process_reaped = True
                break
            except BaseException as error:
                interrupted = _capture_swift_build_cleanup_exception(
                    interrupted,
                    errors,
                    "direct process reap",
                    error,
                )
        if not process_reaped:
            fatal_errors.append("direct process was not reaped")
    if not session_clean:
        fatal_errors.append("session was not proven empty before cleanup deadline")
    if interrupted is not None:
        for detail in (*errors, *fatal_errors):
            interrupted.add_note(detail)
        raise interrupted
    if fatal_errors:
        failure = RuntimeError("swift build process-tree cleanup failed")
        for detail in (*errors, *fatal_errors):
            failure.add_note(detail)
        raise failure
    return tuple(errors)


def _capture_swift_build_cleanup_exception(
    interrupted: BaseException | None,
    errors: list[str],
    context: str,
    error: BaseException,
) -> BaseException | None:
    if isinstance(error, Exception):
        _record_swift_build_cleanup_error(errors, context, error)
        return interrupted
    if interrupted is None:
        return error
    interrupted.add_note(f"{context}: {type(error).__name__}: {error}")
    return interrupted


def _attempt_swift_build_session_cleanup(
    process: subprocess.Popen[str],
    *,
    known_members: dict[int, int] | None = None,
) -> tuple[BaseException | None, tuple[str, ...]]:
    try:
        diagnostics = _terminate_swift_build_session(process, known_members=known_members)
    except BaseException as error:
        return error, ()
    return None, diagnostics


def _add_swift_build_cleanup_notes(
    target: BaseException,
    cleanup_error: BaseException | None,
    cleanup_diagnostics: tuple[str, ...],
) -> None:
    if cleanup_error is not None:
        target.add_note(f"Swift build cleanup: {cleanup_error}")
        for detail in getattr(cleanup_error, "__notes__", ()):
            target.add_note(f"Swift build cleanup detail: {detail}")
    for detail in cleanup_diagnostics:
        target.add_note(f"Swift build cleanup diagnostic: {detail}")


def _prepare_swift_dependency_mirror(
    package: Path,
    root: Path,
    environment: dict[str, str],
) -> tuple[Path, dict[str, Any]]:
    try:
        root = root.resolve(strict=True)
    except OSError as error:
        raise RouteError("SWIFT_ANALYZER_BUILD_ROOT_UNSAFE") from error
    _verify_secure_directory_chain(root, "SWIFT_ANALYZER_BUILD_ROOT_UNSAFE")
    git_identity = _verify_apple_git(root, environment)
    cache, cache_receipt = _ensure_swift_dependency_cache(package, root, environment)
    mirror_parent = root / "verified-offline-mirror"
    mirror_parent.mkdir(mode=0o700)
    mirror = mirror_parent / "swift-syntax.git"
    dependency = _clone_verified_swift_dependency(
        cache,
        mirror,
        root=root,
        environment=environment,
        source_has_worktree=True,
    )
    cache_after = _verify_swift_git_repository(
        cache,
        root=root,
        environment=environment,
        require_worktree=True,
    )
    if _swift_dependency_tree_identity(dependency) != _swift_dependency_tree_identity(cache_after):
        raise RouteError("SWIFT_ANALYZER_DEPENDENCY_CACHE_CHANGED_DURING_CLONE")
    if cache_receipt != _swift_dependency_cache_receipt(
        cache,
        _swift_dependency_cache_key(),
        _swift_dependency_tree_identity(dependency),
    ):
        raise RouteError("SWIFT_ANALYZER_DEPENDENCY_CACHE_RECEIPT_INVALID")
    return mirror, {
        "seed": _SWIFT_DEPENDENCY_CACHE_SEED,
        "cache": cache_receipt,
        "git": git_identity,
        "identity": _SWIFT_DEPENDENCY_IDENTITY,
        "version": _SWIFT_SYNTAX_VERSION,
        "revision": _SWIFT_SYNTAX_REVISION,
        "sha256": dependency["sha256"],
        "file_count": dependency["file_count"],
        "bytes": dependency["bytes"],
    }


def _verify_swift_xcode_directory_chain(directory: Path, failure: str) -> tuple[tuple[object, ...], ...]:
    if not directory.is_absolute() or not directory.is_relative_to(_XCODE_ROOT):
        raise RouteError(failure)
    cursor = Path("/")
    identities: list[tuple[object, ...]] = []
    try:
        for part in directory.parts[1:]:
            cursor = cursor / part
            metadata = cursor.lstat()
            applications_exception = cursor == Path("/Applications") and (
                stat.S_IMODE(metadata.st_mode) == 0o775 and metadata.st_uid == 0 and metadata.st_gid == 80
            )
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != 0
                or (stat.S_IMODE(metadata.st_mode) & 0o022 and not applications_exception)
            ):
                raise RouteError(failure)
            identities.append(
                (
                    str(cursor),
                    metadata.st_dev,
                    metadata.st_ino,
                    metadata.st_mode,
                    metadata.st_uid,
                    metadata.st_gid,
                    metadata.st_mtime_ns,
                )
            )
        if directory.resolve(strict=True) != directory:
            raise RouteError(failure)
    except OSError as error:
        raise RouteError(failure) from error
    return tuple(identities)


def _swift_build_component_receipt(
    spec: tuple[object, ...],
    content_cache: dict[Path, bytes],
) -> dict[str, Any]:
    (
        role_value,
        lexical_value,
        resolved_value,
        link_target_value,
        sha256_value,
        bytes_value,
        mode_value,
        uid_value,
        gid_value,
        nlink_value,
    ) = spec
    role = str(role_value)
    if not isinstance(lexical_value, Path) or not isinstance(resolved_value, Path):
        raise RouteError("SWIFT_ANALYZER_BUILD_CLOSURE_SPEC_INVALID")
    lexical = lexical_value
    expected_resolved = resolved_value
    failure = f"SWIFT_ANALYZER_BUILD_CLOSURE_COMPONENT_INVALID:{role}"
    try:
        lexical_metadata = lexical.lstat()
        if link_target_value is None:
            if stat.S_ISLNK(lexical_metadata.st_mode):
                raise RouteError(failure)
        else:
            if (
                not stat.S_ISLNK(lexical_metadata.st_mode)
                or lexical_metadata.st_uid != 0
                or lexical_metadata.st_gid != 0
                or os.readlink(lexical) != link_target_value
                or Path(str(link_target_value)).is_absolute()
                or ".." in Path(str(link_target_value)).parts
            ):
                raise RouteError(failure)
        resolved = lexical.resolve(strict=True)
        if resolved != expected_resolved:
            raise RouteError(failure)
        _verify_swift_xcode_directory_chain(resolved.parent, failure)
        if resolved not in content_cache:
            content_cache[resolved] = _stable_read_regular_file(
                resolved,
                failure=failure,
                maximum_bytes=250_000_000,
                allowed_uids=frozenset({0}),
            )
        content = content_cache[resolved]
        metadata = resolved.lstat()
    except OSError as error:
        raise RouteError(failure) from error
    observed = {
        "role": role,
        "path": str(lexical),
        "resolved_path": str(resolved),
        "link_target": link_target_value,
        "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
        "nlink": metadata.st_nlink,
    }
    expected = {
        "role": role,
        "path": str(lexical),
        "resolved_path": str(expected_resolved),
        "link_target": link_target_value,
        "sha256": "sha256:" + str(sha256_value),
        "bytes": bytes_value,
        "mode": mode_value,
        "uid": uid_value,
        "gid": gid_value,
        "nlink": nlink_value,
    }
    if observed != expected:
        raise RouteError(failure)
    return observed


def _swift_build_tree_receipt(spec: tuple[object, ...]) -> dict[str, Any]:
    role_value, lexical_value, resolved_value, sha256_value, count_value, bytes_value = spec
    role = str(role_value)
    if not isinstance(lexical_value, Path) or not isinstance(resolved_value, Path):
        raise RouteError("SWIFT_ANALYZER_BUILD_CLOSURE_SPEC_INVALID")
    lexical = lexical_value
    expected_resolved = resolved_value
    failure = f"SWIFT_ANALYZER_BUILD_CLOSURE_TREE_INVALID:{role}"
    try:
        resolved = lexical.resolve(strict=True)
        if resolved != expected_resolved:
            raise RouteError(failure)
        root_identity = _verify_swift_xcode_directory_chain(resolved, failure)
    except OSError as error:
        raise RouteError(failure) from error

    def discover() -> list[Path]:
        files: list[Path] = []
        try:
            candidates = sorted(resolved.rglob("*"), key=lambda item: item.relative_to(resolved).as_posix())
            if len(candidates) > 10_000:
                raise RouteError(failure)
            for item in candidates:
                metadata = item.lstat()
                if (
                    stat.S_ISLNK(metadata.st_mode)
                    or metadata.st_uid != 0
                    or metadata.st_gid != 0
                    or stat.S_IMODE(metadata.st_mode) & 0o022
                    or not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode))
                ):
                    raise RouteError(failure)
                if stat.S_ISREG(metadata.st_mode):
                    files.append(item)
        except OSError as error:
            raise RouteError(failure) from error
        return files

    paths = discover()
    files: list[dict[str, Any]] = []
    total = 0
    for item in paths:
        relative = item.relative_to(resolved).as_posix()
        content = _stable_read_regular_file(
            item,
            failure=f"{failure}:{relative}",
            maximum_bytes=100_000_000,
            minimum_bytes=0,
            allowed_uids=frozenset({0}),
        )
        total += len(content)
        files.append(
            {
                "path": relative,
                "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }
        )
    if [item.relative_to(resolved).as_posix() for item in discover()] != [item["path"] for item in files]:
        raise RouteError(failure)
    if _verify_swift_xcode_directory_chain(resolved, failure) != root_identity:
        raise RouteError(failure)
    observed = {
        "role": role,
        "root": str(lexical),
        "sha256": _canonical_digest({"files": files}),
        "file_count": len(files),
        "bytes": total,
    }
    expected = {
        "role": role,
        "root": str(lexical),
        "sha256": "sha256:" + str(sha256_value),
        "file_count": count_value,
        "bytes": bytes_value,
    }
    if observed != expected:
        raise RouteError(failure)
    return observed


def _swift_build_closure_receipt() -> dict[str, Any]:
    try:
        sdk_link = _SWIFT_SDK_ROOT.lstat()
        if (
            not stat.S_ISLNK(sdk_link.st_mode)
            or sdk_link.st_uid != 0
            or sdk_link.st_gid != 0
            or os.readlink(_SWIFT_SDK_ROOT) != "MacOSX.sdk"
            or _SWIFT_SDK_ROOT.resolve(strict=True) != _SWIFT_SDK_RESOLVED_ROOT
        ):
            raise RouteError("SWIFT_ANALYZER_BUILD_CLOSURE_SDK_ROOT_INVALID")
    except OSError as error:
        raise RouteError("SWIFT_ANALYZER_BUILD_CLOSURE_SDK_ROOT_INVALID") from error
    content_cache: dict[Path, bytes] = {}
    return {
        "schema": _SWIFT_BUILD_CLOSURE_SCHEMA,
        "scope": _SWIFT_BUILD_CLOSURE_SCOPE,
        "compiler_runtime_soundness": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "components": [_swift_build_component_receipt(spec, content_cache) for spec in _SWIFT_BUILD_COMPONENT_SPECS],
        "trees": [_swift_build_tree_receipt(spec) for spec in _SWIFT_BUILD_TREE_SPECS],
    }


def _canonical_swift_build_closure_identity(closure: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": closure.get("schema"),
        "scope": closure.get("scope"),
        "compiler_runtime_soundness": closure.get("compiler_runtime_soundness"),
        "certification": closure.get("certification"),
        "components": [
            {key: component.get(key) for key in ("role", "link_target", "sha256", "bytes", "mode", "nlink")}
            for component in closure.get("components", [])
            if isinstance(component, dict)
        ],
        "trees": [
            {key: tree.get(key) for key in ("role", "sha256", "file_count", "bytes")}
            for tree in closure.get("trees", [])
            if isinstance(tree, dict)
        ],
    }


def _normalize_swift_build_mtimes(root: Path) -> None:
    failure = "SWIFT_ANALYZER_BUILD_MTIME_NORMALIZATION_FAILED"
    try:
        candidates = sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True)
        for item in candidates:
            metadata = item.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise RouteError(failure)
            os.utime(item, ns=(0, 0), follow_symlinks=False)
        os.utime(root, ns=(0, 0), follow_symlinks=False)
        for item in (root, *candidates):
            metadata = item.lstat()
            if metadata.st_mtime_ns != 0:
                raise RouteError(failure)
    except OSError as error:
        raise RouteError(failure) from error


def _require_swift_build_mtimes_normalized(root: Path) -> None:
    failure = "SWIFT_ANALYZER_BUILD_MTIME_NORMALIZATION_CHANGED"
    try:
        for item in (root, *sorted(root.rglob("*"), key=lambda candidate: candidate.as_posix())):
            metadata = item.lstat()
            if stat.S_ISLNK(metadata.st_mode) or metadata.st_mtime_ns != 0:
                raise RouteError(failure)
    except OSError as error:
        raise RouteError(failure) from error


def _canonical_swift_toolchain_identity(toolchain: dict[str, Any]) -> dict[str, Any]:
    profile = toolchain.get("profile")
    profile_items = profile if isinstance(profile, list) else []
    observed_build_closure = toolchain.get("build_closure")
    build_closure: dict[str, Any] = observed_build_closure if isinstance(observed_build_closure, dict) else {}
    return {
        "swiftc_sha256": toolchain.get("swiftc_sha256"),
        "swift_driver_sha256": toolchain.get("swift_driver_sha256"),
        "version": toolchain.get("version"),
        "profile": [item for item in profile_items if isinstance(item, str) and not item.startswith("sdk-path=")],
        "build_closure": _canonical_swift_build_closure_identity(build_closure),
    }


def _swift_toolchain_receipt(toolchain: ExactToolchain) -> dict[str, Any]:
    if (
        toolchain.language != "swift"
        or toolchain.auxiliary is None
        or toolchain.executable_sha256 is None
        or toolchain.auxiliary_sha256 is None
    ):
        raise RouteError("SWIFT_ANALYZER_DRIVER_PROVENANCE_REQUIRED")
    return {
        "swiftc": toolchain.executable,
        "swiftc_sha256": "sha256:" + toolchain.executable_sha256,
        "swift_driver": toolchain.auxiliary,
        "swift_driver_sha256": "sha256:" + toolchain.auxiliary_sha256,
        "version": toolchain.version,
        "profile": list(toolchain.profile),
        "build_closure": _swift_build_closure_receipt(),
    }


def _require_current_swift_toolchain(
    expected: ExactToolchain,
    *,
    expected_receipt: dict[str, Any] | None = None,
) -> ExactToolchain:
    try:
        observed = exact_toolchain("swift")
    except RouteError as error:
        raise RouteError("SWIFT_ANALYZER_TOOLCHAIN_CHANGED_DURING_BUILD") from error
    baseline_receipt = expected_receipt if expected_receipt is not None else _swift_toolchain_receipt(expected)
    if observed != expected or _swift_toolchain_receipt(observed) != baseline_receipt:
        raise RouteError("SWIFT_ANALYZER_TOOLCHAIN_CHANGED_DURING_BUILD")
    return observed


def _canonical_swift_analyzer_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    dependency = receipt["dependency"]
    mirror = dependency["mirror"]
    cache = mirror["cache"]
    network = receipt["network_isolation"]
    network_probe = network["probe"]
    probe_compiler = network_probe["build"]["compiler"]
    build = receipt["build"]
    binary = receipt["binary"]
    seal = receipt["execution_seal"]
    return {
        "schema_version": receipt["schema_version"],
        "kind": receipt["kind"],
        "source_inputs": receipt["source_inputs"],
        "dependency": {
            "identity": dependency["identity"],
            "version": dependency["version"],
            "revision": dependency["revision"],
            "sha256": dependency["sha256"],
            "file_count": dependency["file_count"],
            "bytes": dependency["bytes"],
            "mirror": {
                "seed": mirror["seed"],
                "identity": mirror["identity"],
                "version": mirror["version"],
                "revision": mirror["revision"],
                "sha256": mirror["sha256"],
                "file_count": mirror["file_count"],
                "bytes": mirror["bytes"],
                "git": {
                    "sha256": mirror["git"]["sha256"],
                    "version": mirror["git"]["version"],
                },
                "cache": {
                    key: cache[key]
                    for key in (
                        "cache_key",
                        "cache_schema",
                        "object_store_policy",
                        "identity",
                        "version",
                        "revision",
                        "seed",
                        "sha256",
                        "file_count",
                        "bytes",
                    )
                },
            },
        },
        "toolchain": _canonical_swift_toolchain_identity(receipt["toolchain"]),
        "build": {
            **build,
            "argv": ["<canonical-build-root>" if item == "/elmos/swift-analyzer" else item for item in build["argv"]],
        },
        "network_isolation": {
            "status": network["status"],
            "scope": network["scope"],
            "sandbox": {key: network["sandbox"][key] for key in ("sha256", "bytes", "mode", "nlink", "cdhash_full")},
            "verifier": {key: network["verifier"][key] for key in ("sha256", "bytes", "mode", "nlink")},
            "policy": network["policy"],
            "probe": {
                "result": network_probe["result"],
                "source": network_probe["source"],
                "build": {
                    "environment_policy": network_probe["build"]["environment_policy"],
                    "argv": network_probe["build"]["argv"],
                    "environment": network_probe["build"]["environment"],
                    "compiler": {
                        key: probe_compiler[key] for key in ("role", "link_target", "sha256", "bytes", "mode", "nlink")
                    },
                },
                "binary": {key: network_probe["binary"][key] for key in ("name", "sha256", "bytes", "mode", "nlink")},
                "execution_seal": {
                    "policy": network_probe["execution_seal"]["policy"],
                    "mode": network_probe["execution_seal"]["mode"],
                    "binary": {
                        key: network_probe["execution_seal"]["binary"][key]
                        for key in ("name", "sha256", "bytes", "mode", "nlink")
                    },
                },
                "mach_o": {
                    **{
                        key: network_probe["mach_o"][key]
                        for key in ("architecture", "file_type", "uuid", "cdhash_full")
                    },
                    "linked_libraries": ["system-libSystem"],
                },
            },
        },
        "binary": {key: binary[key] for key in ("name", "sha256", "bytes", "mode", "nlink")},
        "execution_seal": {
            "policy": seal["policy"],
            "mode": seal["mode"],
            "binary": {key: seal["binary"][key] for key in ("name", "sha256", "bytes", "mode", "nlink")},
        },
    }


def _build_swift_analyzer(toolchain: ExactToolchain, package: Path) -> tuple[Path, dict[str, Any]]:
    toolchain = _require_current_swift_toolchain(toolchain)
    toolchain_receipt = _swift_toolchain_receipt(toolchain)
    source_manifest = _swift_analyzer_input_manifest(package)
    temporary = tempfile.TemporaryDirectory(prefix="elmos-swift-analyzer-")
    root = Path(temporary.name).resolve(strict=True)
    root.chmod(0o700)
    snapshot = root / "package"
    snapshot.mkdir(mode=0o700)
    for item in source_manifest["files"]:
        relative = str(item["path"])
        destination = snapshot / relative
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        destination.write_bytes(source_manifest["contents"][relative])
        destination.chmod(0o600)
    home = root / "home"
    scratch_tmp = root / "tmp"
    cache = root / "cache"
    config = root / "config"
    security = root / "security"
    build = root / "build"
    for directory in (home, scratch_tmp, cache, config, security, build):
        directory.mkdir(mode=0o700)
    if toolchain.auxiliary is None:
        temporary.cleanup()
        raise RouteError("SWIFT_ANALYZER_DRIVER_PROVENANCE_REQUIRED")
    driver = Path(toolchain.auxiliary)
    environment = sanitized_subprocess_env(
        home=home,
        temp_dir=scratch_tmp,
        executable_dirs=(driver.resolve().parent, Path(toolchain.executable).resolve().parent),
    )
    environment.update(_SWIFT_DETERMINISTIC_ENVIRONMENT)
    mirror, mirror_receipt = _prepare_swift_dependency_mirror(package, root, environment)
    network_isolation, network_execution_identity = _verified_swift_network_isolation(root, environment)
    mirror_config = snapshot / ".swiftpm" / "configuration" / "mirrors.json"
    mirror_config.parent.mkdir(mode=0o700, parents=True)
    mirror_config.write_text(
        json.dumps(
            {
                "object": [
                    {
                        "mirror": mirror.as_uri(),
                        "original": "https://github.com/swiftlang/swift-syntax.git",
                    }
                ],
                "version": 1,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    mirror_config.chmod(0o600)
    _normalize_swift_build_mtimes(snapshot)
    _normalize_swift_build_mtimes(mirror)
    swift_command = [
        str(driver),
        "build",
        "--package-path",
        str(snapshot),
        "--cache-path",
        str(cache),
        "--config-path",
        str(config),
        "--security-path",
        str(security),
        "--scratch-path",
        str(build),
        "--manifest-cache",
        "none",
        "--disable-sandbox",
        "--disable-automatic-resolution",
        "-c",
        "release",
        "-Xswiftc",
        "-debug-prefix-map",
        "-Xswiftc",
        f"{root}=/elmos/swift-analyzer",
        "-Xswiftc",
        "-file-prefix-map",
        "-Xswiftc",
        f"{root}=/elmos/swift-analyzer",
        "-Xswiftc",
        "-file-compilation-dir",
        "-Xswiftc",
        "/elmos/swift-analyzer",
        "-Xswiftc",
        "-gnone",
        "-Xswiftc",
        "-no-serialize-debugging-options",
        "-Xcc",
        f"-fdebug-prefix-map={root}=/elmos/swift-analyzer",
        "-Xcc",
        f"-ffile-prefix-map={root}=/elmos/swift-analyzer",
        "-Xcc",
        f"-fmacro-prefix-map={root}=/elmos/swift-analyzer",
        "-Xcc",
        "-frandom-seed=elmos-swift-analyzer",
        "-Xlinker",
        "-no_uuid",
    ]
    command = [str(_SANDBOX_EXEC), "-p", _SANDBOX_EXEC_POLICY, *swift_command]
    try:
        _require_current_swift_network_execution_identity(
            network_execution_identity,
            root=root,
            environment=environment,
        )
    except RouteError:
        temporary.cleanup()
        raise
    build_error: RouteError | None = None
    try:
        _run_swift_build_step(
            command,
            cwd=snapshot,
            environment=environment,
            timeout=_SWIFT_ANALYZER_COLD_BUILD_TIMEOUT_SECONDS,
            failure="SWIFT_ANALYZER_BUILD_FAILED",
        )
    except RouteError as error:
        build_error = error
    try:
        _require_current_swift_network_execution_identity(
            network_execution_identity,
            root=root,
            environment=environment,
        )
    except RouteError:
        temporary.cleanup()
        raise
    if build_error is not None:
        temporary.cleanup()
        raise build_error
    try:
        _require_current_swift_toolchain(toolchain, expected_receipt=toolchain_receipt)
    except RouteError:
        temporary.cleanup()
        raise
    _require_swift_build_mtimes_normalized(snapshot)
    _require_swift_build_mtimes_normalized(mirror)
    snapshot_manifest = _swift_analyzer_input_manifest(snapshot)
    current_manifest = _swift_analyzer_input_manifest(package)
    if (
        snapshot_manifest["sha256"] != source_manifest["sha256"]
        or current_manifest["sha256"] != source_manifest["sha256"]
    ):
        temporary.cleanup()
        raise RouteError("SWIFT_ANALYZER_INPUT_CHANGED_DURING_BUILD")
    dependency = _swift_dependency_tree(build / "checkouts" / "swift-syntax")
    binary_candidate = build / "release" / "ElmosSwiftAnalyzer"
    if binary_candidate.is_symlink():
        temporary.cleanup()
        raise RouteError("SWIFT_ANALYZER_BINARY_UNSAFE")
    binary = binary_candidate.resolve(strict=True)
    if not binary.is_relative_to(build.resolve()):
        temporary.cleanup()
        raise RouteError("SWIFT_ANALYZER_BINARY_PATH_ESCAPE")
    sealed_binary, execution_seal = _seal_swift_analyzer_binary(binary, root)
    binary_receipt = execution_seal["binary"]
    receipt = {
        "schema_version": "1.0.0",
        "kind": _SWIFT_ANALYZER_KIND,
        "source_inputs": {
            "sha256": source_manifest["sha256"],
            "files": source_manifest["files"],
        },
        "dependency": {
            "identity": _SWIFT_DEPENDENCY_IDENTITY,
            "version": _SWIFT_SYNTAX_VERSION,
            "revision": _SWIFT_SYNTAX_REVISION,
            **dependency,
            "mirror": mirror_receipt,
        },
        "toolchain": toolchain_receipt,
        "network_isolation": network_isolation,
        "build": {
            "configuration": "release",
            "automatic_resolution": False,
            "manifest_cache": "none",
            "environment_policy": "minimal-empty-home-deterministic-v1",
            "deterministic_environment": dict(_SWIFT_DETERMINISTIC_ENVIRONMENT),
            "mtime_normalization": {
                "epoch_nanoseconds": 0,
                "scope": ["source-snapshot", "dependency-mirror"],
            },
            "reproducible_path_policy": "debug-file-macro-prefix-map-no-uuid-v1",
            "argv": [
                "<sandbox-exec>",
                "-p",
                "<deny-network-policy>",
                "<swift-driver>",
                "build",
                "--package-path",
                "<source-snapshot>",
                "--cache-path",
                "<isolated-cache>",
                "--config-path",
                "<isolated-config>",
                "--security-path",
                "<isolated-security>",
                "--scratch-path",
                "<isolated-build>",
                "--manifest-cache",
                "none",
                "--disable-sandbox",
                "--disable-automatic-resolution",
                "-c",
                "release",
                "-Xswiftc",
                "-debug-prefix-map",
                "-Xswiftc",
                "<build-root>=/elmos/swift-analyzer",
                "-Xswiftc",
                "-file-prefix-map",
                "-Xswiftc",
                "<build-root>=/elmos/swift-analyzer",
                "-Xswiftc",
                "-file-compilation-dir",
                "-Xswiftc",
                "<canonical-compilation-dir>",
                "-Xswiftc",
                "-gnone",
                "-Xswiftc",
                "-no-serialize-debugging-options",
                "-Xcc",
                "-fdebug-prefix-map=<build-root>=/elmos/swift-analyzer",
                "-Xcc",
                "-ffile-prefix-map=<build-root>=/elmos/swift-analyzer",
                "-Xcc",
                "-fmacro-prefix-map=<build-root>=/elmos/swift-analyzer",
                "-Xcc",
                "-frandom-seed=elmos-swift-analyzer",
                "-Xlinker",
                "-no_uuid",
            ],
        },
        "binary": binary_receipt,
        "execution_seal": execution_seal,
    }
    canonical_identity = _canonical_swift_analyzer_receipt(receipt)
    receipt["canonical_identity"] = {
        "sha256": _canonical_digest(canonical_identity),
        "receipt": canonical_identity,
    }
    global _SWIFT_ANALYZER_TEMPORARY
    _SWIFT_ANALYZER_TEMPORARY = temporary
    return sealed_binary, receipt


def _swift_toolchain_identity(toolchain: ExactToolchain) -> str:
    return _canonical_digest(
        {
            "language": toolchain.language,
            "version": toolchain.version,
            "executable": toolchain.executable,
            "auxiliary": toolchain.auxiliary,
            "profile": list(toolchain.profile),
            "executable_sha256": toolchain.executable_sha256,
            "auxiliary_sha256": toolchain.auxiliary_sha256,
        }
    )


def _permanent_swift_analyzer_failure(error: RouteError) -> bool:
    value = str(error)
    return value.startswith(
        (
            "SWIFT_ANALYZER_DRIVER_PROVENANCE_REQUIRED",
            "SWIFT_ANALYZER_INPUT_CHANGED_DURING_BUILD",
            "SWIFT_ANALYZER_TOOLCHAIN_CHANGED_DURING_BUILD",
            "NETWORK_ISOLATION_NOT_RUN:sandbox-exec-provenance",
            "NETWORK_ISOLATION_NOT_RUN:sandbox-exec-identity",
            "NETWORK_ISOLATION_NOT_RUN:sandbox-exec-signature",
            "NETWORK_ISOLATION_NOT_RUN:codesign-provenance",
            "NETWORK_ISOLATION_NOT_RUN:codesign-identity",
            "NETWORK_ISOLATION_NOT_RUN:probe-source",
            "NETWORK_ISOLATION_NOT_RUN:probe-compiler",
            "NETWORK_ISOLATION_NOT_RUN:probe-sdk",
            "NETWORK_ISOLATION_NOT_RUN:probe-build",
            "NETWORK_ISOLATION_NOT_RUN:probe-binary",
            "NETWORK_ISOLATION_NOT_RUN:probe-mach-o",
            "NETWORK_ISOLATION_NOT_RUN:probe-signature",
            "NETWORK_ISOLATION_NOT_RUN:probe-seal",
        )
    )


def _swift_analyzer(toolchain: ExactToolchain) -> tuple[Path, dict[str, Any]]:
    package = ENGINE_ROOT / "native" / "swift"
    current = _swift_analyzer_input_manifest(package)
    current_toolchain = _swift_toolchain_identity(toolchain)
    with _SWIFT_ANALYZER_LOCK:
        global _SWIFT_ANALYZER_BINARY, _SWIFT_ANALYZER_RECEIPT
        global _SWIFT_ANALYZER_FAILURE
        if _SWIFT_ANALYZER_FAILURE is not None:
            failed_inputs, failed_toolchain, failure = _SWIFT_ANALYZER_FAILURE
            if current["sha256"] != failed_inputs or current_toolchain != failed_toolchain:
                raise RouteError("SWIFT_ANALYZER_IDENTITY_CHANGED_AFTER_BUILD_FAILURE")
            raise RouteError(failure)
        if _SWIFT_ANALYZER_BINARY is None or _SWIFT_ANALYZER_RECEIPT is None:
            try:
                _SWIFT_ANALYZER_BINARY, _SWIFT_ANALYZER_RECEIPT = _build_swift_analyzer(toolchain, package)
            except RouteError as error:
                if _permanent_swift_analyzer_failure(error):
                    _SWIFT_ANALYZER_FAILURE = (
                        str(current["sha256"]),
                        current_toolchain,
                        str(error),
                    )
                raise
            except OSError as error:
                failure = "SWIFT_ANALYZER_BUILD_FILESYSTEM_FAILED"
                _SWIFT_ANALYZER_FAILURE = (
                    str(current["sha256"]),
                    current_toolchain,
                    failure,
                )
                raise RouteError(failure) from error
        if current["sha256"] != _SWIFT_ANALYZER_RECEIPT["source_inputs"]["sha256"]:
            raise RouteError("SWIFT_ANALYZER_INPUT_CHANGED_DURING_PROCESS")
        if _SWIFT_ANALYZER_RECEIPT.get("toolchain") != _swift_toolchain_receipt(toolchain):
            raise RouteError("SWIFT_ANALYZER_TOOLCHAIN_CHANGED_DURING_PROCESS")
        _verify_swift_execution_seal(_SWIFT_ANALYZER_BINARY, _SWIFT_ANALYZER_RECEIPT)
        return _SWIFT_ANALYZER_BINARY, json.loads(json.dumps(_SWIFT_ANALYZER_RECEIPT))


def swift_analyzer_build_receipt() -> dict[str, Any]:
    """Return a defensive copy of the verified per-process Swift build receipt."""

    _, receipt = _swift_analyzer(exact_toolchain("swift"))
    return receipt


def _cleanup_swift_analyzer() -> None:
    global _SWIFT_ANALYZER_TEMPORARY, _SWIFT_ANALYZER_BINARY, _SWIFT_ANALYZER_RECEIPT
    global _SWIFT_ANALYZER_FAILURE
    with _SWIFT_ANALYZER_LOCK:
        if _SWIFT_ANALYZER_TEMPORARY is not None:
            root = Path(_SWIFT_ANALYZER_TEMPORARY.name)
            try:
                root.chmod(0o700)
            except OSError:
                pass
            _SWIFT_ANALYZER_TEMPORARY.cleanup()
        _SWIFT_ANALYZER_TEMPORARY = None
        _SWIFT_ANALYZER_BINARY = None
        _SWIFT_ANALYZER_RECEIPT = None
        _SWIFT_ANALYZER_FAILURE = None


atexit.register(_cleanup_swift_analyzer)


def _bind_swift_analyzer_identity(value: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    analyzer_version = value.get("analyzer_version")
    if not isinstance(analyzer_version, str) or not analyzer_version:
        raise RouteError("SWIFT_ANALYZER_VERSION_REQUIRED")
    canonical_identity = _canonical_swift_analyzer_receipt(receipt)
    canonical = receipt.get("canonical_identity")
    canonical_digest = _canonical_digest(canonical_identity)
    if (
        not isinstance(canonical, dict)
        or canonical.get("receipt") != canonical_identity
        or canonical.get("sha256") != canonical_digest
    ):
        raise RouteError("SWIFT_ANALYZER_CANONICAL_IDENTITY_INVALID")
    canonical_toolchain = _canonical_swift_toolchain_identity(receipt["toolchain"])
    toolchain_digest = _canonical_digest(canonical_toolchain)
    build_closure_digest = _canonical_digest(canonical_toolchain["build_closure"])
    policy_digest = receipt["network_isolation"]["policy"]["sha256"]
    binary_digest = receipt["binary"]["sha256"]
    bound = dict(value)
    bound["analyzer_version"] = (
        f"{analyzer_version};source-inputs={receipt['source_inputs']['sha256']};"
        f"swift-driver={receipt['toolchain']['swift_driver_sha256']};"
        f"swift-syntax-tree={receipt['dependency']['sha256']};"
        f"canonical-receipt={canonical_digest};binary={binary_digest};"
        f"toolchain={toolchain_digest};build-closure={build_closure_digest};"
        f"network-policy={policy_digest}"
    )
    return bound


def _toolchain_profile_value(profile: tuple[str, ...], key: str) -> str:
    prefix = key + "="
    matches = [item[len(prefix) :] for item in profile if item.startswith(prefix)]
    if len(matches) != 1 or not matches[0]:
        raise RouteError(f"EXACT_TOOLCHAIN_PROFILE_VALUE_REQUIRED:{key}")
    return matches[0]


def _read_csharp_bound_file(
    path: Path,
    root: Path,
    *,
    failure: str,
    maximum_bytes: int,
) -> bytes:
    if root.is_symlink():
        raise RouteError(failure)
    try:
        relative = path.relative_to(root)
        resolved_root = root.resolve(strict=True)
    except (OSError, ValueError) as error:
        raise RouteError(failure) from error
    cursor = root
    try:
        for part in relative.parts:
            cursor = cursor / part
            metadata = cursor.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise RouteError(failure)
        before = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise RouteError(failure) from error
    if (
        not resolved.is_relative_to(resolved_root)
        or not stat.S_ISREG(before.st_mode)
        or before.st_size <= 0
        or before.st_size > maximum_bytes
        or stat.S_IMODE(before.st_mode) & 0o022 != 0
    ):
        raise RouteError(failure)
    try:
        content = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise RouteError(failure) from error
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_identity != after_identity or len(content) != after.st_size:
        raise RouteError(failure + "_CHANGED")
    return content


def _csharp_analyzer_input_manifest(engine: Path) -> dict[str, Any]:
    if engine.is_symlink():
        raise RouteError("CSHARP_ANALYZER_INPUT_ROOT_UNSAFE")
    try:
        resolved = engine.resolve(strict=True)
    except OSError as error:
        raise RouteError("CSHARP_ANALYZER_INPUT_ROOT_MISSING") from error
    if not resolved.is_dir():
        raise RouteError("CSHARP_ANALYZER_INPUT_ROOT_UNSAFE")
    files: list[dict[str, Any]] = []
    contents: dict[str, bytes] = {}
    for relative in _CSHARP_ANALYZER_INPUTS:
        content = _read_csharp_bound_file(
            engine / relative,
            engine,
            failure=f"CSHARP_ANALYZER_INPUT_UNSAFE:{relative}",
            maximum_bytes=_CSHARP_ANALYZER_MAX_INPUT_BYTES,
        )
        contents[relative] = content
        files.append(
            {
                "path": relative,
                "bytes": len(content),
                "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
            }
        )
    summary = {"files": files}
    return {
        "sha256": _canonical_digest(summary),
        "files": files,
        "contents": contents,
    }


def _csharp_package_cache_root() -> Path:
    return Path(pwd.getpwuid(os.getuid()).pw_dir) / ".nuget" / "packages"


def _csharp_verified_package_manifest(lock_bytes: bytes, cache_root: Path) -> dict[str, Any]:
    try:
        lock = json.loads(lock_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RouteError("CSHARP_ANALYZER_PACKAGE_LOCK_INVALID") from error
    if not isinstance(lock, dict):
        raise RouteError("CSHARP_ANALYZER_PACKAGE_LOCK_INVALID")
    dependencies = lock.get("dependencies")
    if lock.get("version") != 2 or not isinstance(dependencies, dict) or not dependencies:
        raise RouteError("CSHARP_ANALYZER_PACKAGE_LOCK_INVALID")
    packages: list[dict[str, Any]] = []
    contents: dict[str, bytes] = {}
    identities: set[tuple[str, str]] = set()
    for target_framework in sorted(dependencies):
        target_packages = dependencies[target_framework]
        if not isinstance(target_framework, str) or not target_framework or not isinstance(target_packages, dict):
            raise RouteError("CSHARP_ANALYZER_PACKAGE_LOCK_INVALID")
        for package_id in sorted(target_packages, key=str.casefold):
            metadata = target_packages[package_id]
            if (
                not isinstance(package_id, str)
                or re.fullmatch(r"[A-Za-z0-9_.-]+", package_id) is None
                or not isinstance(metadata, dict)
            ):
                raise RouteError("CSHARP_ANALYZER_PACKAGE_LOCK_INVALID")
            version = metadata.get("resolved")
            lock_content_hash = metadata.get("contentHash")
            if (
                not isinstance(version, str)
                or re.fullmatch(r"[A-Za-z0-9_.+-]+", version) is None
                or not isinstance(lock_content_hash, str)
            ):
                raise RouteError("CSHARP_ANALYZER_PACKAGE_LOCK_INVALID")
            try:
                decoded_lock_hash = base64.b64decode(lock_content_hash, validate=True)
            except (ValueError, binascii.Error) as error:
                raise RouteError("CSHARP_ANALYZER_PACKAGE_LOCK_INVALID") from error
            if len(decoded_lock_hash) != hashlib.sha512().digest_size:
                raise RouteError("CSHARP_ANALYZER_PACKAGE_LOCK_INVALID")
            identity = (package_id.casefold(), version.casefold())
            if identity in identities:
                raise RouteError("CSHARP_ANALYZER_PACKAGE_LOCK_DUPLICATED")
            identities.add(identity)
            normalized_id, normalized_version = identity
            package_directory = cache_root / normalized_id / normalized_version
            filename = f"{normalized_id}.{normalized_version}.nupkg"
            nupkg = package_directory / filename
            sha512_file = package_directory / f"{filename}.sha512"
            metadata_file = package_directory / ".nupkg.metadata"
            if any(path.is_symlink() for path in (nupkg, sha512_file, metadata_file)):
                raise RouteError(f"CSHARP_ANALYZER_PACKAGE_CACHE_UNSAFE:{package_id}:{version}")
            if not all(path.is_file() for path in (nupkg, sha512_file, metadata_file)):
                raise RouteError(f"CSHARP_ANALYZER_PACKAGE_CACHE_MISSING:{package_id}:{version}")
            package_bytes = _read_csharp_bound_file(
                nupkg,
                cache_root,
                failure=f"CSHARP_ANALYZER_PACKAGE_CACHE_UNSAFE:{package_id}:{version}:nupkg",
                maximum_bytes=_CSHARP_ANALYZER_MAX_OUTPUT_FILE_BYTES,
            )
            sha512_bytes = _read_csharp_bound_file(
                sha512_file,
                cache_root,
                failure=f"CSHARP_ANALYZER_PACKAGE_CACHE_UNSAFE:{package_id}:{version}:sha512",
                maximum_bytes=1_000,
            )
            metadata_bytes = _read_csharp_bound_file(
                metadata_file,
                cache_root,
                failure=f"CSHARP_ANALYZER_PACKAGE_CACHE_UNSAFE:{package_id}:{version}:metadata",
                maximum_bytes=10_000,
            )
            try:
                declared_sha512 = sha512_bytes.decode("ascii").strip()
                decoded_sha512 = base64.b64decode(declared_sha512, validate=True)
                package_metadata = json.loads(metadata_bytes)
            except (UnicodeDecodeError, ValueError, binascii.Error, json.JSONDecodeError) as error:
                raise RouteError(f"CSHARP_ANALYZER_PACKAGE_CACHE_INVALID:{package_id}:{version}") from error
            raw_sha512 = base64.b64encode(hashlib.sha512(package_bytes).digest()).decode("ascii")
            if len(decoded_sha512) != hashlib.sha512().digest_size or raw_sha512 != declared_sha512:
                raise RouteError(f"CSHARP_ANALYZER_PACKAGE_NUPKG_SHA512_MISMATCH:{package_id}:{version}")
            if package_metadata != {
                "version": 2,
                "contentHash": lock_content_hash,
                "source": "https://api.nuget.org/v3/index.json",
            }:
                raise RouteError(f"CSHARP_ANALYZER_PACKAGE_METADATA_MISMATCH:{package_id}:{version}")
            contents[filename] = package_bytes
            packages.append(
                {
                    "id": package_id,
                    "version": version,
                    "target_framework": target_framework,
                    "filename": filename,
                    "bytes": len(package_bytes),
                    "sha256": "sha256:" + hashlib.sha256(package_bytes).hexdigest(),
                    "raw_nupkg_sha512": raw_sha512,
                    "lock_content_hash": lock_content_hash,
                    "sha512_file_sha256": "sha256:" + hashlib.sha256(sha512_bytes).hexdigest(),
                    "metadata_sha256": "sha256:" + hashlib.sha256(metadata_bytes).hexdigest(),
                    "source": "https://api.nuget.org/v3/index.json",
                }
            )
    packages.sort(key=lambda item: (str(item["id"]).casefold(), str(item["version"]).casefold()))
    summary = {"packages": packages}
    return {
        "sha256": _canonical_digest(summary),
        "packages": packages,
        "contents": contents,
    }


def _verify_csharp_package_mirror(mirror: Path, expected: dict[str, Any]) -> None:
    packages = expected.get("packages")
    if not isinstance(packages, list):
        raise RouteError("CSHARP_ANALYZER_PACKAGE_MIRROR_INVALID")
    expected_paths = {str(item["filename"]) for item in packages}
    observed_paths: set[str] = set()
    for path in mirror.rglob("*"):
        relative = path.relative_to(mirror).as_posix()
        if path.is_symlink():
            raise RouteError(f"CSHARP_ANALYZER_PACKAGE_MIRROR_UNSAFE:{relative}")
        if path.is_file():
            observed_paths.add(relative)
        elif not path.is_dir():
            raise RouteError(f"CSHARP_ANALYZER_PACKAGE_MIRROR_UNSAFE:{relative}")
    if observed_paths != expected_paths:
        raise RouteError("CSHARP_ANALYZER_PACKAGE_MIRROR_PATH_SET_CHANGED")
    for item in packages:
        filename = str(item["filename"])
        content = _read_csharp_bound_file(
            mirror / filename,
            mirror,
            failure=f"CSHARP_ANALYZER_PACKAGE_MIRROR_UNSAFE:{filename}",
            maximum_bytes=_CSHARP_ANALYZER_MAX_OUTPUT_FILE_BYTES,
        )
        if (
            len(content) != item["bytes"]
            or "sha256:" + hashlib.sha256(content).hexdigest() != item["sha256"]
            or base64.b64encode(hashlib.sha512(content).digest()).decode("ascii") != item["raw_nupkg_sha512"]
        ):
            raise RouteError(f"CSHARP_ANALYZER_PACKAGE_MIRROR_CHANGED:{filename}")


def _csharp_toolchain_identity(toolchain: ExactToolchain) -> dict[str, Any]:
    if toolchain.language != "csharp" or toolchain.version != "10.0.301":
        raise RouteError("CSHARP_ANALYZER_TOOLCHAIN_IDENTITY_INVALID")
    bundle_identity = verify_csharp_toolchain(toolchain)
    declared = Path(toolchain.executable)
    if not declared.is_absolute():
        raise RouteError("CSHARP_ANALYZER_TOOLCHAIN_PATH_INVALID")
    try:
        declared_before = declared.lstat()
        resolved = declared.resolve(strict=True)
        before = resolved.lstat()
        content = resolved.read_bytes()
        after = resolved.lstat()
        declared_after = declared.lstat()
        resolved_after = declared.resolve(strict=True)
    except OSError as error:
        raise RouteError("CSHARP_ANALYZER_TOOLCHAIN_UNAVAILABLE") from error
    declared_identity = (
        declared_before.st_dev,
        declared_before.st_ino,
        declared_before.st_mode,
        declared_before.st_size,
        declared_before.st_mtime_ns,
    )
    if (
        declared_identity
        != (
            declared_after.st_dev,
            declared_after.st_ino,
            declared_after.st_mode,
            declared_after.st_size,
            declared_after.st_mtime_ns,
        )
        or resolved_after != resolved
    ):
        raise RouteError("CSHARP_ANALYZER_TOOLCHAIN_CHANGED")
    resolved_identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
    )
    if (
        resolved_identity
        != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
        )
        or len(content) != after.st_size
        or not stat.S_ISREG(after.st_mode)
        or stat.S_IMODE(after.st_mode) & 0o111 == 0
        or stat.S_IMODE(after.st_mode) & 0o022 != 0
    ):
        raise RouteError("CSHARP_ANALYZER_TOOLCHAIN_UNSAFE")
    executable_sha256 = "sha256:" + hashlib.sha256(content).hexdigest()
    if toolchain.executable_sha256 is not None and executable_sha256 != "sha256:" + toolchain.executable_sha256:
        raise RouteError("CSHARP_ANALYZER_TOOLCHAIN_DIGEST_MISMATCH")
    identity = {
        "language": toolchain.language,
        "version": toolchain.version,
        "declared_path": str(declared),
        "resolved_path": str(resolved),
        "executable_sha256": executable_sha256,
        "executable_bytes": len(content),
        "executable_mode": f"{stat.S_IMODE(after.st_mode):04o}",
        "profile": list(toolchain.profile),
        "bundle": bundle_identity,
    }
    return {**identity, "sha256": _canonical_digest(identity)}


def _csharp_analyzer_output_manifest(output: Path) -> dict[str, Any]:
    if output.is_symlink():
        raise RouteError("CSHARP_ANALYZER_OUTPUT_UNSAFE")
    try:
        resolved = output.resolve(strict=True)
    except OSError as error:
        raise RouteError("CSHARP_ANALYZER_OUTPUT_MISSING") from error
    if not resolved.is_dir():
        raise RouteError("CSHARP_ANALYZER_OUTPUT_UNSAFE")
    files: list[dict[str, Any]] = []
    total_bytes = 0
    for path in sorted(output.rglob("*"), key=lambda item: item.relative_to(output).as_posix()):
        relative = path.relative_to(output).as_posix()
        if path.is_symlink():
            raise RouteError(f"CSHARP_ANALYZER_OUTPUT_UNSAFE:{relative}")
        if path.is_dir():
            continue
        content = _read_csharp_bound_file(
            path,
            output,
            failure=f"CSHARP_ANALYZER_OUTPUT_UNSAFE:{relative}",
            maximum_bytes=_CSHARP_ANALYZER_MAX_OUTPUT_FILE_BYTES,
        )
        total_bytes += len(content)
        if total_bytes > _CSHARP_ANALYZER_MAX_OUTPUT_BYTES:
            raise RouteError("CSHARP_ANALYZER_OUTPUT_TOO_LARGE")
        files.append(
            {
                "path": relative,
                "bytes": len(content),
                "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
            }
        )
    paths = {str(item["path"]) for item in files}
    if _CSHARP_ANALYZER_ENTRYPOINT not in paths:
        raise RouteError("CSHARP_ANALYZER_ENTRYPOINT_MISSING")
    summary = {"files": files}
    return {
        "sha256": _canonical_digest(summary),
        "bytes": total_bytes,
        "file_count": len(files),
        "entrypoint": _CSHARP_ANALYZER_ENTRYPOINT,
        "files": files,
    }


def _verify_csharp_analyzer_output(output: Path, expected: dict[str, Any]) -> None:
    if _csharp_analyzer_output_manifest(output) != expected:
        raise RouteError("CSHARP_ANALYZER_OUTPUT_CHANGED")


def _run_csharp_build_step(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    failure: str,
) -> None:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=900,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RouteError(failure + ":process") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-2_000:]
        raise RouteError(failure + ":" + detail)


def _build_csharp_analyzer(
    toolchain: ExactToolchain,
    engine: Path,
) -> tuple[tempfile.TemporaryDirectory[str], Path, dict[str, Any]]:
    source_manifest = _csharp_analyzer_input_manifest(engine)
    toolchain_identity = _csharp_toolchain_identity(toolchain)
    package_lock_path = "src/Elmos.Dotnet.SemanticCli/packages.lock.json"
    package_cache = _csharp_package_cache_root()
    package_manifest = _csharp_verified_package_manifest(
        source_manifest["contents"][package_lock_path],
        package_cache,
    )
    temporary = tempfile.TemporaryDirectory(prefix="elmos-csharp-semantic-cli-")
    root = Path(temporary.name)
    try:
        root.chmod(0o700)
        snapshot = root / "dotnet-engine"
        snapshot.mkdir(mode=0o700)
        for item in source_manifest["files"]:
            relative = str(item["path"])
            destination = snapshot / relative
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            destination.write_bytes(source_manifest["contents"][relative])
            destination.chmod(0o600)
        home = root / "home"
        scratch = root / "tmp"
        http_cache = root / "http-cache"
        package_mirror = root / "package-source"
        output = root / "output"
        for directory in (home, scratch, http_cache, package_mirror, output):
            directory.mkdir(mode=0o700)
        packages = _csharp_package_restore_cache(
            toolchain, source_manifest, toolchain_identity, package_manifest
        )
        if packages is None:
            packages = root / "packages"
            packages.mkdir(mode=0o700)
        for item in package_manifest["packages"]:
            filename = str(item["filename"])
            destination = package_mirror / filename
            destination.write_bytes(package_manifest["contents"][filename])
            destination.chmod(0o600)
        _verify_csharp_package_mirror(package_mirror, package_manifest)
        environment = sanitized_subprocess_env(
            home=home,
            temp_dir=scratch,
            executable_dirs=(Path(toolchain.executable).resolve().parent,),
        )
        environment.update(
            {
                "DOTNET_CLI_HOME": str(home.resolve()),
                "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
                "DOTNET_NOLOGO": "1",
                "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
                "DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE": "1",
                "DOTNET_MULTILEVEL_LOOKUP": "0",
                "MSBUILDDISABLENODEREUSE": "1",
                "NUGET_PACKAGES": str(packages.resolve()),
                "NUGET_HTTP_CACHE_PATH": str(http_cache.resolve()),
            }
        )
        project = snapshot / "src" / "Elmos.Dotnet.SemanticCli" / "Elmos.Dotnet.SemanticCli.csproj"
        restore_command = [
            toolchain.executable,
            "restore",
            str(project),
            "--locked-mode",
            "--disable-parallel",
            "--packages",
            str(packages),
            "--source",
            str(package_mirror),
            "--no-http-cache",
            "--ignore-failed-sources",
            "--nologo",
        ]
        _run_csharp_build_step(
            restore_command,
            cwd=snapshot,
            environment=environment,
            failure="CSHARP_ANALYZER_RESTORE_FAILED",
        )
        build_command = [
            toolchain.executable,
            "build",
            str(project),
            "--configuration",
            "Release",
            "--no-restore",
            "--no-incremental",
            "--disable-build-servers",
            "--output",
            str(output),
            "--nologo",
        ]
        _run_csharp_build_step(
            build_command,
            cwd=snapshot,
            environment=environment,
            failure="CSHARP_ANALYZER_BUILD_FAILED",
        )
        snapshot_manifest = _csharp_analyzer_input_manifest(snapshot)
        current_manifest = _csharp_analyzer_input_manifest(engine)
        current_toolchain = _csharp_toolchain_identity(toolchain)
        if (
            snapshot_manifest["sha256"] != source_manifest["sha256"]
            or current_manifest["sha256"] != source_manifest["sha256"]
        ):
            raise RouteError("CSHARP_ANALYZER_INPUT_CHANGED_DURING_BUILD")
        if current_toolchain != toolchain_identity:
            raise RouteError("CSHARP_ANALYZER_TOOLCHAIN_CHANGED_DURING_BUILD")
        current_packages = _csharp_verified_package_manifest(
            current_manifest["contents"][package_lock_path],
            package_cache,
        )
        if current_packages["sha256"] != package_manifest["sha256"]:
            raise RouteError("CSHARP_ANALYZER_PACKAGE_CACHE_CHANGED_DURING_BUILD")
        _verify_csharp_package_mirror(package_mirror, package_manifest)
        output_manifest = _csharp_analyzer_output_manifest(output)
        binary = output / _CSHARP_ANALYZER_ENTRYPOINT
        receipt = {
            "schema_version": "1.0.0",
            "kind": _CSHARP_ANALYZER_KIND,
            "cache_scope": "process-local",
            "source_inputs": {
                "sha256": source_manifest["sha256"],
                "files": source_manifest["files"],
            },
            "toolchain": toolchain_identity,
            "packages": {
                "sha256": package_manifest["sha256"],
                "source_policy": "verified-nuget-org-flat-mirror-v1",
                "packages": package_manifest["packages"],
            },
            "restore": {
                "locked_mode": True,
                "disable_parallel": True,
                "http_cache": False,
                "environment_policy": "minimal-empty-home-v1",
                "argv": [
                    "<dotnet>",
                    "restore",
                    "<source-snapshot-project>",
                    "--locked-mode",
                    "--disable-parallel",
                    "--packages",
                    "<isolated-packages>",
                    "--source",
                    "<verified-flat-package-mirror>",
                    "--no-http-cache",
                    "--ignore-failed-sources",
                    "--nologo",
                ],
            },
            "build": {
                "configuration": "Release",
                "restore": False,
                "incremental": False,
                "build_servers": False,
                "repository_bin_obj_used": False,
                "argv": [
                    "<dotnet>",
                    "build",
                    "<source-snapshot-project>",
                    "--configuration",
                    "Release",
                    "--no-restore",
                    "--no-incremental",
                    "--disable-build-servers",
                    "--output",
                    "<isolated-output>",
                    "--nologo",
                ],
            },
            "output": output_manifest,
        }
    except RouteError:
        temporary.cleanup()
        raise
    except OSError as error:
        temporary.cleanup()
        raise RouteError("CSHARP_ANALYZER_BUILD_FILESYSTEM_FAILED") from error
    return temporary, binary, receipt


def _csharp_analyzer(toolchain: ExactToolchain) -> tuple[Path, dict[str, Any]]:
    engine = REPOSITORY_ROOT / "engines" / "dotnet-engine"
    with _CSHARP_ANALYZER_LOCK:
        global _CSHARP_ANALYZER_TEMPORARY, _CSHARP_ANALYZER_BINARY, _CSHARP_ANALYZER_RECEIPT
        global _CSHARP_ANALYZER_FAILURE
        current_inputs = _csharp_analyzer_input_manifest(engine)
        current_toolchain = _csharp_toolchain_identity(toolchain)
        if _CSHARP_ANALYZER_FAILURE is not None:
            failed_inputs, failed_toolchain, failure = _CSHARP_ANALYZER_FAILURE
            if current_inputs["sha256"] != failed_inputs or current_toolchain["sha256"] != failed_toolchain:
                raise RouteError("CSHARP_ANALYZER_IDENTITY_CHANGED_AFTER_BUILD_FAILURE")
            raise RouteError(failure)
        if _CSHARP_ANALYZER_BINARY is None or _CSHARP_ANALYZER_RECEIPT is None:
            # The build is process-local today, so a thousand-repository run
            # rebuilds an identical analyzer a thousand times.  Try the
            # cross-process cache first, keyed on precisely the two identities
            # this function already re-checks below -- the source inputs and the
            # toolchain -- so a hit is only possible when those match, and is
            # additionally re-verified against the stored output manifest.
            cache_key = _toolchain_build_cache_key(
                "csharp-analyzer",
                Path(toolchain.executable),
                salt=(str(current_inputs["sha256"]), str(current_toolchain["sha256"])),
            )
            cached = _load_persistent_analyzer_build(
                "csharp-analyzer", cache_key, _verify_csharp_analyzer_output
            )
            if cached is not None:
                cached_output, cached_receipt = cached
                _CSHARP_ANALYZER_BINARY = cached_output / _CSHARP_ANALYZER_ENTRYPOINT
                _CSHARP_ANALYZER_RECEIPT = cached_receipt
            else:
                try:
                    temporary, binary, receipt = _build_csharp_analyzer(toolchain, engine)
                except RouteError as error:
                    _CSHARP_ANALYZER_FAILURE = (
                        str(current_inputs["sha256"]),
                        str(current_toolchain["sha256"]),
                        str(error),
                    )
                    raise
                _CSHARP_ANALYZER_TEMPORARY = temporary
                _CSHARP_ANALYZER_BINARY = binary
                _CSHARP_ANALYZER_RECEIPT = receipt
                # Publishing is best-effort: a cache that cannot be written
                # costs a rebuild next time and nothing else.
                _store_persistent_analyzer_build("csharp-analyzer", cache_key, binary.parent, receipt)
        receipt = _CSHARP_ANALYZER_RECEIPT
        binary = _CSHARP_ANALYZER_BINARY
        if current_inputs["sha256"] != receipt["source_inputs"]["sha256"]:
            raise RouteError("CSHARP_ANALYZER_INPUT_CHANGED_DURING_PROCESS")
        if current_toolchain != receipt["toolchain"]:
            raise RouteError("CSHARP_ANALYZER_TOOLCHAIN_CHANGED_DURING_PROCESS")
        _verify_csharp_analyzer_output(binary.parent, receipt["output"])
        return binary, json.loads(json.dumps(receipt))


def csharp_analyzer_build_receipt() -> dict[str, Any]:
    """Return a defensive copy of the verified per-process C# build receipt."""

    _, receipt = _csharp_analyzer(exact_toolchain("csharp"))
    return receipt


def _cleanup_csharp_analyzer() -> None:
    global _CSHARP_ANALYZER_TEMPORARY, _CSHARP_ANALYZER_BINARY, _CSHARP_ANALYZER_RECEIPT
    global _CSHARP_ANALYZER_FAILURE
    with _CSHARP_ANALYZER_LOCK:
        if _CSHARP_ANALYZER_TEMPORARY is not None:
            _CSHARP_ANALYZER_TEMPORARY.cleanup()
        _CSHARP_ANALYZER_TEMPORARY = None
        _CSHARP_ANALYZER_BINARY = None
        _CSHARP_ANALYZER_RECEIPT = None
        _CSHARP_ANALYZER_FAILURE = None


atexit.register(_cleanup_csharp_analyzer)


def _bind_csharp_analyzer_identity(value: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    analyzer_version = value.get("analyzer_version")
    if not isinstance(analyzer_version, str) or not analyzer_version:
        raise RouteError("CSHARP_ANALYZER_VERSION_REQUIRED")
    bound = dict(value)
    bound["analyzer_version"] = (
        f"{analyzer_version};source-inputs={receipt['source_inputs']['sha256']};"
        f"dotnet={receipt['toolchain']['executable_sha256']};"
        f"dotnet-bundle={receipt['toolchain']['sha256']};"
        f"build-output={receipt['output']['sha256']}"
    )
    return bound


_TOOLCHAIN_BUILD_CACHE_SCHEMA = "toolchain-build-cache-v1"
_CARGO_BUILD_CACHE_SCHEMA = "cargo-build-cache-v1"


def _toolchain_build_cache_key(
    kind: str,
    executable: Path,
    files: Sequence[Path] = (),
    trees: Sequence[Path] = (),
    salt: Sequence[str] = (),
) -> str:
    """Content identity of everything that can change one analyzer build.

    A cache hit is only sound if the key covers every input the compiler reads.
    For these analyzers that set is closed and enumerable -- the compiler binary,
    the analyzer sources, any vendored dependency tree, and the flags the build
    is invoked with -- because every one of them is built offline with pinned or
    vendored dependencies and no ambient registry.  Two runs with equal keys are
    therefore required to produce equal output, which is what makes reusing the
    build directory evidence-preserving rather than a shortcut.

    Paths enter the digest relative to their own root and length-delimited, so a
    file named ``a/bc`` and a file named ``ab/c`` cannot collide into the same
    key by concatenation.
    """
    digest = hashlib.sha256()

    def absorb(label: str, value: str) -> None:
        digest.update(f"{len(label)}:{label}".encode())
        digest.update(f"{len(value)}:{value}".encode())

    absorb("schema", _TOOLCHAIN_BUILD_CACHE_SCHEMA)
    absorb("kind", kind)
    absorb("executable", _sha256_file(executable))
    for item in salt:
        absorb("salt", item)
    for path in files:
        absorb(f"file:{path.name}", _sha256_file(path) if path.is_file() else "absent")
    for tree in trees:
        if not tree.is_dir():
            absorb(f"tree:{tree.name}", "absent")
            continue
        for path in sorted(p for p in tree.rglob("*") if p.is_file() and not p.is_symlink()):
            absorb(f"tree:{path.relative_to(tree).as_posix()}", _sha256_file(path))
    return digest.hexdigest()


def _toolchain_build_cache(kind: str, key: str, names: Sequence[str]) -> tuple[Path, ...] | None:
    """Materialise a persistent, content-addressed build directory set.

    Returns ``None`` whenever the cache cannot be established safely, so a
    read-only or hostile home directory degrades to the previous per-call
    temporary directory instead of blocking analysis.
    """
    try:
        base = (
            Path(pwd.getpwuid(os.getuid()).pw_dir)
            / ".cache"
            / "elmos-polyglot-route-engine"
            / _TOOLCHAIN_BUILD_CACHE_SCHEMA
            / kind
        )
        base.mkdir(mode=0o700, parents=True, exist_ok=True)
        root = base / key
        directories = []
        for name in names:
            directory = root / name
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            directories.append(directory)
    except OSError:
        return None
    return tuple(directories)


def _csharp_package_restore_cache(
    toolchain: ExactToolchain,
    source_manifest: dict[str, Any],
    toolchain_identity: dict[str, Any],
    package_manifest: dict[str, Any],
) -> Path | None:
    """Persistent NuGet package directory for the C# analyzer restore.

    The C# analyzer was the last one still rebuilt from scratch in every
    process: the other toolchains reuse a content-addressed build directory,
    while this one only ever had the per-process globals, so a fresh process --
    which is what discovery spawns -- restored and extracted the whole Roslyn
    package set again.

    The argument that licenses the cargo, Go and Java caches holds here too, and
    the inputs are enumerated rather than assumed: the restore runs
    ``--locked-mode`` against a verified local mirror with ``--no-http-cache``
    and no reachable registry, so the extracted package set is a function of the
    lock file, the mirror contents and the SDK. All three are hashed into the
    key, so equal keys are required to yield equal restores.

    Only the restore is shared. The compile still runs in the per-run temporary
    directory under ``--no-incremental``, and its output is still verified
    against a manifest computed from the bytes it just produced, so nothing that
    reaches a receipt comes out of the cache.

    The whole source manifest enters the key, not just the files a restore is
    believed to read. Narrowing it to the project and lock files would be an
    optimisation resting on an assumption about MSBuild's evaluation, and a
    cache key that omits a real input returns a wrong build rather than a slow
    one. Analyzer sources change during development, not in production, so the
    misses this costs are the cheap ones.

    Returns ``None`` when no cache can be established, which leaves the previous
    per-run behaviour exactly as it was.
    """
    try:
        key = _toolchain_build_cache_key(
            "dotnet",
            Path(toolchain.executable),
            salt=(
                f"source-inputs={source_manifest['sha256']}",
                f"toolchain={toolchain_identity['sha256']}",
                f"package-mirror={package_manifest['sha256']}",
            ),
        )
    except OSError:
        # Same contract as _toolchain_build_cache: a key that cannot be computed
        # degrades to the per-run directory rather than failing the analysis.
        return None
    directories = _toolchain_build_cache("dotnet", key, ("packages",))
    return None if directories is None else directories[0]


def _cargo_build_cache_key(package: Path, executable: Path) -> str:
    return _toolchain_build_cache_key(
        "cargo",
        executable,
        files=(package / "Cargo.toml", package / "Cargo.lock", package / ".cargo" / "config.toml"),
        trees=(package / "vendor",),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cargo_build_cache(package: Path, executable: Path) -> tuple[Path, Path, dict[str, Any]] | None:
    """A persistent, content-addressed CARGO_HOME/CARGO_TARGET_DIR pair.

    Without this, every analyzer invocation gets a fresh empty target directory
    and cargo rebuilds the whole vendored dependency graph -- proc-macro crates
    included -- before analyzing a single function.  Measured on this crate that
    is ~17.8s cold against ~0.03s warm, and the analyzer is invoked once per
    *candidate function*, so a Rust file with eight functions pays that cost
    eight times.

    Returning ``None`` falls back to the previous per-call temporary directory,
    so a cache path that cannot be established safely never blocks analysis.
    """
    key = _cargo_build_cache_key(package, executable)
    directories = _toolchain_build_cache("cargo", key, ("cargo-home", "cargo-target"))
    if directories is None:
        return None
    cargo_home, cargo_target = directories
    receipt = {
        "cache_schema": _CARGO_BUILD_CACHE_SCHEMA,
        "cache_key": key,
        "cache_scope": "content-addressed-persistent",
    }
    return cargo_home, cargo_target, receipt


_ANALYZER_BUILD_RECEIPT = "build-receipt.json"


#: Reusing a *built analyzer binary* across processes is opt-in, unlike reusing
#: a compiler's own build directory.
#:
#: The difference is observable.  `test_csharp_analyzer_cache` asserts how many
#: build commands a single process issues, because "this process built the
#: analyzer it is about to run" is a property the C# and Swift paths currently
#: promise.  A cross-process cache makes that count depend on state outside the
#: process, which is a real semantic change -- not one to make silently, and not
#: one to hide by relaxing the tests that noticed it.  So it is enabled
#: deliberately, per deployment.
#:
#: Adopting it means updating those build-count assertions on purpose.
_ANALYZER_BINARY_CACHE_ENV = "ELMOS_ANALYZER_BINARY_CACHE"


def _analyzer_binary_cache_enabled() -> bool:
    return os.environ.get(_ANALYZER_BINARY_CACHE_ENV, "") == "1"


def _persistent_analyzer_root(kind: str, key: str) -> Path | None:
    if not _analyzer_binary_cache_enabled():
        return None
    if _toolchain_build_cache(kind, key, ()) is None:
        return None
    return (
        Path(pwd.getpwuid(os.getuid()).pw_dir)
        / ".cache"
        / "elmos-polyglot-route-engine"
        / _TOOLCHAIN_BUILD_CACHE_SCHEMA
        / kind
        / key
    )


def _load_persistent_analyzer_build(kind: str, key: str, verify: Any) -> tuple[Path, dict[str, Any]] | None:
    """Reuse a previously built analyzer tree, but only if it still verifies.

    The Swift and C# analyzers are built into a temporary directory that dies
    with the process, so every repository in a portfolio rebuilds them from
    scratch even though the inputs are identical.  The receipt those builds
    already produce is what makes reuse checkable: it carries a digest of every
    output file, and `verify` is the engine's own output verifier -- not a
    weaker check written for the cache.

    So a hit is not "trust the directory", it is "re-derive the output manifest
    and refuse if one byte moved".  A damaged or tampered entry is discarded and
    rebuilt rather than used.
    """
    root = _persistent_analyzer_root(kind, key)
    if root is None:
        return None
    output = root / "output"
    receipt_path = root / _ANALYZER_BUILD_RECEIPT
    if not output.is_dir() or not receipt_path.is_file():
        return None
    try:
        receipt = json.loads(receipt_path.read_text())
        verify(output, receipt["output"])
    except (OSError, ValueError, KeyError, TypeError, RouteError):
        shutil.rmtree(output, ignore_errors=True)
        receipt_path.unlink(missing_ok=True)
        return None
    return output, receipt


def _store_persistent_analyzer_build(
    kind: str,
    key: str,
    built_output: Path,
    receipt: Mapping[str, Any],
) -> Path | None:
    """Publish a freshly built analyzer tree for the next process to reuse.

    Copy-then-rename, so a concurrent reader never observes a partial tree, and
    the receipt is written only once the tree is in place, so a receipt always
    describes something that exists.
    """
    root = _persistent_analyzer_root(kind, key)
    if root is None:
        return None
    output = root / "output"
    staging = root / f".staging-{os.getpid()}"
    try:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.copytree(built_output, staging, symlinks=False)
        shutil.rmtree(output, ignore_errors=True)
        staging.rename(output)
        (root / _ANALYZER_BUILD_RECEIPT).write_text(json.dumps(dict(receipt), sort_keys=True))
    except (OSError, ValueError):
        shutil.rmtree(staging, ignore_errors=True)
        return None
    return output


def _go_build_cache_environment(helper: Path, executable: Path) -> dict[str, str] | None:
    """Persistent GOCACHE/GOPATH for the Go analyzer.

    `sanitized_subprocess_env` points HOME and XDG_CACHE_HOME at the per-call
    temporary directory, which is correct for isolation and catastrophic for
    cost: Go resolves its build cache under those, so `go run` recompiles the
    analyzer and every package it touches on every invocation.  Measured here
    that is 7.34s per call against 0.068s with a warm cache -- and the analyzer
    runs once per *candidate function*, so this is the single largest avoidable
    cost in the engine.

    Isolation is preserved rather than traded away: the cache directory is keyed
    on the Go binary's own digest and the analyzer source digest, so a different
    toolchain or a modified analyzer cannot read another key's artifacts, and
    the sandboxed HOME the rest of the environment relies on is untouched.
    """
    try:
        key = _toolchain_build_cache_key("go", executable, files=(helper,))
    except OSError:
        return None
    directories = _toolchain_build_cache("go", key, ("gocache", "gopath"))
    if directories is None:
        return None
    gocache, gopath = directories
    return {
        "GOCACHE": str(gocache.resolve()),
        "GOPATH": str(gopath.resolve()),
        "GOMODCACHE": str((gopath / "pkg" / "mod").resolve()),
        # The analyzer is stdlib-only and must stay that way; if it ever grows a
        # module dependency this is the line that has to be revisited rather
        # than silently reaching the network from inside an analysis.
        "GOFLAGS": "-mod=mod",
        "GOPROXY": "off",
        "GOTOOLCHAIN": "local",
    }


def _run(
    command: list[str],
    *,
    cwd: Path,
    timeout: int = 120,
    isolated_cargo: bool = False,
    cargo_package: Path | None = None,
    environment_overrides: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    executable = Path(command[0])
    executable = executable if executable.is_absolute() else (cwd / executable)
    try:
        with tempfile.TemporaryDirectory(prefix="elmos-native-process-") as temporary:
            root = Path(temporary)
            home = root / "home"
            scratch = root / "tmp"
            home.mkdir(mode=0o700)
            scratch.mkdir(mode=0o700)
            environment = sanitized_subprocess_env(
                home=home,
                temp_dir=scratch,
                executable_dirs=(executable.resolve().parent,),
            )
            if isolated_cargo:
                cached = _cargo_build_cache(cargo_package, executable) if cargo_package else None
                if cached is not None:
                    cargo_home, cargo_target, _cache_receipt = cached
                else:
                    cargo_home = root / "cargo-home"
                    cargo_target = root / "cargo-target"
                    cargo_home.mkdir(mode=0o700)
                    cargo_target.mkdir(mode=0o700)
                environment.update(
                    {
                        "CARGO_HOME": str(cargo_home.resolve()),
                        "CARGO_NET_OFFLINE": "true",
                        "CARGO_TARGET_DIR": str(cargo_target.resolve()),
                    }
                )
            if environment_overrides:
                environment.update(environment_overrides)
            completed = subprocess.run(
                command,
                cwd=cwd,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=environment,
            )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RouteError(f"NATIVE_ANALYZER_FAILED:{command[0]}:process") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-2_000:]
        raise RouteError(f"NATIVE_ANALYZER_FAILED:{command[0]}:{detail}")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RouteError(f"NATIVE_ANALYZER_INVALID_JSON:{command[0]}") from error
    if not isinstance(value, dict):
        raise RouteError("NATIVE_ANALYZER_OBJECT_REQUIRED")
    return value


def _run_trusted_swift_analyzer(
    binary: Path,
    receipt: dict[str, Any],
    arguments: list[str],
    *,
    allowed_domain_errors: frozenset[str],
) -> dict[str, Any]:
    """Run one receipt-bound Swift analyzer with exact error promotion.

    ``_run`` intentionally wraps every non-zero process result.  Only this
    Swift-specific trust boundary may unwrap a domain rejection, and only
    when the entire wrapped value binds the verified absolute executable and
    one complete allowlisted suffix. Unknown, forged, or multi-line output
    remains the original ``NATIVE_ANALYZER_FAILED`` value.
    """

    if not binary.is_absolute() or any(
        not reason or "\n" in reason or "\r" in reason for reason in allowed_domain_errors
    ):
        raise RouteError("SWIFT_ANALYZER_DOMAIN_ERROR_POLICY_INVALID")
    receipt_binary = receipt.get("binary")
    expected_digest = receipt_binary.get("sha256") if isinstance(receipt_binary, dict) else None
    if not isinstance(expected_digest, str):
        raise RouteError("SWIFT_ANALYZER_BINARY_RECEIPT_INVALID")
    before = _verify_swift_execution_seal(binary, receipt)
    try:
        value = _run([str(binary), *arguments], cwd=binary.parent)
    except RouteError as error:
        if _verify_swift_execution_seal(binary, receipt) != before:
            raise RouteError("SWIFT_ANALYZER_CHANGED_DURING_EXECUTION") from error
        wrapped = str(error)
        for reason in allowed_domain_errors:
            if wrapped == f"NATIVE_ANALYZER_FAILED:{binary}:{reason}":
                raise RouteError(reason) from error
        raise
    if _verify_swift_execution_seal(binary, receipt) != before:
        raise RouteError("SWIFT_ANALYZER_CHANGED_DURING_EXECUTION")
    return value


def _javascript_bound_content(
    path: Path,
    root: Path,
    *,
    expected_sha256: str,
    expected_bytes: int,
    failure: str,
) -> bytes:
    guarded = _read_csharp_bound_file(
        path,
        root,
        failure=failure,
        maximum_bytes=expected_bytes,
    )
    content = _stable_read_regular_file(
        path,
        failure=failure,
        maximum_bytes=expected_bytes,
        minimum_bytes=expected_bytes,
        allowed_uids=frozenset({os.getuid()}),
        require_nlink_one=True,
    )
    final = _read_csharp_bound_file(
        path,
        root,
        failure=failure,
        maximum_bytes=expected_bytes,
    )
    if (
        guarded != content
        or final != content
        or len(content) != expected_bytes
        or hashlib.sha256(content).hexdigest() != expected_sha256
    ):
        raise RouteError(failure)
    return content


def _run_trusted_php_analyzer(
    toolchain: ExactToolchain,
    source: Path,
    function_name: str,
    *,
    emitted_target: bool,
) -> dict[str, Any]:
    """Run the PHP frontend against a content-pinned copy of its own script.

    The analyzer is a *script*, not a built binary, so the thing that has to be
    pinned is the file the interpreter is about to read. It is read through the
    same triple-read the JavaScript analyzer uses -- guarded read, stable read
    with an fd-level stat, guarded read again -- and compared against the
    recorded digest and length before the interpreter is ever invoked, so a
    swap between the check and the run is what the two outer reads exist to
    catch.

    The analyzer's own reported version is then rewritten into an identity chain
    the same way the Swift and TypeScript paths rewrite theirs, so a persisted
    IR names the exact script and interpreter that produced it rather than just
    "php".
    """
    raw_source = source.expanduser()
    if raw_source.is_symlink():
        raise RouteError("PHP_ANALYZER_SOURCE_UNSAFE")
    resolved = raw_source.resolve()
    if not resolved.is_file() or resolved.stat().st_size > _PHP_ANALYZER_MAX_SOURCE_BYTES:
        raise RouteError("PHP_ANALYZER_SOURCE_UNSAFE")

    analyzer_before = _javascript_bound_content(
        _PHP_ANALYZER,
        ENGINE_ROOT,
        expected_sha256=_PHP_ANALYZER_SHA256,
        expected_bytes=_PHP_ANALYZER_BYTES,
        failure="PHP_ANALYZER_ASSET_UNSAFE",
    )
    arguments = [str(resolved), function_name]
    if emitted_target:
        arguments.append("--emitted-target")
    value = _run(
        [toolchain.executable, *_PHP_INTERPRETER_FLAGS, str(_PHP_ANALYZER), *arguments],
        cwd=ENGINE_ROOT,
    )
    analyzer_after = _javascript_bound_content(
        _PHP_ANALYZER,
        ENGINE_ROOT,
        expected_sha256=_PHP_ANALYZER_SHA256,
        expected_bytes=_PHP_ANALYZER_BYTES,
        failure="PHP_ANALYZER_ASSET_UNSAFE",
    )
    if analyzer_before != analyzer_after:
        raise RouteError("PHP_ANALYZER_SNAPSHOT_CHANGED_DURING_EXECUTION")
    if type(value) is not dict:
        raise RouteError("NATIVE_ANALYZER_OBJECT_REQUIRED")
    reported = value.get("analyzer_version")
    if type(reported) is not str or not reported:
        raise RouteError("PHP_ANALYZER_VERSION_REQUIRED")
    bound = dict(value)
    bound["analyzer_version"] = (
        f"{reported};analyzer-sha256={_PHP_ANALYZER_SHA256};"
        f"interpreter-sha256={toolchain.executable_sha256};"
        f"interpreter-version={toolchain.version}"
    )
    return bound


def _javascript_metadata_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _normalize_private_analyzer_root_group(root: Path, *, failure: str) -> None:
    """Normalize a new private analyzer root without permitting path replacement."""

    try:
        before = root.lstat()
        resolved_before = root.resolve(strict=True)
    except OSError as error:
        raise RouteError(failure) from error
    if (
        root != resolved_before
        or root.is_symlink()
        or not stat.S_ISDIR(before.st_mode)
        or before.st_uid != os.getuid()
        or stat.S_IMODE(before.st_mode) != 0o700
    ):
        raise RouteError(failure)
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_uid,
        before.st_size,
        before.st_mtime_ns,
    )
    exact_before = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_uid,
        before.st_gid,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    descriptor_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(root, descriptor_flags)
    except OSError as error:
        raise RouteError(failure) from error
    try:
        opened_before = os.fstat(descriptor)
        if (
            (
                opened_before.st_dev,
                opened_before.st_ino,
                opened_before.st_mode,
                opened_before.st_nlink,
                opened_before.st_uid,
                opened_before.st_gid,
                opened_before.st_size,
                opened_before.st_mtime_ns,
                opened_before.st_ctime_ns,
            )
            != exact_before
        ):
            raise RouteError(failure)
        os.fchown(descriptor, -1, os.getgid())
        opened_after = os.fstat(descriptor)
        after = root.lstat()
        resolved_after = root.resolve(strict=True)
    except OSError as error:
        raise RouteError(failure) from error
    finally:
        os.close(descriptor)
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_nlink,
        after.st_uid,
        after.st_size,
        after.st_mtime_ns,
    )
    exact_after = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_nlink,
        after.st_uid,
        after.st_gid,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if (
        root != resolved_after
        or root.is_symlink()
        or not stat.S_ISDIR(after.st_mode)
        or after.st_uid != os.getuid()
        or after.st_gid != os.getgid()
        or stat.S_IMODE(after.st_mode) != 0o700
        or identity_after != identity_before
        or exact_after
        != (
            opened_after.st_dev,
            opened_after.st_ino,
            opened_after.st_mode,
            opened_after.st_nlink,
            opened_after.st_uid,
            opened_after.st_gid,
            opened_after.st_size,
            opened_after.st_mtime_ns,
            opened_after.st_ctime_ns,
        )
    ):
        raise RouteError(failure)


def _javascript_file_receipt(path: Path, content: bytes) -> dict[str, object]:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise RouteError("JAVASCRIPT_ANALYZER_INPUT_UNSAFE") from error
    return {
        "path": str(path),
        "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
        "nlink": metadata.st_nlink,
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "mtime_ns": metadata.st_mtime_ns,
        "ctime_ns": metadata.st_ctime_ns,
    }


def _javascript_directory_chain(directory: Path, failure: str) -> tuple[tuple[object, ...], ...]:
    """Bind path components without treating unrelated child writes as drift."""

    if not directory.is_absolute():
        raise RouteError(failure)
    cursor = Path("/")
    identities: list[tuple[object, ...]] = []
    try:
        for part in directory.parts[1:]:
            cursor = cursor / part
            metadata = cursor.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid not in {0, os.getuid()}
                or stat.S_IMODE(metadata.st_mode) & 0o022
            ):
                raise RouteError(failure)
            identities.append(
                (
                    str(cursor),
                    metadata.st_dev,
                    metadata.st_ino,
                    metadata.st_mode,
                    metadata.st_uid,
                    metadata.st_gid,
                )
            )
        if directory.resolve(strict=True) != directory:
            raise RouteError(failure)
    except OSError as error:
        raise RouteError(failure) from error
    return tuple(identities)


def _javascript_strict_json_object(content: bytes, failure: str) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result

    try:
        value = json.loads(content.decode("utf-8"), object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise RouteError(failure) from error
    if not isinstance(value, dict):
        raise RouteError(failure)
    return value


def _validate_javascript_typescript_metadata(contents: dict[str, bytes]) -> None:
    failure = "JAVASCRIPT_TYPESCRIPT_ASSET_UNSAFE"
    try:
        manifest_content = contents["asset-manifest.json"]
        package_content = contents["package.json"]
    except KeyError as error:
        raise RouteError(failure) from error
    manifest = _javascript_strict_json_object(manifest_content, failure)
    expected_files = [
        {"path": name, "bytes": byte_count, "sha256": "sha256:" + digest}
        for name, byte_count, digest in _JAVASCRIPT_TYPESCRIPT_ASSET_SPECS
        if name != "asset-manifest.json"
    ]
    if manifest != {
        "schema_version": "1.0.0",
        "asset_id": "typescript-parser-5.9.2",
        "package": {
            "name": "typescript",
            "version": "5.9.2",
            "license": "Apache-2.0",
            "repository": "https://github.com/microsoft/TypeScript.git",
            "registry_tarball": "https://registry.npmjs.org/typescript/-/typescript-5.9.2.tgz",
            "registry_integrity": (
                "sha512-CWBzXQrc/qOkhidw1OzBTQuYRbfyxDXJMVJ1XNwUHGROVmuaeiEm3OslpZ1RV96d7SKKjZKrSJu3+t/xlw3R9A=="
            ),
        },
        "files": expected_files,
    }:
        raise RouteError(failure)
    package = _javascript_strict_json_object(package_content, failure)
    if (
        package.get("name") != "typescript"
        or package.get("version") != "5.9.2"
        or package.get("license") != "Apache-2.0"
        or package.get("repository") != {"type": "git", "url": "https://github.com/microsoft/TypeScript.git"}
        or package.get("main") != "./lib/typescript.js"
    ):
        raise RouteError(failure)


def _javascript_typescript_assets() -> tuple[dict[str, object], dict[str, bytes]]:
    failure = "JAVASCRIPT_TYPESCRIPT_ASSET_UNSAFE"
    root = _JAVASCRIPT_TYPESCRIPT_ROOT
    expected_names = tuple(name for name, _byte_count, _digest in _JAVASCRIPT_TYPESCRIPT_ASSET_SPECS)
    try:
        if not root.is_absolute() or root.name != "typescript-5.9.2":
            raise RouteError(failure)
        chain_before = _javascript_directory_chain(root, failure)
        root_before = root.lstat()
        names_before = tuple(sorted(item.name for item in root.iterdir()))
        resolved_root = root.resolve(strict=True)
    except OSError as error:
        raise RouteError(failure) from error
    root_identity = _javascript_metadata_identity(root_before)
    if (
        resolved_root != root
        or not stat.S_ISDIR(root_before.st_mode)
        or root_before.st_uid != os.getuid()
        or root_before.st_gid != os.getgid()
        or stat.S_IMODE(root_before.st_mode) != _JAVASCRIPT_TYPESCRIPT_ROOT_MODE
        or root_before.st_nlink != _JAVASCRIPT_TYPESCRIPT_ROOT_NLINK
        or names_before != tuple(sorted(expected_names))
    ):
        raise RouteError(failure)

    contents: dict[str, bytes] = {}
    files: dict[str, object] = {}
    for name, expected_bytes, expected_sha256 in _JAVASCRIPT_TYPESCRIPT_ASSET_SPECS:
        path = root / name
        try:
            relative = path.relative_to(root)
            metadata_before = path.lstat()
            resolved = path.resolve(strict=True)
        except (OSError, ValueError) as error:
            raise RouteError(failure) from error
        if (
            relative.parts != (name,)
            or resolved != path
            or not resolved.is_relative_to(root)
            or not stat.S_ISREG(metadata_before.st_mode)
            or metadata_before.st_uid != os.getuid()
            or metadata_before.st_gid != os.getgid()
            or stat.S_IMODE(metadata_before.st_mode) != _JAVASCRIPT_TYPESCRIPT_ASSET_MODE
            or metadata_before.st_nlink != 1
        ):
            raise RouteError(failure)
        content = _stable_read_regular_file(
            path,
            failure=failure,
            maximum_bytes=expected_bytes,
            minimum_bytes=expected_bytes,
            allowed_uids=frozenset({os.getuid()}),
            require_nlink_one=True,
        )
        try:
            metadata_after = path.lstat()
        except OSError as error:
            raise RouteError(failure) from error
        if (
            _javascript_metadata_identity(metadata_before) != _javascript_metadata_identity(metadata_after)
            or len(content) != expected_bytes
            or hashlib.sha256(content).hexdigest() != expected_sha256
        ):
            raise RouteError(failure)
        contents[name] = content
        files[name] = _javascript_file_receipt(path, content)

    _validate_javascript_typescript_metadata(contents)
    try:
        names_after = tuple(sorted(item.name for item in root.iterdir()))
        root_after = root.lstat()
        chain_after = _javascript_directory_chain(root, failure)
    except OSError as error:
        raise RouteError(failure) from error
    if (
        names_after != names_before
        or _javascript_metadata_identity(root_after) != root_identity
        or chain_after != chain_before
    ):
        raise RouteError(failure)
    return (
        {
            "root": {
                "path": str(root),
                "mode": f"{stat.S_IMODE(root_after.st_mode):04o}",
                "uid": root_after.st_uid,
                "gid": root_after.st_gid,
                "nlink": root_after.st_nlink,
                "device": root_after.st_dev,
                "inode": root_after.st_ino,
                "mtime_ns": root_after.st_mtime_ns,
                "ctime_ns": root_after.st_ctime_ns,
            },
            "path_set": list(expected_names),
            "files": files,
        },
        contents,
    )


def _javascript_analyzer_inputs(
    source: Path,
    descriptor: dict[str, object] | None,
) -> tuple[dict[str, object], dict[str, bytes]]:
    try:
        resolved_analyzer = _JAVASCRIPT_ANALYZER.resolve(strict=True)
    except OSError as error:
        raise RouteError("JAVASCRIPT_ANALYZER_SOURCE_UNSAFE") from error
    if resolved_analyzer != _JAVASCRIPT_ANALYZER:
        raise RouteError("JAVASCRIPT_ANALYZER_SOURCE_UNSAFE")
    analyzer = _javascript_bound_content(
        _JAVASCRIPT_ANALYZER,
        _JAVASCRIPT_ANALYZER.parent,
        expected_sha256=_JAVASCRIPT_ANALYZER_SHA256,
        expected_bytes=_JAVASCRIPT_ANALYZER_BYTES,
        failure="JAVASCRIPT_ANALYZER_SOURCE_UNSAFE",
    )
    typescript_binding, typescript_contents = _javascript_typescript_assets()
    source_content = _stable_read_regular_file(
        source,
        failure="JAVASCRIPT_SOURCE_UNSAFE",
        maximum_bytes=_JAVASCRIPT_ANALYZER_MAX_SOURCE_BYTES,
        allowed_uids=frozenset({os.getuid()}),
        require_nlink_one=True,
    )
    descriptor_content: bytes | None = None
    if descriptor is not None:
        descriptor_path = Path(str(descriptor.get("path", "")))
        expected_sha256 = descriptor.get("sha256")
        expected_bytes = descriptor.get("bytes")
        if (
            not descriptor_path.is_absolute()
            or not isinstance(expected_sha256, str)
            or not isinstance(expected_bytes, int)
            or expected_bytes < 0
        ):
            raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_PATH_UNSAFE")
        descriptor_content = _stable_read_regular_file(
            descriptor_path,
            failure="JAVASCRIPT_ESM_DESCRIPTOR_PATH_UNSAFE",
            maximum_bytes=expected_bytes,
            minimum_bytes=expected_bytes,
            allowed_uids=frozenset({os.getuid()}),
            require_nlink_one=True,
        )
        if hashlib.sha256(descriptor_content).hexdigest() != expected_sha256:
            raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_CHANGED_DURING_READ")
    binding: dict[str, object] = {
        "analyzer_sha256": "sha256:" + hashlib.sha256(analyzer).hexdigest(),
        "analyzer_bytes": len(analyzer),
        "typescript_asset_manifest_sha256": (
            "sha256:" + hashlib.sha256(typescript_contents["asset-manifest.json"]).hexdigest()
        ),
        "typescript_asset_manifest_bytes": len(typescript_contents["asset-manifest.json"]),
        "typescript_license_sha256": "sha256:" + hashlib.sha256(typescript_contents["LICENSE.txt"]).hexdigest(),
        "typescript_license_bytes": len(typescript_contents["LICENSE.txt"]),
        "typescript_package_sha256": "sha256:" + hashlib.sha256(typescript_contents["package.json"]).hexdigest(),
        "typescript_package_bytes": len(typescript_contents["package.json"]),
        "typescript_sha256": "sha256:" + hashlib.sha256(typescript_contents["typescript.js"]).hexdigest(),
        "typescript_bytes": len(typescript_contents["typescript.js"]),
        "source_sha256": "sha256:" + hashlib.sha256(source_content).hexdigest(),
        "source_bytes": len(source_content),
        "live_seal": {
            "analyzer": _javascript_file_receipt(_JAVASCRIPT_ANALYZER, analyzer),
            "typescript_assets": typescript_binding,
            "source": _javascript_file_receipt(source, source_content),
        },
    }
    if descriptor is not None and descriptor_content is not None:
        binding["source_esm_descriptor_sha256"] = "sha256:" + str(descriptor["sha256"])
        binding["source_esm_descriptor_bytes"] = expected_bytes
        binding["source_esm_descriptor_path"] = str(descriptor["path"])
        live_seal = binding["live_seal"]
        assert isinstance(live_seal, dict)
        live_seal["source_esm_descriptor"] = _javascript_file_receipt(Path(str(descriptor["path"])), descriptor_content)
    contents = {
        "analyzer": analyzer,
        "asset-manifest.json": typescript_contents["asset-manifest.json"],
        "LICENSE.txt": typescript_contents["LICENSE.txt"],
        "package.json": typescript_contents["package.json"],
        "typescript.js": typescript_contents["typescript.js"],
        "source": source_content,
    }
    if descriptor_content is not None:
        contents["source_esm_descriptor"] = descriptor_content
    return binding, contents


def _write_javascript_snapshot(path: Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
        try:
            written = 0
            while written < len(content):
                size = os.write(descriptor, content[written:])
                if size <= 0:
                    raise OSError("zero-byte JavaScript analyzer snapshot write")
                written += size
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise RouteError("JAVASCRIPT_ANALYZER_SNAPSHOT_CREATE_FAILED") from error


def _javascript_snapshot_binding(
    root: Path,
    source_name: str,
    *,
    descriptor_required: bool = False,
) -> dict[str, object]:
    failure = "JAVASCRIPT_ANALYZER_SNAPSHOT_UNSAFE"
    try:
        root_metadata = root.lstat()
        resolved_root = root.resolve(strict=True)
    except OSError as error:
        raise RouteError(failure) from error
    if (
        root != resolved_root
        or root.is_symlink()
        or not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid != os.getuid()
        or root_metadata.st_gid != os.getgid()
        or stat.S_IMODE(root_metadata.st_mode) != 0o700
    ):
        raise RouteError(failure)
    directories = (
        root / "assets",
        root / "assets" / "typescript-5.9.2",
        root / "source",
    )
    for directory in directories:
        try:
            metadata = directory.lstat()
            resolved_directory = directory.resolve(strict=True)
        except OSError as error:
            raise RouteError(failure) from error
        if (
            directory.is_symlink()
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_gid != os.getgid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or not resolved_directory.is_relative_to(resolved_root)
        ):
            raise RouteError(failure)
    expected_sets = {
        root: {"assets", "source"},
        root / "assets": {"analyzer.mjs", "typescript-5.9.2"},
        root / "assets" / "typescript-5.9.2": {
            name for name, _byte_count, _digest in _JAVASCRIPT_TYPESCRIPT_ASSET_SPECS
        },
        root / "source": ({source_name, "package.json"} if descriptor_required else {source_name}),
    }
    try:
        if any(
            {item.name for item in directory.iterdir()} != expected for directory, expected in expected_sets.items()
        ):
            raise RouteError(failure)
    except OSError as error:
        raise RouteError(failure) from error
    paths = {
        "analyzer": root / "assets" / "analyzer.mjs",
        "typescript_asset_manifest": root / "assets" / "typescript-5.9.2" / "asset-manifest.json",
        "typescript_license": root / "assets" / "typescript-5.9.2" / "LICENSE.txt",
        "typescript_package": root / "assets" / "typescript-5.9.2" / "package.json",
        "typescript": root / "assets" / "typescript-5.9.2" / "typescript.js",
        "source": root / "source" / source_name,
    }
    limits = {
        "analyzer": _JAVASCRIPT_ANALYZER_BYTES,
        "typescript_asset_manifest": _JAVASCRIPT_TYPESCRIPT_ASSET_SPECS[0][1],
        "typescript_license": _JAVASCRIPT_TYPESCRIPT_ASSET_SPECS[1][1],
        "typescript_package": _JAVASCRIPT_TYPESCRIPT_ASSET_SPECS[2][1],
        "typescript": _JAVASCRIPT_TYPESCRIPT_BYTES,
        "source": _JAVASCRIPT_ANALYZER_MAX_SOURCE_BYTES,
    }
    if descriptor_required:
        paths["source_esm_descriptor"] = root / "source" / "package.json"
        limits["source_esm_descriptor"] = _JAVASCRIPT_ANALYZER_MAX_SOURCE_BYTES
    result: dict[str, object] = {}
    file_seals: dict[str, object] = {}
    for role, path in paths.items():
        try:
            relative = path.relative_to(root)
            metadata = path.lstat()
            resolved_path = path.resolve(strict=True)
        except (OSError, ValueError) as error:
            raise RouteError(failure) from error
        if (
            len(relative.parts) not in {2, 3}
            or path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_gid != os.getgid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
            or not resolved_path.is_relative_to(resolved_root)
        ):
            raise RouteError(failure)
        content = _stable_read_regular_file(
            path,
            failure=failure,
            maximum_bytes=limits[role],
            allowed_uids=frozenset({os.getuid()}),
            require_nlink_one=True,
        )
        result[f"{role}_sha256"] = "sha256:" + hashlib.sha256(content).hexdigest()
        result[f"{role}_bytes"] = len(content)
        file_seals[role] = _javascript_file_receipt(path, content)
    try:
        directory_seals = {
            str(directory.relative_to(root)): _javascript_metadata_identity(directory.lstat())
            for directory in directories
        }
    except (OSError, ValueError) as error:
        raise RouteError(failure) from error
    result["snapshot_seal"] = {
        "root": {
            "path": str(root),
            "mode": f"{stat.S_IMODE(root_metadata.st_mode):04o}",
            "uid": root_metadata.st_uid,
            "gid": root_metadata.st_gid,
            "nlink": root_metadata.st_nlink,
            "device": root_metadata.st_dev,
            "inode": root_metadata.st_ino,
            "mtime_ns": root_metadata.st_mtime_ns,
            "ctime_ns": root_metadata.st_ctime_ns,
        },
        "directories": directory_seals,
        "files": file_seals,
    }
    return result


def _javascript_toolchain_binding(toolchain: ExactToolchain) -> dict[str, str]:
    profile: dict[str, str] = {}
    for item in toolchain.profile:
        key, separator, value = item.partition("=")
        if not separator or not key or not value or key in profile:
            raise RouteError("JAVASCRIPT_ANALYZER_TOOLCHAIN_POLICY_INVALID")
        profile[key] = value
    closure_items = [
        (key, value) for key, value in profile.items() if re.fullmatch(r"node(?:-toolchain)?-closure-sha256", key)
    ]
    if (
        len(closure_items) != 1
        or re.fullmatch(r"[0-9a-f]{64}", closure_items[0][1]) is None
        or profile.get("node-toolchain-closure-schema") != "v1"
    ):
        raise RouteError("JAVASCRIPT_ANALYZER_TOOLCHAIN_POLICY_INVALID")
    profile_bytes = json.dumps(list(toolchain.profile), ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return {
        "closure_field": closure_items[0][0],
        "closure_sha256": closure_items[0][1],
        "profile_sha256": hashlib.sha256(profile_bytes).hexdigest(),
    }


def _verify_trusted_javascript_toolchain(expected: ExactToolchain) -> dict[str, str]:
    if (
        expected.language != "javascript"
        or expected.version != "Node.js 26.0.0 / ES2022 / ESM"
        or not Path(expected.executable).is_absolute()
        or expected.auxiliary is not None
        or expected.executable_sha256 is None
        or re.fullmatch(r"[0-9a-f]{64}", expected.executable_sha256) is None
    ):
        raise RouteError("JAVASCRIPT_ANALYZER_TOOLCHAIN_POLICY_INVALID")
    expected_binding = _javascript_toolchain_binding(expected)
    try:
        current = exact_toolchain("javascript")
    except RouteError as error:
        raise RouteError("JAVASCRIPT_ANALYZER_TOOLCHAIN_CHANGED") from error
    if current != expected or _javascript_toolchain_binding(current) != expected_binding:
        raise RouteError("JAVASCRIPT_ANALYZER_TOOLCHAIN_CHANGED")
    return expected_binding


def _javascript_content_binding(binding: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in binding.items()
        if key not in {"live_seal", "snapshot_seal", "source_esm_descriptor_path"}
    }


def _require_javascript_snapshot_unchanged(
    root: Path,
    source_name: str,
    expected: dict[str, object],
    *,
    descriptor_required: bool = False,
) -> None:
    try:
        current = _javascript_snapshot_binding(root, source_name, descriptor_required=descriptor_required)
    except RouteError as error:
        raise RouteError("JAVASCRIPT_ANALYZER_SNAPSHOT_CHANGED_DURING_EXECUTION") from error
    if current != expected:
        raise RouteError("JAVASCRIPT_ANALYZER_SNAPSHOT_CHANGED_DURING_EXECUTION")


def _require_javascript_inputs_unchanged(
    source: Path,
    expected: dict[str, object],
    descriptor: dict[str, object] | None,
) -> None:
    try:
        current_descriptor = javascript_esm_descriptor(source)
        if current_descriptor != descriptor:
            raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_CHANGED_DURING_EXECUTION")
        current, _contents = _javascript_analyzer_inputs(source, current_descriptor)
    except RouteError as error:
        raise RouteError("JAVASCRIPT_ANALYZER_INPUT_CHANGED_DURING_EXECUTION") from error
    if current != expected:
        raise RouteError("JAVASCRIPT_ANALYZER_INPUT_CHANGED_DURING_EXECUTION")


def _run_trusted_javascript_analyzer(
    toolchain: ExactToolchain,
    source: Path,
    selector: str,
    *,
    emitted_target: bool = False,
) -> dict[str, Any]:
    descriptor = javascript_esm_descriptor(source)
    if selector != "--inventory" and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", selector) is None:
        raise RouteError("JAVASCRIPT_ANALYZER_COMMAND_SHAPE_INVALID")
    if selector == "--inventory" and emitted_target:
        raise RouteError("JAVASCRIPT_ANALYZER_COMMAND_SHAPE_INVALID")
    expected_inputs, contents = _javascript_analyzer_inputs(source, descriptor)
    expected_toolchain = _verify_trusted_javascript_toolchain(toolchain)
    with tempfile.TemporaryDirectory(prefix="elmos-javascript-analyzer-") as temporary:
        root = Path(temporary).resolve(strict=True)
        root.chmod(0o700)
        _normalize_private_analyzer_root_group(
            root,
            failure="JAVASCRIPT_ANALYZER_SNAPSHOT_UNSAFE",
        )
        assets = root / "assets"
        typescript_assets = assets / "typescript-5.9.2"
        sources = root / "source"
        assets.mkdir(mode=0o700)
        typescript_assets.mkdir(mode=0o700)
        sources.mkdir(mode=0o700)
        analyzer = assets / "analyzer.mjs"
        typescript = typescript_assets / "typescript.js"
        source_snapshot = sources / source.name
        _write_javascript_snapshot(analyzer, contents["analyzer"])
        for name, _byte_count, _digest in _JAVASCRIPT_TYPESCRIPT_ASSET_SPECS:
            _write_javascript_snapshot(typescript_assets / name, contents[name])
        _write_javascript_snapshot(source_snapshot, contents["source"])
        if descriptor is not None:
            _write_javascript_snapshot(sources / "package.json", contents["source_esm_descriptor"])
        expected_snapshot = _javascript_snapshot_binding(root, source.name, descriptor_required=descriptor is not None)
        if _javascript_content_binding(expected_snapshot) != _javascript_content_binding(expected_inputs):
            raise RouteError("JAVASCRIPT_ANALYZER_SNAPSHOT_CONTENT_MISMATCH")
        _require_javascript_snapshot_unchanged(
            root, source.name, expected_snapshot, descriptor_required=descriptor is not None
        )
        _require_javascript_inputs_unchanged(source, expected_inputs, descriptor)
        if _verify_trusted_javascript_toolchain(toolchain) != expected_toolchain:
            raise RouteError("JAVASCRIPT_ANALYZER_TOOLCHAIN_CHANGED")
        command = [
            toolchain.executable,
            str(analyzer),
            str(typescript),
            str(source_snapshot),
            selector,
            *(["--emitted-target"] if emitted_target else []),
        ]
        try:
            value = _run(command, cwd=root)
        except RouteError as error:
            try:
                _require_javascript_snapshot_unchanged(
                    root, source.name, expected_snapshot, descriptor_required=descriptor is not None
                )
                _require_javascript_inputs_unchanged(source, expected_inputs, descriptor)
            except RouteError as changed:
                raise changed from error
            _verify_trusted_javascript_toolchain(toolchain)
            raise
        _require_javascript_snapshot_unchanged(
            root, source.name, expected_snapshot, descriptor_required=descriptor is not None
        )
        _require_javascript_inputs_unchanged(source, expected_inputs, descriptor)
        if _verify_trusted_javascript_toolchain(toolchain) != expected_toolchain:
            raise RouteError("JAVASCRIPT_ANALYZER_TOOLCHAIN_CHANGED")
        analyzer_version = value.get("analyzer_version")
        if not isinstance(analyzer_version, str) or not analyzer_version:
            raise RouteError("JAVASCRIPT_ANALYZER_VERSION_REQUIRED")
        bound = dict(value)
        bound["analyzer_version"] = (
            f"{analyzer_version};analyzer={_JAVASCRIPT_ANALYZER_SHA256};"
            f"typescript={_JAVASCRIPT_TYPESCRIPT_SHA256};"
            f"typescript-assets={_JAVASCRIPT_TYPESCRIPT_MANIFEST_SHA256};"
            f"node={toolchain.executable_sha256};"
            f"node-closure={expected_toolchain['closure_sha256']};"
            f"node-profile={expected_toolchain['profile_sha256']}"
        )
        return bound


def _validated_typescript_parser_receipt(value: object) -> dict[str, str | int]:
    failure = "TYPESCRIPT_ANALYZER_PARSER_RECEIPT_INVALID"
    required_keys = {
        "schema_version",
        "path",
        "sha256",
        "bytes",
        "mode",
        "uid",
        "gid",
        "nlink",
        "compiler_root",
        "compiler_closure_sha256",
        "compiler_closure_file_count",
        "compiler_closure_bytes",
        "semantic_soundness",
    }
    if not isinstance(value, dict) or set(value) != required_keys:
        raise RouteError(failure)
    path_value = value.get("path")
    root_value = value.get("compiler_root")
    sha256 = value.get("sha256")
    closure_sha256 = value.get("compiler_closure_sha256")
    mode = value.get("mode")
    byte_count = value.get("bytes")
    closure_file_count = value.get("compiler_closure_file_count")
    closure_bytes = value.get("compiler_closure_bytes")
    uid = value.get("uid")
    gid = value.get("gid")
    nlink = value.get("nlink")
    if (
        type(value.get("schema_version")) is not int
        or value.get("schema_version") != 1
        or value.get("semantic_soundness") != "NOT_RUN"
        or not isinstance(path_value, str)
        or not isinstance(root_value, str)
        or not isinstance(sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", sha256) is None
        or not isinstance(closure_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", closure_sha256) is None
        or not isinstance(mode, str)
        or re.fullmatch(r"0[0-7]{3}", mode) is None
        or type(byte_count) is not int
        or byte_count <= 0
        or type(closure_file_count) is not int
        or closure_file_count <= 0
        or type(closure_bytes) is not int
        or closure_bytes < byte_count
        or type(uid) is not int
        or uid not in {0, os.getuid()}
        or type(gid) is not int
        or gid < 0
        or type(nlink) is not int
        or nlink != 1
        or int(mode, 8) & 0o022
    ):
        raise RouteError(failure)
    parser = Path(path_value)
    compiler_root = Path(root_value)
    try:
        relative = parser.relative_to(compiler_root)
    except ValueError as error:
        raise RouteError(failure) from error
    if (
        not parser.is_absolute()
        or not compiler_root.is_absolute()
        or parser == compiler_root
        or not relative.parts
        or ".." in parser.parts
        or ".." in compiler_root.parts
    ):
        raise RouteError(failure)
    return {str(key): item for key, item in value.items() if isinstance(item, str | int)}


def _typescript_toolchain_binding(
    toolchain: ExactToolchain,
    parser_receipt: dict[str, str | int],
) -> dict[str, str]:
    failure = "TYPESCRIPT_ANALYZER_TOOLCHAIN_POLICY_INVALID"
    profile: dict[str, str] = {}
    for item in toolchain.profile:
        key, separator, value = item.partition("=")
        if not separator or not key or not value or key in profile:
            raise RouteError(failure)
        profile[key] = value
    if (
        toolchain.language != "typescript"
        or toolchain.version != "5.9.2 / Node 26.0.0"
        or not Path(toolchain.executable).is_absolute()
        or toolchain.auxiliary is None
        or not Path(toolchain.auxiliary).is_absolute()
        or toolchain.executable_sha256 is None
        or re.fullmatch(r"[0-9a-f]{64}", toolchain.executable_sha256) is None
        or toolchain.auxiliary_sha256 is None
        or re.fullmatch(r"[0-9a-f]{64}", toolchain.auxiliary_sha256) is None
        or profile.get("typescript-toolchain-closure-schema") != "v1"
        or profile.get("typescript-language-version") != "5.9.2"
        or profile.get("typescript-package-root") != parser_receipt["compiler_root"]
        or profile.get("typescript-closure-sha256") != parser_receipt["compiler_closure_sha256"]
        or profile.get("typescript-closure-file-count") != str(parser_receipt["compiler_closure_file_count"])
        or profile.get("typescript-closure-bytes") != str(parser_receipt["compiler_closure_bytes"])
        or profile.get("typescript-parser-sha256") != parser_receipt["sha256"]
        or profile.get("typescript-compiler-runtime-semantic-soundness") != "NOT_RUN"
        or re.fullmatch(r"[0-9a-f]{64}", profile.get("node-closure-sha256", "")) is None
    ):
        raise RouteError(failure)
    for key in (
        "node-closure-component-count",
        "node-closure-edge-count",
        "node-closure-system-edge-count",
    ):
        try:
            if int(profile.get(key, "")) <= 0:
                raise ValueError
        except ValueError as error:
            raise RouteError(failure) from error
    profile_bytes = json.dumps(list(toolchain.profile), ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return {
        "typescript_closure_sha256": str(parser_receipt["compiler_closure_sha256"]),
        "node_closure_sha256": profile["node-closure-sha256"],
        "profile_sha256": hashlib.sha256(profile_bytes).hexdigest(),
    }


def _typescript_file_seal(path: Path, content: bytes, failure: str) -> dict[str, object]:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise RouteError(failure) from error
    return {
        "path": str(path),
        "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
        "nlink": metadata.st_nlink,
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "mtime_ns": metadata.st_mtime_ns,
        "ctime_ns": metadata.st_ctime_ns,
    }


def _typescript_parser_content(receipt: dict[str, str | int]) -> bytes:
    failure = "TYPESCRIPT_ANALYZER_PARSER_INPUT_UNSAFE"
    parser = Path(str(receipt["path"]))
    compiler_root = Path(str(receipt["compiler_root"]))
    try:
        resolved_parser = parser.resolve(strict=True)
        resolved_root = compiler_root.resolve(strict=True)
    except OSError as error:
        raise RouteError(failure) from error
    if resolved_parser != parser or resolved_root != compiler_root or not parser.is_relative_to(compiler_root):
        raise RouteError(failure)
    content = _stable_read_regular_file(
        parser,
        failure=failure,
        maximum_bytes=int(receipt["bytes"]),
        minimum_bytes=int(receipt["bytes"]),
        allowed_uids=frozenset({int(receipt["uid"])}),
        require_nlink_one=True,
    )
    seal = _typescript_file_seal(parser, content, failure)
    if (
        hashlib.sha256(content).hexdigest() != receipt["sha256"]
        or seal["bytes"] != receipt["bytes"]
        or seal["mode"] != receipt["mode"]
        or seal["uid"] != receipt["uid"]
        or seal["gid"] != receipt["gid"]
        or seal["nlink"] != receipt["nlink"]
    ):
        raise RouteError(failure)
    return content


def _typescript_analyzer_inputs(
    source: Path,
    parser_receipt: dict[str, str | int],
) -> tuple[dict[str, object], dict[str, bytes]]:
    analyzer = _javascript_bound_content(
        _TYPESCRIPT_ANALYZER,
        _TYPESCRIPT_ANALYZER.parent,
        expected_sha256=_TYPESCRIPT_ANALYZER_SHA256,
        expected_bytes=_TYPESCRIPT_ANALYZER_BYTES,
        failure="TYPESCRIPT_ANALYZER_SOURCE_UNSAFE",
    )
    parser = _typescript_parser_content(parser_receipt)
    source_content = _stable_read_regular_file(
        source,
        failure="TYPESCRIPT_ANALYZER_SOURCE_INPUT_UNSAFE",
        maximum_bytes=_TYPESCRIPT_ANALYZER_MAX_SOURCE_BYTES,
        allowed_uids=frozenset({os.getuid()}),
        require_nlink_one=True,
    )
    binding: dict[str, object] = {
        "analyzer_sha256": "sha256:" + hashlib.sha256(analyzer).hexdigest(),
        "analyzer_bytes": len(analyzer),
        "parser_sha256": "sha256:" + hashlib.sha256(parser).hexdigest(),
        "parser_bytes": len(parser),
        "source_sha256": "sha256:" + hashlib.sha256(source_content).hexdigest(),
        "source_bytes": len(source_content),
        "parser_receipt": dict(parser_receipt),
        "live_seal": {
            "analyzer": _typescript_file_seal(
                _TYPESCRIPT_ANALYZER,
                analyzer,
                "TYPESCRIPT_ANALYZER_SOURCE_UNSAFE",
            ),
            "parser": _typescript_file_seal(
                Path(str(parser_receipt["path"])),
                parser,
                "TYPESCRIPT_ANALYZER_PARSER_INPUT_UNSAFE",
            ),
            "source": _typescript_file_seal(
                source,
                source_content,
                "TYPESCRIPT_ANALYZER_SOURCE_INPUT_UNSAFE",
            ),
        },
    }
    return binding, {"analyzer": analyzer, "parser": parser, "source": source_content}


def _write_typescript_snapshot(path: Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
        try:
            written = 0
            while written < len(content):
                size = os.write(descriptor, content[written:])
                if size <= 0:
                    raise OSError("zero-byte TypeScript analyzer snapshot write")
                written += size
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise RouteError("TYPESCRIPT_ANALYZER_SNAPSHOT_CREATE_FAILED") from error


def _typescript_snapshot_binding(root: Path, source_name: str) -> dict[str, object]:
    failure = "TYPESCRIPT_ANALYZER_SNAPSHOT_UNSAFE"
    try:
        root_metadata = root.lstat()
        resolved_root = root.resolve(strict=True)
    except OSError as error:
        raise RouteError(failure) from error
    if (
        root != resolved_root
        or root.is_symlink()
        or not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid != os.getuid()
        or root_metadata.st_gid != os.getgid()
        or stat.S_IMODE(root_metadata.st_mode) != 0o700
    ):
        raise RouteError(failure)
    assets = root / "assets"
    sources = root / "source"
    directories = (assets, sources)
    for directory in directories:
        try:
            metadata = directory.lstat()
            resolved = directory.resolve(strict=True)
        except OSError as error:
            raise RouteError(failure) from error
        if (
            directory.is_symlink()
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_gid != os.getgid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or not resolved.is_relative_to(resolved_root)
        ):
            raise RouteError(failure)
    expected_sets = {
        root: {"assets", "source"},
        assets: {"analyzer.mjs", "typescript.js"},
        sources: {source_name},
    }
    try:
        if any(
            {item.name for item in directory.iterdir()} != expected for directory, expected in expected_sets.items()
        ):
            raise RouteError(failure)
    except OSError as error:
        raise RouteError(failure) from error
    paths = {
        "analyzer": assets / "analyzer.mjs",
        "parser": assets / "typescript.js",
        "source": sources / source_name,
    }
    limits = {
        "analyzer": _TYPESCRIPT_ANALYZER_BYTES,
        "parser": 20_000_000,
        "source": _TYPESCRIPT_ANALYZER_MAX_SOURCE_BYTES,
    }
    result: dict[str, object] = {}
    files: dict[str, object] = {}
    for role, path in paths.items():
        try:
            relative = path.relative_to(root)
            metadata = path.lstat()
            resolved = path.resolve(strict=True)
        except (OSError, ValueError) as error:
            raise RouteError(failure) from error
        if (
            len(relative.parts) != 2
            or path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_gid != os.getgid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
            or not resolved.is_relative_to(resolved_root)
        ):
            raise RouteError(failure)
        content = _stable_read_regular_file(
            path,
            failure=failure,
            maximum_bytes=limits[role],
            allowed_uids=frozenset({os.getuid()}),
            require_nlink_one=True,
        )
        result[f"{role}_sha256"] = "sha256:" + hashlib.sha256(content).hexdigest()
        result[f"{role}_bytes"] = len(content)
        files[role] = _typescript_file_seal(path, content, failure)
    result["snapshot_seal"] = {
        "root": {
            "path": str(root),
            "mode": f"{stat.S_IMODE(root_metadata.st_mode):04o}",
            "uid": root_metadata.st_uid,
            "gid": root_metadata.st_gid,
            "nlink": root_metadata.st_nlink,
            "device": root_metadata.st_dev,
            "inode": root_metadata.st_ino,
            "mtime_ns": root_metadata.st_mtime_ns,
            "ctime_ns": root_metadata.st_ctime_ns,
        },
        "directories": {
            str(directory.relative_to(root)): _javascript_metadata_identity(directory.lstat())
            for directory in directories
        },
        "files": files,
    }
    return result


def _typescript_content_binding(binding: dict[str, object]) -> dict[str, object]:
    keys = {
        "analyzer_sha256",
        "analyzer_bytes",
        "parser_sha256",
        "parser_bytes",
        "source_sha256",
        "source_bytes",
    }
    return {key: binding[key] for key in sorted(keys)}


def _require_typescript_snapshot_unchanged(
    root: Path,
    source_name: str,
    expected: dict[str, object],
) -> None:
    try:
        current = _typescript_snapshot_binding(root, source_name)
    except RouteError as error:
        raise RouteError("TYPESCRIPT_ANALYZER_SNAPSHOT_CHANGED_DURING_EXECUTION") from error
    if current != expected:
        raise RouteError("TYPESCRIPT_ANALYZER_SNAPSHOT_CHANGED_DURING_EXECUTION")


def _require_typescript_inputs_unchanged(
    source: Path,
    expected_receipt: dict[str, str | int],
    expected_inputs: dict[str, object],
) -> dict[str, str | int]:
    try:
        current_receipt = _validated_typescript_parser_receipt(typescript_parser_receipt())
        current_inputs, _ = _typescript_analyzer_inputs(source, current_receipt)
    except RouteError as error:
        raise RouteError("TYPESCRIPT_ANALYZER_INPUT_CHANGED_DURING_EXECUTION") from error
    if current_receipt != expected_receipt or current_inputs != expected_inputs:
        raise RouteError("TYPESCRIPT_ANALYZER_INPUT_CHANGED_DURING_EXECUTION")
    return current_receipt


def _require_typescript_toolchain_unchanged(
    expected: ExactToolchain,
    expected_binding: dict[str, str],
    parser_receipt: dict[str, str | int],
) -> None:
    try:
        current = exact_toolchain("typescript")
        current_binding = _typescript_toolchain_binding(current, parser_receipt)
    except RouteError as error:
        raise RouteError("TYPESCRIPT_ANALYZER_TOOLCHAIN_CHANGED") from error
    if current != expected or current_binding != expected_binding:
        raise RouteError("TYPESCRIPT_ANALYZER_TOOLCHAIN_CHANGED")


def _run_trusted_typescript_analyzer(
    toolchain: ExactToolchain,
    source: Path,
    selector: str,
    *,
    emitted_target: bool = False,
) -> dict[str, Any]:
    if selector != "--inventory" and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", selector) is None:
        raise RouteError("TYPESCRIPT_ANALYZER_COMMAND_SHAPE_INVALID")
    if selector == "--inventory" and emitted_target:
        raise RouteError("TYPESCRIPT_ANALYZER_COMMAND_SHAPE_INVALID")
    parser_receipt = _validated_typescript_parser_receipt(typescript_parser_receipt())
    toolchain_binding = _typescript_toolchain_binding(toolchain, parser_receipt)
    expected_inputs, contents = _typescript_analyzer_inputs(source, parser_receipt)
    with tempfile.TemporaryDirectory(prefix="elmos-typescript-analyzer-") as temporary:
        root = Path(temporary).resolve(strict=True)
        root.chmod(0o700)
        _normalize_private_analyzer_root_group(
            root,
            failure="TYPESCRIPT_ANALYZER_SNAPSHOT_UNSAFE",
        )
        assets = root / "assets"
        sources = root / "source"
        assets.mkdir(mode=0o700)
        sources.mkdir(mode=0o700)
        analyzer = assets / "analyzer.mjs"
        parser = assets / "typescript.js"
        source_snapshot = sources / source.name
        _write_typescript_snapshot(analyzer, contents["analyzer"])
        _write_typescript_snapshot(parser, contents["parser"])
        _write_typescript_snapshot(source_snapshot, contents["source"])
        expected_snapshot = _typescript_snapshot_binding(root, source.name)
        if _typescript_content_binding(expected_snapshot) != _typescript_content_binding(expected_inputs):
            raise RouteError("TYPESCRIPT_ANALYZER_SNAPSHOT_CONTENT_MISMATCH")
        _require_typescript_snapshot_unchanged(root, source.name, expected_snapshot)
        command = [
            toolchain.executable,
            str(analyzer),
            str(parser),
            str(source_snapshot),
            selector,
            *(["--emitted-target"] if emitted_target else []),
        ]
        try:
            value = _run(command, cwd=root)
        except RouteError as error:
            try:
                _require_typescript_snapshot_unchanged(root, source.name, expected_snapshot)
                current_receipt = _require_typescript_inputs_unchanged(source, parser_receipt, expected_inputs)
                _require_typescript_toolchain_unchanged(toolchain, toolchain_binding, current_receipt)
            except RouteError as changed:
                raise changed from error
            raise
        _require_typescript_snapshot_unchanged(root, source.name, expected_snapshot)
        current_receipt = _require_typescript_inputs_unchanged(source, parser_receipt, expected_inputs)
        _require_typescript_toolchain_unchanged(toolchain, toolchain_binding, current_receipt)
        analyzer_version = value.get("analyzer_version")
        if analyzer_version != "5.9.2":
            raise RouteError("TYPESCRIPT_ANALYZER_VERSION_MISMATCH")
        bound = dict(value)
        bound["analyzer_version"] = (
            f"{analyzer_version};analyzer={_TYPESCRIPT_ANALYZER_SHA256};"
            f"typescript-parser={parser_receipt['sha256']};"
            f"typescript-closure={toolchain_binding['typescript_closure_sha256']};"
            f"node={toolchain.executable_sha256};"
            f"node-closure={toolchain_binding['node_closure_sha256']};"
            f"typescript-profile={toolchain_binding['profile_sha256']}"
        )
        return bound


def _java_analyzer_source_snapshot(helper: Path) -> tuple[dict[str, object], bytes]:
    expected = ENGINE_ROOT / "native" / "java" / "Analyzer.java"
    if not helper.is_absolute() or helper != expected:
        raise RouteError("JAVA_ANALYZER_SOURCE_UNSAFE")
    guarded_content = _read_csharp_bound_file(
        helper,
        ENGINE_ROOT,
        failure="JAVA_ANALYZER_SOURCE_UNSAFE",
        maximum_bytes=_JAVA_ANALYZER_SOURCE_MAX_BYTES,
    )
    content = _stable_read_regular_file(
        helper,
        failure="JAVA_ANALYZER_SOURCE_UNSAFE",
        maximum_bytes=_JAVA_ANALYZER_SOURCE_MAX_BYTES,
        allowed_uids=frozenset({os.getuid()}),
    )
    final_content = _read_csharp_bound_file(
        helper,
        ENGINE_ROOT,
        failure="JAVA_ANALYZER_SOURCE_UNSAFE",
        maximum_bytes=_JAVA_ANALYZER_SOURCE_MAX_BYTES,
    )
    if content != guarded_content or content != final_content:
        raise RouteError("JAVA_ANALYZER_SOURCE_UNSAFE_CHANGED")
    binding: dict[str, object] = {
        "path": str(helper),
        "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
    }
    return binding, content


def _java_analyzer_source_binding(helper: Path) -> dict[str, object]:
    binding, _ = _java_analyzer_source_snapshot(helper)
    return binding


def _java_analyzer_snapshot_binding(snapshot: Path, root: Path) -> dict[str, object]:
    try:
        root_metadata = root.lstat()
        resolved_root = root.resolve(strict=True)
    except OSError as error:
        raise RouteError("JAVA_ANALYZER_SNAPSHOT_UNSAFE") from error
    if (
        root != resolved_root
        or root.is_symlink()
        or not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid != os.getuid()
        or stat.S_IMODE(root_metadata.st_mode) != 0o700
        or snapshot.parent != root
        or snapshot.name != "Analyzer.java"
    ):
        raise RouteError("JAVA_ANALYZER_SNAPSHOT_UNSAFE")
    content = _stable_read_regular_file(
        snapshot,
        failure="JAVA_ANALYZER_SNAPSHOT_UNSAFE",
        maximum_bytes=_JAVA_ANALYZER_SOURCE_MAX_BYTES,
        allowed_uids=frozenset({os.getuid()}),
    )
    try:
        metadata = snapshot.lstat()
    except OSError as error:
        raise RouteError("JAVA_ANALYZER_SNAPSHOT_UNSAFE") from error
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise RouteError("JAVA_ANALYZER_SNAPSHOT_UNSAFE")
    return {
        "path": str(snapshot),
        "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
    }


def _write_java_analyzer_snapshot(root: Path, content: bytes) -> tuple[Path, dict[str, object]]:
    snapshot = root / "Analyzer.java"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(snapshot, flags, 0o600)
        try:
            written = 0
            while written < len(content):
                chunk_bytes = os.write(descriptor, content[written:])
                if chunk_bytes <= 0:
                    raise OSError("zero-byte Java analyzer snapshot write")
                written += chunk_bytes
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise RouteError("JAVA_ANALYZER_SNAPSHOT_CREATE_FAILED") from error
    binding = _java_analyzer_snapshot_binding(snapshot, root)
    if binding["sha256"] != "sha256:" + hashlib.sha256(content).hexdigest() or binding["bytes"] != len(content):
        raise RouteError("JAVA_ANALYZER_SNAPSHOT_CONTENT_MISMATCH")
    return snapshot, binding


def _verify_trusted_java_toolchain(expected: ExactToolchain) -> None:
    digest = re.compile(r"[0-9a-f]{64}").fullmatch
    if (
        expected.language != "java"
        or expected.version != "21.0.11"
        or not Path(expected.executable).is_absolute()
        or expected.auxiliary is None
        or not Path(expected.auxiliary).is_absolute()
        or not expected.profile
        or expected.executable_sha256 is None
        or digest(expected.executable_sha256) is None
        or expected.auxiliary_sha256 is None
        or digest(expected.auxiliary_sha256) is None
    ):
        raise RouteError("JAVA_ANALYZER_TOOLCHAIN_POLICY_INVALID")
    try:
        current = exact_toolchain("java")
    except RouteError as error:
        raise RouteError("JAVA_ANALYZER_TOOLCHAIN_CHANGED") from error
    if current != expected:
        raise RouteError("JAVA_ANALYZER_TOOLCHAIN_CHANGED")


def _java_analyzer_arguments(arguments: list[str]) -> None:
    if (
        len(arguments) not in {2, 3}
        or any(not isinstance(argument, str) or not argument for argument in arguments)
        or any("\n" in argument or "\r" in argument or "\x00" in argument for argument in arguments)
        or (len(arguments) == 3 and arguments[2] != "--emitted-target")
        or arguments[1] in {"--inventory", "--emitted-target"}
    ):
        raise RouteError("JAVA_ANALYZER_COMMAND_SHAPE_INVALID")
    source = Path(arguments[0])
    try:
        resolved = source.resolve(strict=True)
    except OSError as error:
        raise RouteError("JAVA_ANALYZER_COMMAND_SHAPE_INVALID") from error
    if not source.is_absolute() or source != resolved or source.is_symlink() or not source.is_file():
        raise RouteError("JAVA_ANALYZER_COMMAND_SHAPE_INVALID")


_JAVA_ANALYZER_CLASS_RECEIPT = "class-receipt.json"


def _verify_java_analyzer_classes(classes: Path, receipt: Mapping[str, Any]) -> None:
    """Refuse to execute bytecode that is not the bytecode we recorded."""
    recorded = receipt.get("classes")
    if not isinstance(recorded, dict) or not recorded:
        raise RouteError("JAVA_ANALYZER_CLASS_RECEIPT_INVALID")
    observed = {
        path.relative_to(classes).as_posix(): path
        for path in classes.rglob("*.class")
        if path.is_file() and not path.is_symlink()
    }
    if set(observed) != set(recorded):
        raise RouteError("JAVA_ANALYZER_CLASS_SET_CHANGED")
    for relative, digest in sorted(recorded.items()):
        if _sha256_file(observed[relative]) != digest:
            raise RouteError("JAVA_ANALYZER_CLASS_CHANGED")


def _java_analyzer_classes(helper: Path, toolchain: ExactToolchain) -> tuple[Path, dict[str, Any]] | None:
    """Compile the Java analyzer once and bind the bytecode to its source.

    The engine runs the analyzer through JEP 330's source launcher, which
    recompiles `Analyzer.java` on every invocation -- measured at ~1.65s per
    call against ~0.56s for an already-compiled class, and the analyzer runs
    once per candidate function.

    The source-launcher form is not merely convenient, though: it is what makes
    the executed program byte-bound to the source this module hashed.  Caching
    bytecode has to preserve that property rather than trade it away, so the
    cache is keyed on the compiler binary and the analyzer source digest, and a
    receipt records the digest of every class file produced from them.  Those
    digests are re-checked before every run, so "what executed" stays provably
    derived from "what we hashed" -- the binding moves from source to bytecode
    and is established once under a content-addressed key, instead of being
    re-derived on every call.

    Returns ``None`` when the compiler is unavailable or the cache cannot be
    written, which falls back to the existing source-launcher path.
    """
    compiler = Path(toolchain.executable).parent / "javac"
    if not compiler.is_file():
        return None
    try:
        key = _toolchain_build_cache_key("java", compiler, files=(helper,), salt=("release=21",))
    except OSError:
        return None
    directories = _toolchain_build_cache("java", key, ("classes",))
    if directories is None:
        return None
    (classes,) = directories
    receipt_path = classes.parent / _JAVA_ANALYZER_CLASS_RECEIPT

    if receipt_path.is_file():
        try:
            receipt = json.loads(receipt_path.read_text())
            _verify_java_analyzer_classes(classes, receipt)
            return classes, receipt
        except (OSError, ValueError, RouteError):
            # A damaged or tampered cache entry is rebuilt, never trusted.
            shutil.rmtree(classes, ignore_errors=True)
            classes.mkdir(mode=0o700, parents=True, exist_ok=True)

    staging = classes.parent / f".staging-{os.getpid()}"
    shutil.rmtree(staging, ignore_errors=True)
    try:
        staging.mkdir(mode=0o700, parents=True)
        completed = subprocess.run(
            [str(compiler), "--release", "21", "-nowarn", "-d", str(staging), str(helper)],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if completed.returncode != 0:
            shutil.rmtree(staging, ignore_errors=True)
            return None
        produced = sorted(p for p in staging.rglob("*.class") if p.is_file())
        if not produced:
            shutil.rmtree(staging, ignore_errors=True)
            return None
        receipt = {
            "cache_schema": _TOOLCHAIN_BUILD_CACHE_SCHEMA,
            "cache_key": key,
            "cache_scope": "content-addressed-persistent",
            "analyzer_source_sha256": _sha256_file(helper),
            "compiler_sha256": _sha256_file(compiler),
            "classes": {path.relative_to(staging).as_posix(): _sha256_file(path) for path in produced},
        }
        # Publish atomically, so a concurrent reader never observes a partial
        # class set.  Two writers derived the same key from the same inputs, so
        # whichever lands is equivalent by construction.
        shutil.rmtree(classes, ignore_errors=True)
        staging.rename(classes)
        receipt_path.write_text(json.dumps(receipt, sort_keys=True))
    except (OSError, subprocess.SubprocessError):
        shutil.rmtree(staging, ignore_errors=True)
        return None
    return classes, receipt


def _run_trusted_java_analyzer(
    toolchain: ExactToolchain,
    helper: Path,
    arguments: list[str],
    *,
    allowed_domain_errors: frozenset[str],
) -> dict[str, Any]:
    """Run the exact source-file Java analyzer with fail-closed error promotion."""

    if allowed_domain_errors != _JAVA_ANALYZE_PROMOTABLE_DOMAIN_ERRORS:
        raise RouteError("JAVA_ANALYZER_DOMAIN_ERROR_POLICY_INVALID")
    _java_analyzer_arguments(arguments)
    expected_helper, helper_content = _java_analyzer_source_snapshot(helper)
    with tempfile.TemporaryDirectory(prefix="elmos-java-analyzer-") as temporary:
        root = Path(temporary).resolve(strict=True)
        root.chmod(0o700)
        snapshot, expected_snapshot = _write_java_analyzer_snapshot(root, helper_content)
        try:
            current_helper = _java_analyzer_source_binding(helper)
        except RouteError as error:
            raise RouteError("JAVA_ANALYZER_SOURCE_CHANGED_BEFORE_EXECUTION") from error
        if current_helper != expected_helper:
            raise RouteError("JAVA_ANALYZER_SOURCE_CHANGED_BEFORE_EXECUTION")
        _verify_trusted_java_toolchain(toolchain)
        # Prefer the cached bytecode, whose digests were just re-verified
        # against the receipt built from this exact source; fall back to the
        # source launcher whenever the cache is unavailable, so behaviour is
        # identical either way and only the compile cost differs.
        cached_classes = _java_analyzer_classes(helper, toolchain)
        if cached_classes is not None:
            classes, _class_receipt = cached_classes
            command = [toolchain.executable, "-cp", str(classes), "Analyzer", *arguments]
        else:
            command = [toolchain.executable, "--source", "21", str(snapshot), *arguments]
        try:
            value = _run(command, cwd=root)
        except RouteError as error:
            try:
                current_snapshot = _java_analyzer_snapshot_binding(snapshot, root)
            except RouteError as verification_error:
                raise RouteError("JAVA_ANALYZER_SNAPSHOT_CHANGED_DURING_EXECUTION") from verification_error
            if current_snapshot != expected_snapshot:
                raise RouteError("JAVA_ANALYZER_SNAPSHOT_CHANGED_DURING_EXECUTION") from error
            try:
                current_helper = _java_analyzer_source_binding(helper)
            except RouteError as verification_error:
                raise RouteError("JAVA_ANALYZER_SOURCE_CHANGED_DURING_EXECUTION") from verification_error
            if current_helper != expected_helper:
                raise RouteError("JAVA_ANALYZER_SOURCE_CHANGED_DURING_EXECUTION") from error
            _verify_trusted_java_toolchain(toolchain)
            wrapped = str(error)
            for reason in allowed_domain_errors:
                if wrapped == f"NATIVE_ANALYZER_FAILED:{toolchain.executable}:{reason}":
                    raise RouteError(reason) from error
            raise
        try:
            current_snapshot = _java_analyzer_snapshot_binding(snapshot, root)
        except RouteError as error:
            raise RouteError("JAVA_ANALYZER_SNAPSHOT_CHANGED_DURING_EXECUTION") from error
        if current_snapshot != expected_snapshot:
            raise RouteError("JAVA_ANALYZER_SNAPSHOT_CHANGED_DURING_EXECUTION")
        try:
            current_helper = _java_analyzer_source_binding(helper)
        except RouteError as error:
            raise RouteError("JAVA_ANALYZER_SOURCE_CHANGED_DURING_EXECUTION") from error
        if current_helper != expected_helper:
            raise RouteError("JAVA_ANALYZER_SOURCE_CHANGED_DURING_EXECUTION")
        _verify_trusted_java_toolchain(toolchain)
        return value


def _run_csharp_semantic_cli(
    toolchain: ExactToolchain,
    arguments: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    binary, receipt = _csharp_analyzer(toolchain)
    value = _run(
        [toolchain.executable, str(binary), *arguments],
        cwd=binary.parent,
    )
    verified_binary, verified_receipt = _csharp_analyzer(toolchain)
    if verified_binary != binary or verified_receipt != receipt:
        raise RouteError("CSHARP_ANALYZER_CHANGED_DURING_EXECUTION")
    return _bind_csharp_analyzer_identity(value, receipt), receipt


def _validated_module_inventory(
    value: dict[str, Any],
    language: Language,
    source: Path,
    source_bytes: bytes,
) -> dict[str, Any]:
    expected_inventory_keys = {
        "schema_version",
        "kind",
        "profile",
        "source_language",
        "source_file",
        "analyzer",
        "analyzer_version",
        "enumeration_status",
        "subjects",
        "diagnostics",
    }
    if set(value) != expected_inventory_keys:
        raise RouteError(f"MODULE_INVENTORY_KEYS_INVALID:{language}:{source.name}")
    if (
        value.get("schema_version") != "1.0.0"
        or value.get("kind") != MODULE_INVENTORY_KIND
        or value.get("profile") != MODULE_INVENTORY_PROFILE
        or value.get("source_language") != language
        or value.get("source_file") != source.name
    ):
        raise RouteError(f"MODULE_INVENTORY_IDENTITY_INVALID:{language}:{source.name}")
    status = value.get("enumeration_status")
    subjects = value.get("subjects")
    diagnostics = value.get("diagnostics")
    if status not in {"PASSED", "FAILED"} or not isinstance(subjects, list) or not isinstance(diagnostics, list):
        raise RouteError(f"MODULE_INVENTORY_CONTRACT_INVALID:{language}:{source.name}")

    normalized_subjects: list[dict[str, Any]] = []
    occurrences: dict[tuple[str, str], int] = {}
    for raw in subjects:
        if not isinstance(raw, dict):
            raise RouteError(f"MODULE_INVENTORY_SUBJECT_INVALID:{language}:{source.name}")
        if set(raw) != {
            "name",
            "qualified_name",
            "declaration_kind",
            "analyzable",
            "source_span",
            "signature",
        }:
            raise RouteError(f"MODULE_INVENTORY_SUBJECT_KEYS_INVALID:{language}:{source.name}")
        name = raw.get("name")
        qualified_name = raw.get("qualified_name")
        declaration_kind = raw.get("declaration_kind")
        analyzable = raw.get("analyzable")
        source_span = raw.get("source_span")
        signature = raw.get("signature")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(qualified_name, str)
            or not qualified_name
            or not isinstance(declaration_kind, str)
            or not declaration_kind
            or not isinstance(analyzable, bool)
            or not isinstance(signature, dict)
        ):
            raise RouteError(f"MODULE_INVENTORY_SUBJECT_INVALID:{language}:{source.name}")
        if source_span is not None:
            if not isinstance(source_span, dict):
                raise RouteError(f"MODULE_INVENTORY_SPAN_INVALID:{language}:{source.name}")
            span_file = source_span.get("file")
            start_byte = source_span.get("start_byte")
            end_byte = source_span.get("end_byte")
            if (
                span_file != source.name
                or not isinstance(start_byte, int)
                or not isinstance(end_byte, int)
                or start_byte < 0
                or end_byte <= start_byte
                or end_byte > source.stat().st_size
            ):
                raise RouteError(f"MODULE_INVENTORY_SPAN_INVALID:{language}:{source.name}")
        occurrence_key = (declaration_kind, qualified_name)
        occurrence = occurrences.get(occurrence_key, 0) + 1
        occurrences[occurrence_key] = occurrence
        normalized_subjects.append(
            {
                "name": name,
                "qualified_name": qualified_name,
                "declaration_kind": declaration_kind,
                "analyzable": analyzable,
                "source_span": source_span,
                "signature": signature,
                "occurrence": occurrence,
            }
        )
    return {
        **value,
        "source_artifact_sha256": "sha256:" + hashlib.sha256(source_bytes).hexdigest(),
        "source_artifact_bytes": len(source_bytes),
        "directives": _scan_preprocessor_directives(source, language, source_bytes),
        "subjects": normalized_subjects,
        "diagnostics": [str(item) for item in diagnostics],
    }


def inventory_module(source: Path, language: Language) -> dict[str, Any]:
    """Enumerate one file with its real parser/compiler frontend.

    This is deliberately separate from ``analyze``: enumeration establishes
    file closure, while the existing named-function mode decides whether each
    enumerated callable fits ``typed-pure-function-v1``.
    """

    raw_source = source.expanduser()
    if raw_source.is_symlink():
        raise RouteError("SOURCE_FILE_UNSAFE_OR_TOO_LARGE")
    source = raw_source.resolve()
    if not source.is_file() or source.stat().st_size > 2_000_000:
        raise RouteError("SOURCE_FILE_UNSAFE_OR_TOO_LARGE")
    if language == "python":
        raise RouteError("PYTHON_MODULE_INVENTORY_USES_CPYTHON_AST")
    source_bytes = source.read_bytes()
    toolchain = exact_toolchain(language)
    analyzer_build_receipt: dict[str, Any] | None = None
    if language in ("cpp", "objc"):
        value = inventory_clang_module(
            source,
            language,
            toolchain.executable,
            toolchain.version,
            sdk_path=_toolchain_profile_value(toolchain.profile, "sdk-path"),
        )
    elif language == "java":
        helper = ENGINE_ROOT / "native" / "java" / "Analyzer.java"
        value = _run(
            [toolchain.executable, "--source", "21", str(helper), str(source), "--inventory"],
            cwd=ENGINE_ROOT,
        )
    elif language == "csharp":
        value, _ = _run_csharp_semantic_cli(
            toolchain,
            [str(source), "--inventory"],
        )
    elif language == "typescript":
        value = _run_trusted_typescript_analyzer(toolchain, source, "--inventory")
    elif language == "javascript":
        value = _run_trusted_javascript_analyzer(toolchain, source, "--inventory")
    elif language == "go":
        helper = ENGINE_ROOT / "native" / "go" / "analyzer.go"
        value = _run(
            [toolchain.executable, "run", str(helper), "--", str(source), "--inventory"],
            cwd=ENGINE_ROOT,
            environment_overrides=_go_build_cache_environment(helper, Path(toolchain.executable)),
        )
    elif language == "rust":
        package = ENGINE_ROOT / "native" / "rust"
        assert toolchain.auxiliary is not None
        value = _run(
            [
                toolchain.auxiliary,
                "run",
                "--quiet",
                "--offline",
                "--locked",
                "--manifest-path",
                str(package / "Cargo.toml"),
                "--",
                str(source),
                "--inventory",
            ],
            cwd=package,
            timeout=900,
            isolated_cargo=True,
            cargo_package=package,
        )
    elif language == "swift":
        binary, analyzer_build_receipt = _swift_analyzer(toolchain)
        value = _bind_swift_analyzer_identity(
            _run_trusted_swift_analyzer(
                binary,
                analyzer_build_receipt,
                [str(source), "--inventory"],
                allowed_domain_errors=frozenset(),
            ),
            analyzer_build_receipt,
        )
    else:
        raise RouteError(f"MODULE_INVENTORY_UNSUPPORTED:{language}")
    if source.read_bytes() != source_bytes:
        raise RouteError(f"MODULE_INVENTORY_SOURCE_CHANGED:{language}:{source.name}")
    validated = _validated_module_inventory(value, language, source, source_bytes)
    if analyzer_build_receipt is not None:
        validated["analyzer_build_receipt"] = analyzer_build_receipt
    return validated


_BATCH_ANALYZABLE_LANGUAGES: Final[frozenset[str]] = frozenset({"java", "go", "rust"})


def analyze_many(
    source: Path,
    language: Language,
    function_names: Sequence[str],
    *,
    emitted_target: bool = False,
) -> dict[str, SemanticIR | RouteError]:
    """Analyze every candidate in one file, ideally with one analyzer process.

    Discovery asks the native analyzer about one *function* at a time, so a file
    with eight candidates starts eight processes -- and every one of them
    recompiles the same target source before answering about a different method
    of it.  The compile is the entire cost; the scan is free by comparison.

    Batching is introduced strictly as an optimisation with a fallback, never as
    a second oracle.  The batch is attempted first; if it does not return a
    well-formed result for every requested name -- for any reason at all,
    including an analyzer crash partway through -- this falls back to the
    original one-process-per-function path and returns exactly what that would
    have returned.  So the fast path can only ever be taken when it agrees, and
    a verdict never depends on which path produced it.

    That distinction matters most for rejections.  The analyzer signals a
    *promotable* domain rejection by exiting cleanly with a known message; other
    failures surface as a stack trace and must stay unpromotable, because
    `_run_trusted_java_analyzer` deliberately refuses to read a domain error out
    of one.  The batch therefore captures only the promotable kind, and anything
    else aborts it into the per-function path where the existing fail-closed
    handling applies unchanged.
    """
    requested = list(dict.fromkeys(function_names))
    if language in _BATCH_ANALYZABLE_LANGUAGES and len(requested) > 1:
        batched = _analyze_batch(source, language, requested, emitted_target=emitted_target)
        if batched is not None:
            return batched
    results: dict[str, SemanticIR | RouteError] = {}
    for name in requested:
        try:
            results[name] = analyze(source, language, name, emitted_target=emitted_target)
        except RouteError as error:
            results[name] = error
    return results


def _analyze_batch(
    source: Path,
    language: Language,
    function_names: Sequence[str],
    *,
    emitted_target: bool,
) -> dict[str, SemanticIR | RouteError] | None:
    """One analyzer process for a whole file, or ``None`` to fall back."""
    if language not in _BATCH_ANALYZABLE_LANGUAGES:
        return None
    if any("," in name for name in function_names):
        # The wire format is comma-delimited; a name containing one would be
        # silently split, so refuse the fast path rather than guess.
        return None
    raw_source = source.expanduser()
    if raw_source.is_symlink():
        raise RouteError("SOURCE_FILE_UNSAFE_OR_TOO_LARGE")
    resolved = raw_source.resolve()
    if not resolved.is_file() or resolved.stat().st_size > 2_000_000:
        raise RouteError("SOURCE_FILE_UNSAFE_OR_TOO_LARGE")
    if emitted_target:
        _verify_emitted_helper_sources(resolved, language)
    toolchain = exact_toolchain(language)
    selector = "--functions=" + ",".join(function_names)

    # `promote` turns a batch entry's rejection code into exactly the error the
    # per-function path would have raised for the same rejection.  Returning
    # ``None`` from it means "this code is not one this fast path is entitled to
    # interpret", which drops the whole batch to the fallback.
    promote: Any
    try:
        if language == "java":
            helper = ENGINE_ROOT / "native" / "java" / "Analyzer.java"
            arguments = [str(resolved), selector]
            if emitted_target:
                arguments.append("--emitted-target")
            document = _run_trusted_java_analyzer(
                toolchain,
                helper,
                arguments,
                allowed_domain_errors=_JAVA_ANALYZE_PROMOTABLE_DOMAIN_ERRORS,
            )
            # Java promotes only an explicit allow-list; every other failure has
            # to stay a hard failure, which is what the forged-stack-trace tests
            # in `test_native_validation.py` exist to guarantee.
            def promote(reason: str) -> RouteError | None:
                return RouteError(reason) if reason in _JAVA_ANALYZE_PROMOTABLE_DOMAIN_ERRORS else None

        elif language == "go":
            helper = ENGINE_ROOT / "native" / "go" / "analyzer.go"
            arguments = [str(resolved), selector]
            if emitted_target:
                arguments.append("--emitted-target")
            document = _run(
                [toolchain.executable, "run", str(helper), "--", *arguments],
                cwd=ENGINE_ROOT,
                environment_overrides=_go_build_cache_environment(helper, Path(toolchain.executable)),
            )
            # Go has no promotion list: a rejected function fails the analyzer
            # process, and `_run` wraps whatever it printed.  Reconstructing that
            # exact wrapping is what keeps a batched rejection indistinguishable
            # from the individual call it replaced.
            def promote(reason: str) -> RouteError | None:
                return RouteError(f"NATIVE_ANALYZER_FAILED:{toolchain.executable}:{reason}")

        elif language == "rust":
            package = ENGINE_ROOT / "native" / "rust"
            if toolchain.auxiliary is None:
                return None
            cargo = toolchain.auxiliary
            document = _run(
                [
                    cargo,
                    "run",
                    "--quiet",
                    "--offline",
                    "--locked",
                    "--manifest-path",
                    str(package / "Cargo.toml"),
                    "--",
                    str(resolved),
                    selector,
                    *(["--emitted-target"] if emitted_target else []),
                ],
                cwd=package,
                timeout=900,
                isolated_cargo=True,
                cargo_package=package,
            )

            def promote(reason: str) -> RouteError | None:
                return RouteError(f"NATIVE_ANALYZER_FAILED:{cargo}:{reason}")

        else:
            return None
    except RouteError:
        return None
    if document.get("kind") != "elmos.typed-pure-function-batch":
        return None
    entries = document.get("results")
    if not isinstance(entries, list):
        return None

    results: dict[str, SemanticIR | RouteError] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            return None
        name = entry.get("function")
        status = entry.get("status")
        if not isinstance(name, str):
            return None
        if status == "ok":
            value = entry.get("value")
            if not isinstance(value, dict):
                return None
            try:
                results[name] = SemanticIR.from_mapping(value)
            except (RouteError, ValueError, TypeError):
                return None
        elif status == "domain_error":
            reason = entry.get("error")
            if not isinstance(reason, str):
                return None
            # Only a rejection the single-function path would itself have
            # produced may be reconstructed here; anything else means the batch
            # saw a failure mode this fast path is not entitled to interpret,
            # and the whole file drops to the per-function path.
            promoted = promote(reason)
            if promoted is None:
                return None
            results[name] = promoted
        else:
            return None
    if set(results) != set(function_names):
        return None
    return results


def _external_semantic_ir(value: dict[str, Any]) -> SemanticIR:
    """Bind the analyzer's JSON contract before anything downstream trusts it.

    Grafted from the other side of this merge: this side's analyzers are its
    own, but nothing validated their output shape.  An analyzer that returns
    no functions and one diagnostic is reporting a real source problem, and
    promoting that diagnostic is far more useful than the shapeless failure a
    caller would otherwise see several layers later.
    """
    functions = value.get("functions")
    diagnostics = value.get("diagnostics")
    if not isinstance(functions, list) or not isinstance(diagnostics, list):
        raise RouteError("NATIVE_ANALYZER_CONTRACT_INVALID:FUNCTIONS_OR_DIAGNOSTICS")
    if not functions:
        if diagnostics and all(isinstance(item, str) and item for item in diagnostics):
            raise RouteError(str(diagnostics[0]))
        raise RouteError("NATIVE_ANALYZER_CONTRACT_INVALID:EMPTY_FUNCTIONS_WITHOUT_DIAGNOSTIC")
    try:
        semantic = SemanticIR.from_mapping(value)
    except RouteError as error:
        raise RouteError(f"NATIVE_ANALYZER_CONTRACT_INVALID:{error}") from error
    if not semantic.functions:
        raise RouteError("NATIVE_ANALYZER_CONTRACT_INVALID:NO_PARSED_FUNCTIONS")
    return semantic


def analyze(
    source: Path,
    language: Language,
    function_name: str,
    *,
    emitted_target: bool = False,
) -> SemanticIR:
    raw_source = source.expanduser()
    if raw_source.is_symlink():
        raise RouteError("SOURCE_FILE_UNSAFE_OR_TOO_LARGE")
    source = raw_source.resolve()
    if not source.is_file() or source.stat().st_size > 2_000_000:
        raise RouteError("SOURCE_FILE_UNSAFE_OR_TOO_LARGE")
    if emitted_target and language not in ROUTED_LANGUAGES and language not in NATIVE_RELIFTABLE_LANGUAGES:
        raise RouteError(f"EMITTED_TARGET_REANALYSIS_UNSUPPORTED:{language}")
    if emitted_target:
        _verify_emitted_helper_sources(source, language)
    toolchain = exact_toolchain(language)
    if language == "python":
        return analyze_python(source, function_name, emitted_target=emitted_target)
    if language in ("cpp", "objc"):
        return analyze_clang(
            source,
            language,
            function_name,
            toolchain.executable,
            toolchain.version,
            emitted_target=emitted_target,
            sdk_path=_toolchain_profile_value(toolchain.profile, "sdk-path"),
        )
    if language == "swift":
        binary, receipt = _swift_analyzer(toolchain)
        value = _bind_swift_analyzer_identity(
            _run_trusted_swift_analyzer(
                binary,
                receipt,
                [str(source), function_name, *(["--emitted-target"] if emitted_target else [])],
                allowed_domain_errors=_SWIFT_ANALYZE_PROMOTABLE_DOMAIN_ERRORS,
            ),
            receipt,
        )
        return SemanticIR.from_mapping(value)
    if language == "java":
        helper = ENGINE_ROOT / "native" / "java" / "Analyzer.java"
        arguments = [str(source), function_name]
        if emitted_target:
            arguments.append("--emitted-target")
        value = _run_trusted_java_analyzer(
            toolchain,
            helper,
            arguments,
            allowed_domain_errors=_JAVA_ANALYZE_PROMOTABLE_DOMAIN_ERRORS,
        )
    elif language == "csharp":
        arguments = [str(source), function_name]
        if emitted_target:
            arguments.append("--emitted-target")
            project = ENGINE_ROOT / "native" / "csharp"
            value = _run(
                [toolchain.executable, "run", "--project", str(project), "--", *arguments],
                cwd=REPOSITORY_ROOT,
            )
        else:
            value, _ = _run_csharp_semantic_cli(toolchain, arguments)
    elif language == "go":
        helper = ENGINE_ROOT / "native" / "go" / "analyzer.go"
        arguments = [str(source), function_name]
        if emitted_target:
            arguments.append("--emitted-target")
        value = _run(
            [toolchain.executable, "run", str(helper), "--", *arguments],
            cwd=ENGINE_ROOT,
            environment_overrides=_go_build_cache_environment(helper, Path(toolchain.executable)),
        )
    elif language == "rust":
        package = ENGINE_ROOT / "native" / "rust"
        assert toolchain.auxiliary is not None
        value = _run(
            [
                toolchain.auxiliary,
                "run",
                "--quiet",
                "--offline",
                "--locked",
                "--manifest-path",
                str(package / "Cargo.toml"),
                "--",
                str(source),
                function_name,
                *(["--emitted-target"] if emitted_target else []),
            ],
            cwd=package,
            timeout=900,
            isolated_cargo=True,
            cargo_package=package,
        )
    elif language == "javascript":
        value = _run_trusted_javascript_analyzer(
            toolchain,
            source,
            function_name,
            emitted_target=emitted_target,
        )
    elif language == "typescript":
        value = _run_trusted_typescript_analyzer(
            toolchain,
            source,
            function_name,
            emitted_target=emitted_target,
        )
    elif language == "php":
        value = _run_trusted_php_analyzer(
            toolchain,
            source,
            function_name,
            emitted_target=emitted_target,
        )
    else:
        raise RouteError(f"NATIVE_ANALYZER_UNSUPPORTED:{language}")
    return _external_semantic_ir(value)
